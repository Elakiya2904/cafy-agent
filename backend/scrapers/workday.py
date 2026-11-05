"""Fetch and normalize job listings from Workday career sites.

Queries configured Workday tenants, applies supported location filters, and
normalizes returned postings.
"""
import logging
import concurrent.futures
from typing import List, Dict, Any, Optional
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.workday")

UK_DESCRIPTORS = ("united kingdom", "uk", "great britain", "gb", "england", "scotland", "wales", "northern ireland")
DETAIL_WORKERS = 8


class WorkdayScraper(BaseScraper):
    platform_name = "workday"

    def _find_uk_facet(self, facets: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Find the UK value in a location/country facet.

        Many tenants nest locations (e.g. NVIDIA: locationMainGroup -> locationHierarchy1 -> 'United Kingdom').
        Only checking the top level meant no UK filter was applied for those tenants, so we pulled the first
        2000 global postings and lost UK roles beyond that cut-off.
        """
        for facet in facets:
            param = facet.get("facetParameter", "")
            label = (param + facet.get("descriptor", "")).lower()
            values = facet.get("values") or []
            if "country" in label or "location" in label:
                ids = [
                    v["id"] for v in values
                    if (v.get("descriptor") or "").strip().lower() in UK_DESCRIPTORS and v.get("id")
                ]
                if ids:
                    return {param: ids}
            # Nested facet groups: each value may itself be a facet with its own values.
            nested = [v for v in values if isinstance(v.get("values"), list) and v.get("facetParameter")]
            if nested:
                found = self._find_uk_facet(nested)
                if found:
                    return found
        return {}

    def _uk_country_facet(self, url: str, headers: Dict[str, str]) -> Dict[str, List[str]]:
        """Use the tenant's country facet (when it has one) to ask Workday for UK jobs only."""
        resp = self.post(url, json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}, headers=headers)
        if not resp:
            return {}
        try:
            return self._find_uk_facet(resp.json().get("facets", []))
        except Exception:
            return {}

    def _detail(self, base: str, ext_path: str) -> Optional[Dict[str, Any]]:
        """Posting detail: the listing only says '3 Locations' and carries no description."""
        resp = self.get(f"{base}{ext_path}", headers={"Accept": "application/json"})
        if not resp:
            return None
        try:
            return resp.json().get("jobPostingInfo") or None
        except Exception:
            return None

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        tenant = company_config.get("tenant", "").strip()
        name = company_config.get("name", tenant.title()).strip()
        host = company_config.get("host", "").strip() or f"{tenant}.wd1.myworkdayjobs.com"
        site = company_config.get("site", "").strip() or f"{tenant}_careers"

        if not tenant:
            return []

        base = f"https://{host}/wday/cxs/{tenant}/{site}"
        url = f"{base}/jobs"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        postings: List[Dict[str, Any]] = []
        limit = 20
        offset = 0
        max_total = 2000  # Workday does not serve results beyond ~2000 per query
        applied_facets = self._uk_country_facet(url, headers)
        total_available = None

        while offset < max_total:
            payload = {
                "appliedFacets": applied_facets,
                "limit": limit,
                "offset": offset,
                "searchText": ""
            }

            resp = self.post(url, json=payload, headers=headers)
            if not resp:
                break

            try:
                data = resp.json()
            except Exception as e:
                logger.error(f"[Workday] Failed to parse JSON for {tenant}: {e}")
                break

            job_postings = data.get("jobPostings", [])
            if not job_postings:
                break
            postings.extend(p for p in job_postings if p.get("externalPath"))

            if total_available is None:
                # Workday only reports "total" on the first page; later pages return 0
                total_available = data.get("total", 0)
            offset += limit
            if offset >= min(total_available, max_total):
                break

        # Fetch details only where they can matter: everything when the UK facet is applied, otherwise
        # postings whose listing text is UK or an opaque "N Locations" summary.
        def wants_detail(p: Dict[str, Any]) -> bool:
            text = p.get("locationsText") or ""
            return bool(applied_facets) or "locations" in text.lower() or JobNormalizer.is_uk_location(text)

        targets = [p for p in postings if wants_detail(p)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
            details = dict(zip(
                (p["externalPath"] for p in targets),
                pool.map(lambda p: self._detail(base, p["externalPath"]), targets),
            ))

        normalized_jobs = []
        for item in postings:
            ext_path = item["externalPath"]
            info = details.get(ext_path) or {}
            source_id = ext_path.strip("/").replace("/", "_")
            # Public job page is /<locale>/<site>/job/...; the tenant is NOT part of this path (it 404s).
            job_url = info.get("externalUrl") or f"https://{host}/en-US/{site}{ext_path}"

            locs = [info.get("location")] + list(info.get("additionalLocations") or [])
            locs = [l for l in locs if l] or [item.get("locationsText") or ""]
            loc = "; ".join(dict.fromkeys(locs))
            country = ((info.get("country") or {}).get("descriptor") or "").strip()
            if (country and len(locs) == 1 and country.lower() not in loc.lower()
                    and not JobNormalizer._is_uk_site(loc)):
                loc = f"{loc}, {country}"

            title = item.get("title")
            # Never invent a description: an empty one makes the UI link to the employer's posting instead.
            description = info.get("jobDescription") or ""

            raw_job = {
                "source_id": source_id,
                "title": title,
                "company": name,
                "location": loc,
                "is_remote": "remote" in loc.lower(),
                "url": job_url,
                "description": description,
                "department": "",
                "employment_type": info.get("timeType") or "",
                "posted_at": info.get("startDate") or item.get("postedOn")
            }

            norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
            if norm:
                normalized_jobs.append(norm)

        logger.info(
            f"[Workday] Fetched {len(normalized_jobs)} jobs for {name} ({tenant}); "
            f"UK facet={'yes' if applied_facets else 'no'}, details fetched={len(targets)}"
        )
        return normalized_jobs

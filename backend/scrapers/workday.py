import logging
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.workday")

class WorkdayScraper(BaseScraper):
    platform_name = "workday"

    def _uk_ireland_facets(self, url: str, headers: Dict[str, str]) -> Dict[str, List[str]]:
        """Use the tenant's country facet (when it has one) to ask Workday for UK/Ireland jobs only."""
        resp = self.post(url, json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}, headers=headers)
        if not resp:
            return {}
        try:
            facets = resp.json().get("facets", [])
        except Exception:
            return {}
        for facet in facets:
            param = facet.get("facetParameter", "")
            if "country" not in (param + facet.get("descriptor", "")).lower():
                continue
            ids = [
                v["id"] for v in facet.get("values", [])
                if v.get("descriptor", "").strip().lower() in ("united kingdom", "ireland", "uk")
                and v.get("id")
            ]
            if ids:
                return {param: ids}
        return {}

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        tenant = company_config.get("tenant", "").strip()
        name = company_config.get("name", tenant.title()).strip()
        host = company_config.get("host", "").strip() or f"{tenant}.wd1.myworkdayjobs.com"
        site = company_config.get("site", "").strip() or f"{tenant}_careers"

        if not tenant:
            return []

        url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        normalized_jobs = []
        limit = 20
        offset = 0
        max_total = 2000  # Workday does not serve results beyond ~2000 per query
        applied_facets = self._uk_ireland_facets(url, headers)
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

            for item in job_postings:
                ext_path = item.get("externalPath", "")
                if not ext_path:
                    continue

                source_id = ext_path.strip("/").replace("/", "_")
                job_url = f"https://{host}/en-US/{tenant}/{site}{ext_path}"
                loc = item.get("locationsText") or ""

                raw_job = {
                    "source_id": source_id,
                    "title": item.get("title"),
                    "company": name,
                    "location": loc,
                    "is_remote": "remote" in loc.lower(),
                    "url": job_url,
                    "description": f"Position: {item.get('title')} at {name}." + (f" Location: {loc}." if loc else ""),
                    "department": "",
                    "posted_at": item.get("postedOn")
                }

                norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
                if norm:
                    normalized_jobs.append(norm)

            if total_available is None:
                # Workday only reports "total" on the first page; later pages return 0
                total_available = data.get("total", 0)
            offset += limit
            if offset >= min(total_available, max_total):
                break

        logger.info(f"[Workday] Fetched {len(normalized_jobs)} jobs for {name} ({tenant})")
        return normalized_jobs

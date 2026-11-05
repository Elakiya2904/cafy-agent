"""SmartRecruiters public Posting API scraper.

Endpoint shape and the list -> detail approach are adapted from TelivityAI/careerops
(Apache-2.0, supabase/functions/run-search-mt/index.ts), reimplemented for this codebase.
"""
import logging
import concurrent.futures
from typing import List, Dict, Any, Optional
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.smartrecruiters")

API = "https://api.smartrecruiters.com/v1/companies"
PAGE_SIZE = 100
MAX_PAGES = 10          # hard stop: 1000 postings per company
DETAIL_WORKERS = 8


class SmartRecruitersScraper(BaseScraper):
    platform_name = "smartrecruiters"

    def _list_postings(self, token: str) -> List[Dict[str, Any]]:
        postings: List[Dict[str, Any]] = []
        for page in range(MAX_PAGES):
            resp = self.get(
                f"{API}/{token}/postings",
                params={"limit": PAGE_SIZE, "offset": page * PAGE_SIZE, "country": "gb"},
            )
            if not resp:
                break
            try:
                data = resp.json()
            except Exception as e:
                logger.error(f"[SmartRecruiters] Failed to parse JSON for {token}: {e}")
                break
            content = data.get("content") or []
            postings.extend(content)
            if len(content) < PAGE_SIZE or len(postings) >= int(data.get("totalFound") or 0):
                break
        return postings

    def _description(self, token: str, posting_id: str) -> str:
        """The list endpoint carries no job text; fetch it from the posting detail."""
        resp = self.get(f"{API}/{token}/postings/{posting_id}")
        if not resp:
            return ""
        try:
            sections = ((resp.json().get("jobAd") or {}).get("sections")) or {}
        except Exception:
            return ""
        order = ("companyDescription", "jobDescription", "qualifications", "additionalInformation")
        return "\n".join(
            (sections.get(k) or {}).get("text") or "" for k in order
        )

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        token = company_config.get("token", "").strip()
        name = company_config.get("name", token).strip()
        if not token:
            return []

        postings = self._list_postings(token)
        logger.info(f"[SmartRecruiters] Fetched {len(postings)} raw jobs for {name} ({token})")
        if not postings:
            return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
            descriptions = list(pool.map(lambda p: self._description(token, str(p.get("id"))), postings))

        jobs = []
        for item, desc in zip(postings, descriptions):
            loc = item.get("location") or {}
            pid = str(item.get("id") or "")
            raw_job = {
                "source_id": pid,
                "title": item.get("name"),
                "company": name,
                "location": loc.get("fullLocation") or ", ".join(
                    x for x in (loc.get("city"), loc.get("region")) if x
                ),
                "is_remote": bool(loc.get("remote")),
                "url": f"https://jobs.smartrecruiters.com/{token}/{pid}",
                "description": desc,
                "department": (item.get("department") or {}).get("label")
                or (item.get("function") or {}).get("label") or "",
                "employment_type": (item.get("typeOfEmployment") or {}).get("label") or "",
                "posted_at": item.get("releasedDate"),
            }
            norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
            if norm:
                jobs.append(norm)
        return jobs

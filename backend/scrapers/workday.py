import logging
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.workday")

class WorkdayScraper(BaseScraper):
    platform_name = "workday"

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
        max_total = 60  # Paginate up to 60 jobs per company

        while offset < max_total:
            payload = {
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": "engineer"
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
                loc = item.get("locationsText") or "United States"

                raw_job = {
                    "source_id": source_id,
                    "title": item.get("title"),
                    "company": name,
                    "location": loc,
                    "is_remote": "remote" in loc.lower(),
                    "url": job_url,
                    "description": f"Position: {item.get('title')} at {name}. Location: {loc}.",
                    "department": "Engineering & Technology",
                    "posted_at": item.get("postedOn")
                }

                norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
                if norm:
                    normalized_jobs.append(norm)

            total_available = data.get("total", 0)
            offset += limit
            if offset >= total_available:
                break

        logger.info(f"[Workday] Fetched {len(normalized_jobs)} jobs for {name} ({tenant})")
        return normalized_jobs

import logging
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.ashby")

class AshbyScraper(BaseScraper):
    platform_name = "ashby"

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        token = company_config.get("token", "").strip()
        name = company_config.get("name", token.title()).strip()
        if not token:
            return []

        url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
        resp = self.get(url)
        if not resp:
            logger.info(f"[Ashby] No response received for board '{token}'")
            return []

        try:
            data = resp.json()
        except Exception as e:
            logger.error(f"[Ashby] Failed to parse JSON for {token}: {e}")
            return []

        raw_jobs = data.get("jobs", [])
        logger.info(f"[Ashby] Fetched {len(raw_jobs)} raw jobs from board '{token}' ({name})")

        normalized_jobs = []
        for item in raw_jobs:
            loc = item.get("locationName", "")
            if not loc and item.get("address"):
                loc = item["address"].get("postalAddress", {}).get("addressLocality", "")

            raw_job = {
                "source_id": str(item.get("id")),
                "title": item.get("title"),
                "company": name,
                "location": loc or "",
                "is_remote": item.get("isRemote", False),
                "url": item.get("jobUrl") or f"https://jobs.ashbyhq.com/{token}/{item.get('id')}",
                "description": item.get("descriptionHtml") or item.get("descriptionPlain") or "",
                "department": item.get("departmentName") or "",
                "employment_type": item.get("employmentType") or "",
                "posted_at": item.get("publishedAt")
            }

            norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
            if norm:
                normalized_jobs.append(norm)

        return normalized_jobs

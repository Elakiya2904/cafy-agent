import logging
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.greenhouse")

class GreenhouseScraper(BaseScraper):
    platform_name = "greenhouse"

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        token = company_config.get("token", "").strip()
        name = company_config.get("name", token.title()).strip()
        if not token:
            return []

        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        params = {"content": "true"}

        resp = self.get(url, params=params)
        if not resp:
            logger.info(f"[Greenhouse] No response received for board '{token}'")
            return []

        try:
            data = resp.json()
        except Exception as e:
            logger.error(f"[Greenhouse] Failed to parse JSON for {token}: {e}")
            return []

        raw_jobs = data.get("jobs", [])
        logger.info(f"[Greenhouse] Fetched {len(raw_jobs)} raw jobs from board '{token}' ({name})")

        normalized_jobs = []
        for item in raw_jobs:
            departments = [d.get("name", "") for d in item.get("departments", []) if d.get("name")]
            dept_str = ", ".join(departments) if departments else "General"

            raw_job = {
                "source_id": str(item.get("id")),
                "title": item.get("title"),
                "company": name,
                "location": item.get("location", {}).get("name") if isinstance(item.get("location"), dict) else str(item.get("location") or "Remote"),
                "url": item.get("absolute_url") or f"https://boards.greenhouse.io/{token}/jobs/{item.get('id')}",
                "description": item.get("content", ""),
                "department": dept_str,
                "posted_at": item.get("updated_at")
            }

            norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
            if norm:
                normalized_jobs.append(norm)

        return normalized_jobs

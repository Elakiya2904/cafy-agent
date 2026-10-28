import logging
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.breezyhr")

class BreezyHRScraper(BaseScraper):
    platform_name = "breezyhr"

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        token = company_config.get("token", "").strip()
        name = company_config.get("name", token.title()).strip()
        if not token:
            return []

        url = f"https://{token}.breezy.hr/json"
        resp = self.get(url)
        if not resp:
            logger.info(f"[BreezyHR] No response received for company '{token}'")
            return []

        try:
            data = resp.json()
        except Exception as e:
            logger.error(f"[BreezyHR] JSON parse error for {token}: {e}")
            return []

        if not isinstance(data, list):
            return []

        logger.info(f"[BreezyHR] Fetched {len(data)} raw jobs for {name} ({token})")

        normalized_jobs = []
        for item in data:
            loc_val = item.get("location")
            if isinstance(loc_val, dict):
                loc = loc_val.get("name") or "Remote"
            else:
                loc = str(loc_val or "Remote")

            type_val = item.get("type")
            emp_type = type_val.get("name", "Full-time") if isinstance(type_val, dict) else "Full-time"
            is_remote = "remote" in loc.lower() or (isinstance(type_val, dict) and type_val.get("id") == "remote")

            raw_job = {
                "source_id": str(item.get("id")),
                "title": item.get("name"),
                "company": name,
                "location": loc,
                "is_remote": is_remote,
                "url": item.get("url") or f"https://{token}.breezy.hr/p/{item.get('id')}",
                "description": item.get("description", ""),
                "department": item.get("department") or "Engineering",
                "employment_type": emp_type,
                "posted_at": item.get("published_date")
            }

            norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
            if norm:
                normalized_jobs.append(norm)

        return normalized_jobs

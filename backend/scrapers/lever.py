import logging
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.lever")

class LeverScraper(BaseScraper):
    platform_name = "lever"

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        token = company_config.get("token", "").strip()
        name = company_config.get("name", token.title()).strip()
        if not token:
            return []

        url = f"https://api.lever.co/v0/postings/{token}"
        params = {"mode": "json", "limit": 50}

        resp = self.get(url, params=params)
        if not resp:
            logger.info(f"[Lever] No response received for company '{token}'")
            return []

        try:
            data = resp.json()
        except Exception as e:
            logger.error(f"[Lever] Failed to parse JSON for {token}: {e}")
            return []

        if not isinstance(data, list):
            return []

        logger.info(f"[Lever] Fetched {len(data)} raw jobs for {name} ({token})")

        normalized_jobs = []
        for item in data:
            cats = item.get("categories") or {}
            loc = cats.get("location") or ""
            team = cats.get("team") or ""
            commitment = cats.get("commitment") or ""
            workplace = cats.get("workplaceType") or ""

            desc = item.get("descriptionPlain") or item.get("description") or ""

            raw_job = {
                "source_id": str(item.get("id")),
                "title": item.get("text"),
                "company": name,
                "location": loc,
                "is_remote": "remote" in loc.lower() or workplace.lower() == "remote",
                "url": item.get("hostedUrl") or item.get("applyUrl") or f"https://jobs.lever.co/{token}/{item.get('id')}",
                "description": desc,
                "department": team,
                "employment_type": commitment,
                "posted_at": str(item.get("createdAt")) if item.get("createdAt") else None
            }

            norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
            if norm:
                normalized_jobs.append(norm)

        return normalized_jobs

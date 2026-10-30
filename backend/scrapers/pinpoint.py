import logging
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.pinpoint")

class PinpointScraper(BaseScraper):
    platform_name = "pinpoint"

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        token = company_config.get("token", "").strip()
        name = company_config.get("name", token.title()).strip()
        if not token:
            return []

        url = f"https://{token}.pinpointhq.com/postings.json"
        resp = self.get(url)
        if not resp:
            logger.info(f"[Pinpoint] No response received for company '{token}'")
            return []

        try:
            data = resp.json()
        except Exception as e:
            logger.error(f"[Pinpoint] JSON parse error for {token}: {e}")
            return []

        data_list = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        logger.info(f"[Pinpoint] Fetched {len(data_list)} raw jobs for {name} ({token})")

        normalized_jobs = []
        for item in data_list:
            loc_obj = item.get("location") or {}
            city = loc_obj.get("city") or loc_obj.get("name") or ""
            workplace = item.get("workplace_type") or ""
            is_remote = (
                bool(loc_obj.get("remote"))
                or "remote" in str(city).lower()
                or "remote" in str(workplace).lower()
            )

            job_data = item.get("job") or {}
            dept_obj = item.get("department") or job_data.get("department")
            dept_name = (dept_obj.get("name") or "") if isinstance(dept_obj, dict) else ""

            raw_job = {
                "source_id": str(item.get("id")),
                "title": item.get("title"),
                "company": name,
                "location": str(city),
                "is_remote": is_remote,
                "url": item.get("url") or f"https://{token}.pinpointhq.com/postings/{item.get('id')}",
                "description": item.get("description", ""),
                "department": dept_name,
                "employment_type": (
                    item.get("employment_type_text")
                    or item.get("employment_type")
                    or ""
                )
            }

            norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
            if norm:
                normalized_jobs.append(norm)

        return normalized_jobs

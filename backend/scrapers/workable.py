import logging
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.workable")

class WorkableScraper(BaseScraper):
    platform_name = "workable"

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        token = company_config.get("token", "").strip()
        name = company_config.get("name", token.title()).strip()
        if not token:
            return []

        url = f"https://apply.workable.com/api/v3/accounts/{token}/jobs"
        payload = {"query": "", "department": [], "location": [], "workplace": []}
        headers = {"Content-Type": "application/json"}

        resp = self.post(url, json=payload, headers=headers)
        raw_items = []

        if resp:
            try:
                data = resp.json()
                raw_items = data.get("results", [])
            except Exception as e:
                logger.error(f"[Workable] JSON parse error for {token}: {e}")

        # Fallback to widget endpoint if v3 returned no results
        if not raw_items:
            widget_url = f"https://apply.workable.com/api/v1/widget/accounts/{token}"
            widget_resp = self.get(widget_url)
            if widget_resp:
                try:
                    wdata = widget_resp.json()
                    raw_items = wdata.get("jobs", [])
                except Exception:
                    pass

        logger.info(f"[Workable] Fetched {len(raw_items)} raw jobs for {name} ({token})")

        normalized_jobs = []
        for item in raw_items:
            shortcode = item.get("shortcode") or item.get("id") or ""
            if not shortcode:
                continue

            loc_obj = item.get("location")
            if isinstance(loc_obj, dict):
                loc_parts = [
                    loc_obj.get(key)
                    for key in ("city", "region", "country")
                    if loc_obj.get(key)
                ]
                loc = ", ".join(loc_parts) or "Remote"
            else:
                loc = str(loc_obj or "Remote")

            if not item.get("location") and item.get("locations"):
                locations = item["locations"]
                if isinstance(locations, list) and locations:
                    loc = ", ".join(
                        part
                        for part in (
                            locations[0].get("city"),
                            locations[0].get("region"),
                            locations[0].get("country"),
                        )
                        if part
                    ) or "Remote"

            workplace = str(item.get("workplace") or "").lower()
            is_remote = (
                item.get("remote") is True
                or item.get("telecommuting") is True
                or workplace == "remote"
                or "remote" in loc.lower()
            )
            job_url = item.get("url") or f"https://apply.workable.com/{token}/j/{shortcode}/"
            department = item.get("department") or "Engineering"
            if isinstance(department, list):
                department = ", ".join(str(value) for value in department if value)
            elif isinstance(department, dict):
                department = department.get("name") or "Engineering"

            employment_type = item.get("employment_type") or item.get("type") or "Full-time"
            if employment_type == "full":
                employment_type = "Full-time"
            elif employment_type == "part":
                employment_type = "Part-time"

            raw_job = {
                "source_id": str(shortcode),
                "title": item.get("title"),
                "company": name,
                "location": loc,
                "is_remote": is_remote,
                "url": job_url,
                "description": item.get("description", ""),
                "department": department,
                "employment_type": employment_type,
                "posted_at": item.get("published") or item.get("published_on")
            }

            norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
            if norm:
                normalized_jobs.append(norm)

        return normalized_jobs

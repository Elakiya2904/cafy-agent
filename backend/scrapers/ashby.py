"""Fetch and normalize job listings from Ashby-hosted career pages.

Implements the Ashby board API adapter and converts its response into common
Cafy job records.
"""
import logging
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.ashby")


def _site_label(site: Dict[str, Any]) -> str:
    """'<location>, <country>' — labels like 'Milton Keynes Office' only reveal the country via the address."""
    label = (site.get("location") or site.get("locationName") or "").strip()
    postal = (site.get("address") or {}).get("postalAddress") or {}
    if not label:
        label = (postal.get("addressLocality") or "").strip()
    country = (postal.get("addressCountry") or "").strip()
    # Skip when the label already reads as UK ("London, UK") to avoid "London, UK, United Kingdom".
    if country and country.lower() not in label.lower() and not JobNormalizer._is_uk_site(label):
        label = f"{label}, {country}" if label else country
    return label

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
            if item.get("isListed") is False:
                continue
            # The posting API returns `location` (not `locationName`) plus `secondaryLocations`;
            # UK roles are often only listed as a secondary site (e.g. primary SF, secondary London).
            sites = [item] + [s for s in (item.get("secondaryLocations") or []) if isinstance(s, dict)]
            loc = "; ".join(dict.fromkeys(filter(None, (_site_label(s) for s in sites))))

            raw_job = {
                "source_id": str(item.get("id")),
                "title": item.get("title"),
                "company": name,
                "location": loc,
                "is_remote": item.get("isRemote", False),
                "url": item.get("jobUrl") or f"https://jobs.ashbyhq.com/{token}/{item.get('id')}",
                "description": item.get("descriptionHtml") or item.get("descriptionPlain") or "",
                "department": item.get("department") or item.get("team") or "",
                "employment_type": item.get("employmentType") or "",
                "posted_at": item.get("publishedAt")
            }

            norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
            if norm:
                normalized_jobs.append(norm)

        return normalized_jobs

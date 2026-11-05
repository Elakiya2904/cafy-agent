"""Fetch and normalize job listings from Lever-hosted boards.

Implements Lever's public postings API and maps returned vacancies to the
shared job representation.
"""
import logging
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.lever")

PAGE_SIZE = 100
MAX_PAGES = 20
# Lever's `country` is an ISO code; only UK/IE matter for the location filter.
COUNTRY_NAMES = {"GB": "United Kingdom", "UK": "United Kingdom", "IE": "Ireland"}

class LeverScraper(BaseScraper):
    platform_name = "lever"

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        token = company_config.get("token", "").strip()
        name = company_config.get("name", token.title()).strip()
        if not token:
            return []

        url = f"https://api.lever.co/v0/postings/{token}"

        # Page through the board: a single `limit=50` request silently dropped every posting past 50.
        data: List[Dict[str, Any]] = []
        for page in range(MAX_PAGES):
            resp = self.get(url, params={"mode": "json", "limit": PAGE_SIZE, "skip": page * PAGE_SIZE})
            if not resp:
                if page == 0:
                    logger.info(f"[Lever] No response received for company '{token}'")
                break
            try:
                batch = resp.json()
            except Exception as e:
                logger.error(f"[Lever] Failed to parse JSON for {token}: {e}")
                break
            if not isinstance(batch, list):
                break
            data.extend(batch)
            if len(batch) < PAGE_SIZE:
                break

        logger.info(f"[Lever] Fetched {len(data)} raw jobs for {name} ({token})")

        normalized_jobs = []
        for item in data:
            cats = item.get("categories") or {}
            # Multi-location roles list every site in allLocations; the primary may not be the UK one.
            all_locs = [l for l in (cats.get("allLocations") or []) if l] or [cats.get("location") or ""]
            loc = "; ".join(dict.fromkeys(all_locs))
            country = COUNTRY_NAMES.get((item.get("country") or "").upper())
            # `country` describes the primary site, so only attach it to single-location postings.
            if (country and len(all_locs) == 1 and country.lower() not in loc.lower()
                    and not JobNormalizer._is_uk_site(loc)):
                loc = f"{loc}, {country}" if loc else country
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

import os
import yaml
import time
import logging
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Any, Optional

from .greenhouse import GreenhouseScraper
from .ashby import AshbyScraper
from .workday import WorkdayScraper
from .lever import LeverScraper
from .workable import WorkableScraper
from .oracle_cloud import OracleCloudScraper
from .breezyhr import BreezyHRScraper
from .pinpoint import PinpointScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.manager")
SOURCES_PATH = os.path.join(os.path.dirname(__file__), "sources.yaml")

class ScraperManager:
    """
    Coordinates and monitors dynamic scraping across configured ATS platforms.
    Maintains platform instances, execution statistics, and source configurations.
    """

    def __init__(self, sources_path: str = SOURCES_PATH):
        self.sources_path = sources_path
        self.scrapers = {
            "greenhouse": GreenhouseScraper(),
            "ashby": AshbyScraper(),
            "workday": WorkdayScraper(),
            "lever": LeverScraper(),
            "workable": WorkableScraper(),
            "oracle_cloud": OracleCloudScraper(),
            "breezyhr": BreezyHRScraper(),
            "pinpoint": PinpointScraper(),
        }
        self.platforms_config = self._load_sources()
        self.health_status: Dict[str, Any] = {}
        self._init_health_status()

    def _load_sources(self) -> Dict[str, Any]:
        if not os.path.exists(self.sources_path):
            logger.warning(f"[ScraperManager] sources.yaml not found at {self.sources_path}")
            return {}
        try:
            with open(self.sources_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("platforms", {})
        except Exception as e:
            logger.error(f"[ScraperManager] Failed to load {self.sources_path}: {e}")
            return {}

    def _init_health_status(self):
        for p in self.scrapers.keys():
            self.health_status[p] = {
                "status": "never_run",
                "last_run": None,
                "jobs_collected": 0,
                "duration_seconds": 0.0,
                "last_error": None
            }

    def get_supported_platforms(self) -> List[Dict[str, Any]]:
        platforms_info = []
        for p_key, scraper in self.scrapers.items():
            cfg = self.platforms_config.get(p_key, {})
            companies = [c.get("name", c.get("token", "Company")) for c in cfg.get("companies", [])]
            health = self.health_status.get(p_key, {})
            platforms_info.append({
                "id": p_key,
                "name": cfg.get("name", p_key.replace("_", " ").title()),
                "color": cfg.get("color", "#2563EB"),
                "companies": companies,
                "companies_count": len(companies),
                "status": health.get("status", "never_run"),
                "last_run": health.get("last_run"),
                "jobs_collected": health.get("jobs_collected", 0),
                "last_error": health.get("last_error")
            })
        return platforms_info

    def scrape_platform(self, platform_name: str) -> Dict[str, Any]:
        """
        Scrapes a single platform independently.
        Never throws; records timing, success, or errors in health status.
        """
        p_key = platform_name.lower().replace("-", "_").replace(" ", "_")
        if p_key == "oraclecloud":
            p_key = "oracle_cloud"
        elif p_key == "breezy":
            p_key = "breezyhr"

        scraper = self.scrapers.get(p_key)
        if not scraper:
            return {"platform": platform_name, "jobs": [], "status": "error", "error": f"Unknown platform {platform_name}"}

        cfg = self.platforms_config.get(p_key, {})
        companies = cfg.get("companies", [])

        start_time = time.time()
        jobs: List[Dict[str, Any]] = []
        status = "success"
        error_msg = None

        logger.info(f"[ScraperManager] Starting scrape for '{p_key}' with {len(companies)} companies")

        try:
            scraped_jobs = scraper.scrape_all(companies)
            jobs = [
                job for job in scraped_jobs
                if JobNormalizer.is_uk_or_ireland_location(job.get("location", ""))
            ]
            excluded_count = len(scraped_jobs) - len(jobs)
            if excluded_count:
                logger.info(
                    f"[ScraperManager] Excluded {excluded_count} non-UK/Ireland jobs from '{p_key}'"
                )
            if not jobs and companies:
                status = "empty"
        except Exception as e:
            logger.error(f"[ScraperManager] Error scraping {p_key}: {e}")
            status = "failed"
            error_msg = str(e)

        duration = round(time.time() - start_time, 2)
        now_iso = datetime.utcnow().isoformat()

        # Update telemetry
        self.health_status[p_key] = {
            "status": status,
            "last_run": now_iso,
            "jobs_collected": len(jobs),
            "duration_seconds": duration,
            "last_error": error_msg
        }

        logger.info(f"[ScraperManager] Finished '{p_key}': {len(jobs)} jobs in {duration}s (Status: {status})")

        return {
            "platform": p_key,
            "jobs": jobs,
            "jobs_count": len(jobs),
            "duration_seconds": duration,
            "status": status,
            "error": error_msg,
            "timestamp": now_iso
        }

    def scrape_all(self, max_workers: int = 8) -> Dict[str, Any]:
        """
        Executes parallel scraping across all configured ATS platforms.
        Independent execution ensures failures on one platform don't affect others.
        """
        start_time = time.time()
        all_jobs: List[Dict[str, Any]] = []
        platform_results = {}

        logger.info(f"[ScraperManager] Executing concurrent scrape across {len(self.scrapers)} ATS platforms...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_platform = {
                executor.submit(self.scrape_platform, p_key): p_key
                for p_key in self.scrapers.keys()
            }

            for future in concurrent.futures.as_completed(future_to_platform):
                p_key = future_to_platform[future]
                try:
                    result = future.result()
                    platform_results[p_key] = result
                    all_jobs.extend(result.get("jobs", []))
                except Exception as e:
                    logger.error(f"[ScraperManager] Thread failure for {p_key}: {e}")
                    platform_results[p_key] = {
                        "platform": p_key,
                        "jobs": [],
                        "jobs_count": 0,
                        "status": "failed",
                        "error": str(e)
                    }

        total_duration = round(time.time() - start_time, 2)
        logger.info(f"[ScraperManager] Completed all platforms. Total jobs collected: {len(all_jobs)} in {total_duration}s")

        return {
            "total_jobs": len(all_jobs),
            "total_duration_seconds": total_duration,
            "jobs": all_jobs,
            "platforms": platform_results,
            "timestamp": datetime.utcnow().isoformat()
        }

    def add_company_source(self, platform: str, company_data: Dict[str, Any]) -> bool:
        p_key = platform.lower().replace("-", "_")
        if p_key not in self.scrapers:
            return False

        self.platforms_config.setdefault(p_key, {}).setdefault("companies", []).append(company_data)
        try:
            with open(self.sources_path, "w", encoding="utf-8") as f:
                yaml.safe_dump({"platforms": self.platforms_config}, f)
            return True
        except Exception as e:
            logger.error(f"[ScraperManager] Failed to persist new company to sources.yaml: {e}")
            return False

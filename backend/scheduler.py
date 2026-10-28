import time
import logging
import threading
from datetime import datetime
from typing import Optional

from .scrapers.scraper_manager import ScraperManager
from .database import JobDatabase

logger = logging.getLogger("cafy.scheduler")

class ScrapingScheduler:
    """
    Background worker that runs periodic scraping runs across configured ATS platforms,
    persists new and updated listings into the database, and records run telemetry.
    Decoupled from user résumé uploads.
    """

    def __init__(self, scraper_manager: ScraperManager, database: JobDatabase, interval_hours: float = 6.0):
        self.scraper_manager = scraper_manager
        self.database = database
        self.interval_seconds = int(interval_hours * 3600)
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        if self.is_running:
            logger.info("[Scheduler] Background worker already running.")
            return

        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ScrapingSchedulerThread")
        self._thread.start()
        logger.info(f"[Scheduler] Background worker started with interval: {self.interval_seconds // 3600}h")

    def stop(self):
        if not self.is_running:
            return
        logger.info("[Scheduler] Stopping background worker...")
        self.is_running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def run_now(self) -> dict:
        """Executes an immediate manual scrape run and stores results in DB."""
        logger.info("[Scheduler] Triggering manual full scrape...")
        started_at = datetime.utcnow().isoformat()
        start_time = time.time()

        scrape_result = self.scraper_manager.scrape_all()
        jobs = scrape_result.get("jobs", [])

        # Persist to database
        db_stats = self.database.save_or_update_jobs(jobs)

        # Record telemetry for each platform in scraper_runs
        for p_key, p_res in scrape_result.get("platforms", {}).items():
            self.database.record_scraper_run(
                platform=p_key,
                started_at=started_at,
                finished_at=datetime.utcnow().isoformat(),
                duration=p_res.get("duration_seconds", 0.0),
                jobs_found=p_res.get("jobs_count", 0),
                new_jobs=db_stats.get("new", 0),
                updated_jobs=db_stats.get("updated", 0),
                status=p_res.get("status", "unknown"),
                error_msg=p_res.get("error")
            )

        total_duration = round(time.time() - start_time, 2)
        logger.info(f"[Scheduler] Scrape run complete: {db_stats['new']} new, {db_stats['updated']} updated in {total_duration}s")
        return {
            "total_found": len(jobs),
            "new_jobs": db_stats["new"],
            "updated_jobs": db_stats["updated"],
            "duration_seconds": total_duration,
            "timestamp": started_at
        }

    def _run_loop(self):
        # Initial scrape on launch if database is empty
        stats = self.database.get_stats()
        if stats["total_active_jobs"] == 0:
            logger.info("[Scheduler] Database is empty, performing initial indexing...")
            try:
                self.run_now()
            except Exception as e:
                logger.error(f"[Scheduler] Initial indexing error: {e}")

        while not self._stop_event.is_set():
            # Wait for next interval
            interrupted = self._stop_event.wait(self.interval_seconds)
            if interrupted:
                break

            logger.info("[Scheduler] Scheduled periodic scrape triggered...")
            try:
                self.run_now()
            except Exception as e:
                logger.error(f"[Scheduler] Periodic scrape error: {e}")

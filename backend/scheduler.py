"""Schedule recurring job-board scraping and expose manual run controls.

Runs configured scraper tasks at the selected local time and reports status to
the database and API.
"""
import time
import logging
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
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

    def __init__(
        self,
        scraper_manager: ScraperManager,
        database: JobDatabase,
        schedule_hour: int = 8,
        schedule_minute: int = 0,
        schedule_timezone: str = "Europe/London",
    ):
        self.scraper_manager = scraper_manager
        self.database = database
        if not 0 <= schedule_hour <= 23:
            raise ValueError("schedule_hour must be between 0 and 23")
        if not 0 <= schedule_minute <= 59:
            raise ValueError("schedule_minute must be between 0 and 59")
        self.schedule_hour = schedule_hour
        self.schedule_minute = schedule_minute
        self.schedule_timezone = ZoneInfo(schedule_timezone)
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
        logger.info(
            "[Scheduler] Background worker started for %02d:%02d %s daily",
            self.schedule_hour,
            self.schedule_minute,
            self.schedule_timezone.key,
        )

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
        started_at = datetime.now(timezone.utc).isoformat()
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
                finished_at=datetime.now(timezone.utc).isoformat(),
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

    # How often the loop wakes to check whether a scrape is due. Short enough that a laptop
    # waking from sleep, or a backend started late, catches up within minutes.
    CHECK_INTERVAL_SECONDS = 15 * 60
    # After a run that crashed before recording anything, wait this long before trying again.
    RETRY_AFTER_FAILURE_SECONDS = 60 * 60

    def latest_slot(self, now: Optional[datetime] = None) -> datetime:
        """The most recent scheduled time that has already passed (today's, or yesterday's)."""
        local_now = (now or datetime.now(timezone.utc)).astimezone(self.schedule_timezone)
        slot = local_now.replace(hour=self.schedule_hour, minute=self.schedule_minute, second=0, microsecond=0)
        if slot > local_now:
            slot -= timedelta(days=1)
        return slot

    def next_slot(self, now: Optional[datetime] = None) -> datetime:
        return self.latest_slot(now) + timedelta(days=1)

    @staticmethod
    def _parse_time(value) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return None
        # Runs were recorded with naive UTC timestamps.
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def is_scrape_due(self, now: Optional[datetime] = None) -> bool:
        """True when no scrape has started since the most recent scheduled time.

        This makes up for missed runs: if the backend was off (or asleep) at the scheduled
        time, the scrape runs as soon as it is back instead of skipping the whole day.
        """
        last = self._parse_time(self.database.last_scrape_started_at())
        return last is None or last < self.latest_slot(now)

    def _run_loop(self):
        last_failed_attempt: Optional[datetime] = None
        logged_next: Optional[datetime] = None
        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            try:
                # A fresh database has no runs recorded, so it is due straight away too.
                due = self.is_scrape_due(now)
            except Exception as e:
                logger.error(f"[Scheduler] Could not read scrape history: {e}")
                due = False
            recently_failed = last_failed_attempt and (now - last_failed_attempt).total_seconds() < self.RETRY_AFTER_FAILURE_SECONDS
            if due and not recently_failed:
                missed = self.latest_slot(now)
                logger.info("[Scheduler] Scrape due (no run since %s); starting now.", missed.isoformat())
                try:
                    self.run_now()
                    last_failed_attempt = None
                except Exception as e:
                    last_failed_attempt = now
                    logger.error(f"[Scheduler] Scheduled scrape error: {e}")
                continue

            next_run = self.next_slot(datetime.now(timezone.utc))
            wait_seconds = (next_run.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
            if next_run != logged_next:
                logger.info("[Scheduler] Next daily scrape at %s", next_run.isoformat())
                logged_next = next_run
            if self._stop_event.wait(max(1, min(wait_seconds, self.CHECK_INTERVAL_SECONDS))):
                break

"""Background monitor for the Email Agent.

Periodically syncs every connected inbox (which classifies job emails, updates application
status and prepares interview drafts) and scans for applications that need a follow-up.
It only ever creates drafts and notifications; nothing is sent without candidate approval.
"""
import logging
import os
import threading
from typing import Dict

from .service import AgentError, EmailAgentService

logger = logging.getLogger("cafy.email_monitor")


class EmailMonitor:
    def __init__(self, service: EmailAgentService, interval_minutes: float = 0, follow_up_every: int = 12):
        self.service = service
        env_minutes = float(os.getenv("EMAIL_AGENT_POLL_MINUTES") or 5)
        self.interval_seconds = max(60.0, (interval_minutes or env_minutes) * 60)
        self.follow_up_every = max(1, follow_up_every)  # run the follow-up scan every N polls
        self.is_running = False
        self._thread = None
        self._stop = threading.Event()
        self._polls = 0

    def poll_once(self) -> Dict[str, int]:
        """One pass over all connected accounts. Failures are isolated per account."""
        stats = {"accounts": 0, "synced": 0, "failed": 0, "follow_up_drafts": 0}
        accounts = self.service.connected_accounts()
        candidates = set()
        for acc in accounts:
            stats["accounts"] += 1
            candidates.add(acc["candidate_id"])
            try:
                self.service.sync_account(acc["candidate_id"], acc["id"])
                stats["synced"] += 1
            except AgentError as err:
                stats["failed"] += 1
                logger.warning("[EmailMonitor] sync failed for %s: %s", acc["id"], err)
            except Exception:  # never let one account stop the loop
                stats["failed"] += 1
                logger.exception("[EmailMonitor] unexpected error syncing %s", acc["id"])
        if self._polls % self.follow_up_every == 0:
            for candidate in candidates:
                try:
                    stats["follow_up_drafts"] += len(self.service.scan_follow_ups(candidate))
                except Exception:
                    logger.exception("[EmailMonitor] follow-up scan failed for %s", candidate)
        self._polls += 1
        return stats

    def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="EmailMonitorThread")
        self._thread.start()
        logger.info("[EmailMonitor] started, polling every %ds", self.interval_seconds)

    def stop(self) -> None:
        if not self.is_running:
            return
        self.is_running = False
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.poll_once()
            except Exception:
                logger.exception("[EmailMonitor] poll error")

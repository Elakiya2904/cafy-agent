"""Test the daily scrape schedule, including catching up runs missed while the backend was off."""
import sys
import threading
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, ".")
from backend.scheduler import ScrapingScheduler


class FakeDb:
    def __init__(self, last=None):
        self.last = last

    def last_scrape_started_at(self):
        return self.last


def scheduler(last=None, hour=10):
    return ScrapingScheduler(scraper_manager=mock.Mock(), database=FakeDb(last), schedule_hour=hour)


# 6 Nov 2026 is GMT (UTC+0) in London, so local and UTC times match.
AT_9AM = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
AT_9PM = datetime(2026, 11, 6, 21, 24, tzinfo=timezone.utc)


class TestScrapeSchedule(unittest.TestCase):
    def test_latest_and_next_slot(self):
        s = scheduler()
        self.assertEqual(s.latest_slot(AT_9PM).isoformat(), "2026-11-06T10:00:00+00:00")
        self.assertEqual(s.latest_slot(AT_9AM).isoformat(), "2026-11-05T10:00:00+00:00")
        self.assertEqual(s.next_slot(AT_9PM).isoformat(), "2026-11-07T10:00:00+00:00")

    def test_backend_started_after_the_scheduled_time_catches_up(self):
        # Last run 4 Nov; the backend came up at 21:24 on 6 Nov, after the 10:00 slot.
        self.assertTrue(scheduler("2026-11-04T16:00:00.000001").is_scrape_due(AT_9PM))

    def test_whole_skipped_day_is_caught_up_before_the_next_slot(self):
        # At 09:00 on 6 Nov, yesterday's 10:00 run never happened: scrape now, don't wait.
        self.assertTrue(scheduler("2026-11-04T10:05:00+00:00").is_scrape_due(AT_9AM))

    def test_not_due_when_the_latest_slot_already_ran(self):
        self.assertFalse(scheduler("2026-11-06T10:00:30+00:00").is_scrape_due(AT_9PM))
        self.assertFalse(scheduler("2026-11-05T10:01:00").is_scrape_due(AT_9AM))  # naive = UTC

    def test_fresh_database_is_due(self):
        self.assertTrue(scheduler(None).is_scrape_due(AT_9PM))

    def test_loop_runs_once_when_due_then_waits(self):
        s = scheduler("2026-11-04T10:00:00+00:00")
        waits = []

        def fake_run_now():
            s.database.last = datetime.now(timezone.utc).isoformat()
            return {}

        def fake_wait(seconds):
            waits.append(seconds)
            return True  # stop after the first wait

        with mock.patch.object(s, "run_now", side_effect=fake_run_now) as run, \
             mock.patch.object(s._stop_event, "wait", side_effect=fake_wait):
            s._run_loop()
        self.assertEqual(run.call_count, 1)
        self.assertLessEqual(waits[0], ScrapingScheduler.CHECK_INTERVAL_SECONDS)

    def test_failed_run_is_not_retried_immediately(self):
        s = scheduler(None)
        calls = {"wait": 0}

        def fake_wait(seconds):
            calls["wait"] += 1
            return calls["wait"] >= 2

        with mock.patch.object(s, "run_now", side_effect=RuntimeError("network down")) as run, \
             mock.patch.object(s._stop_event, "wait", side_effect=fake_wait):
            s._run_loop()
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()

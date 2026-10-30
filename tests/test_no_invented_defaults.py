"""Guards against invented/placeholder data creeping back into parsed or scraped records."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from backend import main
from backend.resume_service import ResumeService
from backend.scrapers.job_normalizer import JobNormalizer
from backend.scrapers.scraper_manager import ScraperManager


class TestNoInventedDefaults(unittest.TestCase):

    def test_normalizer_leaves_missing_fields_empty_and_not_remote(self):
        job = JobNormalizer.normalize_job(
            {
                "source_id": "1",
                "title": "Backend Engineer",
                "company": "Acme",
                "url": "https://example.org/jobs/1",
                "description": "Build APIs in Python.",
            },
            "greenhouse",
        )
        self.assertIsNotNone(job)
        self.assertEqual(job["location"], "")
        self.assertEqual(job["employment_type"], "")
        self.assertEqual(job["department"], "")
        self.assertFalse(job["is_remote"], "An unknown location must not be treated as remote")

    def test_detect_remote_with_empty_location(self):
        self.assertFalse(JobNormalizer.detect_remote("", "Engineer", ""))

    def test_scraper_status_before_any_run_is_never_run(self):
        mgr = ScraperManager()
        platforms = mgr.get_supported_platforms()
        self.assertTrue(platforms)
        for p in platforms:
            self.assertIn("status", p)
            self.assertEqual(p["status"], "never_run")

    def test_resume_without_signals_is_not_padded(self):
        parsed = ResumeService().analyze_text(
            "Worked on python and docker projects at various places.\nSkills: Python, Docker",
            "John_Smith_Resume.pdf",
        )
        self.assertEqual(parsed["candidate_name"], "")
        self.assertEqual(parsed["target_roles"], [])
        self.assertEqual(parsed["seniority_level"], "Unknown")
        self.assertEqual(parsed["summary"], "")

    def test_profile_update_without_resume_is_rejected(self):
        saved = main.ACTIVE_SESSION.get("resume")
        main.ACTIVE_SESSION["resume"] = None
        try:
            client = TestClient(main.app)
            resp = client.post("/api/resume/update", json={"skills": ["Python"]})
            self.assertEqual(resp.status_code, 400)
            self.assertIn("Upload a résumé first", resp.json()["detail"])
        finally:
            main.ACTIVE_SESSION["resume"] = saved

    def test_sample_resume_endpoint_removed(self):
        client = TestClient(main.app)
        resp = client.post("/api/resume/sample", data={"sample_key": "fullstack"})
        self.assertIn(resp.status_code, (404, 405))


if __name__ == "__main__":
    unittest.main()

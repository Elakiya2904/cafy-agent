import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import JobDatabase

class TestJobDatabase(unittest.TestCase):

    def setUp(self):
        # Use an in-memory SQLite database or isolated test db
        import uuid
        self.test_db_path = f"file:memdb_{uuid.uuid4().hex}?mode=memory&cache=shared"
        self.db = JobDatabase(db_path=self.test_db_path)

    def test_insert_and_duplicate_prevention(self):
        job1 = {
            "id": "greenhouse_stripe_101",
            "source_job_id": "101",
            "title": "Software Engineer, Core",
            "company": "Stripe",
            "platform": "greenhouse",
            "location": "London, UK",
            "is_remote": False,
            "url": "https://boards.greenhouse.io/stripe/jobs/101",
            "description": "Initial description text.",
            "department": "Engineering",
            "employment_type": "Full-time",
            "posted_at": "2026-03-01",
            "extracted_skills": ["Python", "Go"]
        }

        # First insert
        res1 = self.db.save_or_update_jobs([job1])
        self.assertEqual(res1["new"], 1)
        self.assertEqual(res1["updated"], 0)

        # Query and verify
        jobs = self.db.get_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Software Engineer, Core")
        first_seen = jobs[0]["first_seen"]

        # Re-insert with updated description (should update, not duplicate)
        job1_updated = dict(job1)
        job1_updated["description"] = "Updated description with Kubernetes."
        job1_updated["extracted_skills"] = ["Python", "Go", "Kubernetes"]

        res2 = self.db.save_or_update_jobs([job1_updated])
        self.assertEqual(res2["new"], 0)
        self.assertEqual(res2["updated"], 1)

        # Still only 1 record in database
        jobs_after = self.db.get_jobs()
        self.assertEqual(len(jobs_after), 1)
        self.assertEqual(jobs_after[0]["description"], "Updated description with Kubernetes.")
        self.assertEqual(jobs_after[0]["first_seen"], first_seen)
        self.assertIn("Kubernetes", jobs_after[0]["extracted_skills"])

    def test_record_scraper_run(self):
        run_id = self.db.record_scraper_run(
            platform="greenhouse",
            started_at="2026-03-01T10:00:00",
            finished_at="2026-03-01T10:00:04",
            duration=4.2,
            jobs_found=25,
            new_jobs=10,
            updated_jobs=15,
            status="success"
        )
        self.assertGreater(run_id, 0)
        stats = self.db.get_stats()
        self.assertEqual(len(stats["recent_runs"]), 1)
        self.assertEqual(stats["recent_runs"][0]["platform"], "greenhouse")
        self.assertEqual(stats["recent_runs"][0]["jobs_found"], 25)

    def test_non_uk_and_ireland_jobs_are_not_stored(self):
        job = {
            "id": "greenhouse_stripe_us",
            "source_job_id": "us-1",
            "title": "Software Engineer",
            "company": "Stripe",
            "platform": "greenhouse",
            "location": "Seattle, United States",
            "url": "https://boards.greenhouse.io/stripe/jobs/us-1",
            "description": "Build software.",
            "extracted_skills": ["Python"],
        }

        result = self.db.save_or_update_jobs([job])

        self.assertEqual(result["new"], 0)
        self.assertEqual(self.db.get_jobs(), [])
        self.assertEqual(self.db.get_stats()["total_active_jobs"], 0)

if __name__ == "__main__":
    unittest.main()

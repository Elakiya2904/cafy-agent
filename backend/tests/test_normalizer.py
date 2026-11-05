import unittest
import sys
import os

# Add workspace to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scrapers.job_normalizer import JobNormalizer

class TestJobNormalizer(unittest.TestCase):

    def test_valid_job_normalization(self):
        raw = {
            "id": "1001",
            "title": "Senior Backend Engineer",
            "company": "Acme Corp",
            "location": "San Francisco, CA (Remote)",
            "url": "https://careers.acme.com/jobs/1001",
            "description": "<p>We are hiring a <strong>Python</strong> and <strong>FastAPI</strong> engineer with AWS experience.</p>",
            "department": "Infrastructure",
            "posted_at": "2026-03-01T10:00:00Z"
        }
        norm = JobNormalizer.normalize_job(raw, "greenhouse")
        self.assertIsNotNone(norm)
        self.assertEqual(norm["title"], "Senior Backend Engineer")
        self.assertEqual(norm["company"], "Acme Corp")
        self.assertEqual(norm["platform"], "greenhouse")
        self.assertTrue(norm["is_remote"])
        self.assertIn("Python", norm["extracted_skills"])
        self.assertIn("FastAPI", norm["extracted_skills"])
        self.assertIn("AWS", norm["extracted_skills"])
        self.assertEqual(norm["id"], "greenhouse_acme_corp_1001")
        # Ensure HTML stripped
        self.assertNotIn("<p>", norm["description"])
        self.assertNotIn("<strong>", norm["description"])

    def test_reject_missing_title(self):
        raw = {
            "id": "1002",
            "title": "",
            "company": "Acme Corp",
            "url": "https://careers.acme.com/jobs/1002"
        }
        self.assertIsNone(JobNormalizer.normalize_job(raw, "ashby"))

    def test_reject_missing_id(self):
        raw = {
            "title": "Software Developer",
            "company": "Acme Corp",
            "url": "https://careers.acme.com/jobs/1003"
        }
        self.assertIsNone(JobNormalizer.normalize_job(raw, "lever"))

    def test_reject_invalid_url(self):
        raw = {
            "id": "1004",
            "title": "Staff Engineer",
            "company": "Acme Corp",
            "url": "not-a-valid-url"
        }
        self.assertIsNone(JobNormalizer.normalize_job(raw, "workday"))

    def test_remote_detection(self):
        self.assertTrue(JobNormalizer.detect_remote("Remote - US", "Engineer", ""))
        self.assertTrue(JobNormalizer.detect_remote("New York, NY", "Remote Frontend Developer", ""))
        self.assertTrue(JobNormalizer.detect_remote("London, UK", "Backend Developer", "This is a 100% remote role."))
        self.assertFalse(JobNormalizer.detect_remote("Austin, TX (On-site)", "Systems Engineer", "Must work in office."))

    def test_uk_location_scope(self):
        for location in (
            "London, United Kingdom",
            "Remote - UK",
            "Belfast, Northern Ireland",
            "Derry",
            # Multi-site roles qualify when any site is in the UK.
            "London, UK / Dublin, Ireland",
            "San Francisco; London, United Kingdom",
            "US, CA, Santa Clara; UK, Reading",
            "Dublin, Ireland; London, United Kingdom",
        ):
            with self.subTest(location=location):
                self.assertTrue(JobNormalizer.is_uk_location(location))

        for location in (
            "Remote",
            "Remote - US",
            "Dublin, Ireland",
            "Dublin, Ireland; Cork",
            "New York, NY; Cambridge, MA",
            "Remote - UK and Ireland",
            "Cork",
            "Galway",
            "Limerick",
            "New York, NY",
            "1650 New Brighton Blvd, Minneapolis,MN 55413-1643",
            "Cambridge, MA",
            "Birmingham, Alabama",
            "Minneapolis, United Stat",
            "Seattle, New-York, San Francisco",
            "Toronto, Canada",
            "London, Canada",
            "",
        ):
            with self.subTest(location=location):
                self.assertFalse(JobNormalizer.is_uk_location(location))

    def test_uk_only_location_keeps_just_uk_sites(self):
        self.assertEqual(JobNormalizer.uk_only_location("San Francisco; London, United Kingdom"), "London, United Kingdom")
        self.assertEqual(JobNormalizer.uk_only_location("US, CA, Santa Clara; UK, Reading; UK, Edinburgh"), "UK, Reading; UK, Edinburgh")
        self.assertEqual(JobNormalizer.uk_only_location("New York, NY • London"), "London")
        self.assertEqual(JobNormalizer.uk_only_location("London, UK"), "London, UK")

if __name__ == "__main__":
    unittest.main()

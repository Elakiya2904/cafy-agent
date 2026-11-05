"""What the job detail panel may show: real careers pages only, UK hiring locations only."""
import unittest

import os
import tempfile

from backend.database import JobDatabase, repair_workday_url
from backend.job_intelligence.research import is_hiring_page
from backend.job_intelligence.service import uk_hiring_locations


class TestCareersPage(unittest.TestCase):
    def test_learning_education_and_product_pages_are_not_careers_pages(self):
        for url in ("https://trailhead.salesforce.com/career-path/",
                    "https://www.salesforce.com/in/education/recruitment-admissions-software/?bc=DB",
                    "https://www.salesforce.com/company/careers/university/",
                    "https://example.com/blog/how-we-hire", "https://example.com/learn/careers", ""):
            self.assertFalse(is_hiring_page(url), url)

    def test_real_careers_pages_pass(self):
        for url in ("https://careers.salesforce.com/en/", "https://monzo.com/careers", "https://example.com/jobs",
                    "https://example.com/careers/hiring-process"):
            self.assertTrue(is_hiring_page(url), url)


class TestUkHiringLocations(unittest.TestCase):
    def test_only_uk_sites_without_ats_placeholders(self):
        raw = ["4 Locations", "India - Bangalore", "United Kingdom - London", "2 Locations", "Ireland - Dublin",
               "London, United Kingdom; New York, NY", "united kingdom - london", "Edinburgh, Scotland"]
        self.assertEqual(uk_hiring_locations(raw),
                         ["United Kingdom - London", "London, United Kingdom", "Edinburgh, Scotland"])

    def test_capped(self):
        self.assertEqual(len(uk_hiring_locations([f"London Office {i}, UK" for i in range(20)])), 8)


class TestWorkdayLinkRepair(unittest.TestCase):
    OLD = "https://salesforce.wd12.myworkdayjobs.com/en-US/salesforce/External_Career_Site/job/United-Kingdom---London/AE_JR1"
    NEW = "https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site/job/United-Kingdom---London/AE_JR1"

    def test_tenant_segment_is_removed_only_when_it_matches_the_subdomain(self):
        self.assertEqual(repair_workday_url(self.OLD), self.NEW)
        self.assertEqual(repair_workday_url(self.NEW), self.NEW)
        other = "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/US-CA/X_JR2"
        self.assertEqual(repair_workday_url(other), other)
        self.assertIsNone(repair_workday_url(None))

    def test_stored_links_are_repaired_when_the_database_opens(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = os.path.join(tmp, "jobs.db")
            db = JobDatabase(db_path=path)
            db.save_or_update_jobs([{"id": "workday_x_1", "source_job_id": "1", "title": "AE", "company": "Salesforce",
                                     "platform": "workday", "location": "London, United Kingdom", "url": self.OLD}])
            JobDatabase(db_path=path)  # reopen: runs the repair
            with db._get_connection() as conn:
                self.assertEqual(conn.execute("SELECT url FROM jobs WHERE id='workday_x_1'").fetchone()["url"], self.NEW)


class TestEmploymentType(unittest.TestCase):
    def test_variants_map_to_one_label_and_non_types_are_dropped(self):
        from backend.scrapers.job_normalizer import normalize_employment_type as n
        cases = {"FullTime": "Full-time", "Full time": "Full-time", "Permanent - Full Time": "Full-time", "Permanent": "Full-time",
                 "PartTime": "Part-time", "Temporary Part-Time": "Temporary", "Fixed Term Contract": "Fixed-term",
                 "Maternity Cover": "Fixed-term", "Contract": "Contract", "Intern": "Internship",
                 "Hybrid": "", "Science": "", "Engineering": "", "Mid-Senior Level": "", "": "", None: ""}
        for raw, expected in cases.items():
            self.assertEqual(n(raw), expected, raw)


if __name__ == "__main__":
    unittest.main()

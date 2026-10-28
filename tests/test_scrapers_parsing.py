import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scrapers.greenhouse import GreenhouseScraper
from backend.scrapers.ashby import AshbyScraper
from backend.scrapers.workday import WorkdayScraper
from backend.scrapers.lever import LeverScraper
from backend.scrapers.workable import WorkableScraper
from backend.scrapers.oracle_cloud import OracleCloudScraper
from backend.scrapers.breezyhr import BreezyHRScraper
from backend.scrapers.pinpoint import PinpointScraper

class TestPlatformScrapersParsing(unittest.TestCase):

    @patch("requests.Session.get")
    def test_greenhouse_parsing(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jobs": [{
                "id": 12345,
                "title": "Software Engineer, Payments",
                "location": {"name": "Seattle, WA"},
                "departments": [{"name": "Engineering"}],
                "absolute_url": "https://boards.greenhouse.io/stripe/jobs/12345",
                "updated_at": "2026-03-01T12:00:00Z",
                "content": "<p>Build payment infrastructure with Go and Python.</p>"
            }]
        }
        mock_get.return_value = mock_resp

        scraper = GreenhouseScraper()
        jobs = scraper.scrape_company({"token": "stripe", "name": "Stripe"})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Software Engineer, Payments")
        self.assertEqual(jobs[0]["company"], "Stripe")
        self.assertEqual(jobs[0]["platform"], "greenhouse")
        self.assertIn("Go", jobs[0]["extracted_skills"])

    @patch("requests.Session.get")
    def test_ashby_parsing(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jobs": [{
                "id": "ashby-999",
                "title": "Frontend Engineer",
                "departmentName": "Product",
                "locationName": "Remote - US",
                "isRemote": True,
                "jobUrl": "https://jobs.ashbyhq.com/notion/ashby-999",
                "publishedAt": "2026-03-02",
                "descriptionHtml": "<div>React and TypeScript application</div>"
            }]
        }
        mock_get.return_value = mock_resp

        scraper = AshbyScraper()
        jobs = scraper.scrape_company({"token": "notion", "name": "Notion"})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["platform"], "ashby")
        self.assertTrue(jobs[0]["is_remote"])
        self.assertIn("React", jobs[0]["extracted_skills"])

    @patch("requests.Session.post")
    def test_workday_parsing(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "total": 1,
            "jobPostings": [{
                "title": "AI Cloud Infrastructure Engineer",
                "externalPath": "/job/JR19000",
                "locationsText": "Austin, TX (Remote)",
                "postedOn": "Posted 2 Days Ago"
            }]
        }
        mock_post.return_value = mock_resp

        scraper = WorkdayScraper()
        jobs = scraper.scrape_company({"tenant": "nvidia", "name": "NVIDIA", "host": "nvidia.wd5.myworkdayjobs.com", "site": "External"})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["platform"], "workday")
        self.assertEqual(jobs[0]["company"], "NVIDIA")
        self.assertIn("AI", jobs[0]["title"])

    @patch("requests.Session.get")
    def test_lever_parsing(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{
            "id": "lever-111",
            "text": "Site Reliability Engineer",
            "categories": {"location": "San Francisco, CA", "team": "Infrastructure", "commitment": "Full-time", "workplaceType": "remote"},
            "descriptionPlain": "Kubernetes and Docker cluster operations on AWS.",
                "hostedUrl": "https://jobs.lever.co/spotify/lever-111",
            "createdAt": 1700000000000
        }]
        mock_get.return_value = mock_resp

        scraper = LeverScraper()
        jobs = scraper.scrape_company({"token": "spotify", "name": "Spotify"})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["platform"], "lever")
        self.assertTrue(jobs[0]["is_remote"])
        self.assertIn("Kubernetes", jobs[0]["extracted_skills"])

    @patch("requests.Session.post")
    def test_workable_parsing(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [{
                "id": 6201643,
                "title": "Full Stack Engineer",
                "shortcode": "WK123",
                "department": ["Engineering", "Product"],
                "location": {"city": "London", "region": "England", "country": "UK"},
                "remote": True,
                "type": "full",
                "url": "https://apply.workable.com/j/WK123",
                "published": "2026-03-01T00:00:00Z"
            }]
        }
        mock_post.return_value = mock_resp

        scraper = WorkableScraper()
        jobs = scraper.scrape_company({"token": "typeform", "name": "Typeform"})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["platform"], "workable")
        self.assertEqual(jobs[0]["department"], "Engineering, Product")
        self.assertEqual(jobs[0]["employment_type"], "Full-time")
        self.assertEqual(jobs[0]["location"], "London, England, UK")
        self.assertTrue(jobs[0]["is_remote"])
        self.assertEqual(jobs[0]["url"], "https://apply.workable.com/j/WK123")
        self.assertEqual(jobs[0]["posted_at"], "2026-03-01T00:00:00Z")

    @patch("requests.Session.get")
    def test_oracle_cloud_parsing(self, mock_get):
        first_page = MagicMock()
        first_page.status_code = 200
        first_page.json.return_value = {
            "items": [{
                "TotalJobsCount": 2,
                "requisitionList": [{
                    "Id": "98765",
                    "Title": "Principal Cloud Architect",
                    "PrimaryLocation": "Redwood City, CA",
                    "ShortDescriptionStr": "Architecting OCI cloud infrastructure with Terraform and Linux.",
                    "PostedDate": "2026-03-01",
                    "WorkplaceType": "Remote"
                }]
            }]
        }
        second_page = MagicMock()
        second_page.status_code = 200
        second_page.json.return_value = {
            "items": [{
                "TotalJobsCount": 2,
                "requisitionList": [{
                    "Id": "98766",
                    "Title": "Cloud Software Engineer",
                    "PrimaryLocation": "Austin, TX",
                    "ShortDescriptionStr": "Building cloud services with Python."
                }]
            }]
        }
        mock_get.side_effect = [first_page, second_page]

        scraper = OracleCloudScraper()
        jobs = scraper.scrape_company({
            "token": "oracle",
            "name": "Oracle",
            "host": "oracle.cloud.com",
            "site_id": "CX_45001",
            "careers_url": "https://careers.oracle.com/en/sites/jobsearch"
        })
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["platform"], "oracle_cloud")
        self.assertTrue(jobs[0]["is_remote"])
        self.assertIn("Terraform", jobs[0]["extracted_skills"])
        self.assertEqual(jobs[0]["url"], "https://careers.oracle.com/en/sites/jobsearch/job/98765")
        self.assertEqual(mock_get.call_count, 2)
        self.assertIn("offset=1", mock_get.call_args.kwargs["params"]["finder"])

    @patch("requests.Session.get")
    def test_breezyhr_parsing(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{
            "id": "brz-55",
            "name": "Backend Python Developer",
            "department": "Core Platform",
            "type": {"name": "Full-time", "id": "remote"},
            "location": {"name": "Remote"},
            "url": "https://duo.breezy.hr/p/brz-55",
            "description": "FastAPI, PostgreSQL, and Redis caching.",
            "published_date": "2026-03-01"
        }]
        mock_get.return_value = mock_resp

        scraper = BreezyHRScraper()
        jobs = scraper.scrape_company({"token": "duo", "name": "Duo Security"})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["platform"], "breezyhr")
        self.assertIn("FastAPI", jobs[0]["extracted_skills"])
        self.assertEqual(jobs[0]["posted_at"], "2026-03-01")

    @patch("requests.Session.get")
    def test_pinpoint_parsing(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [{
                "id": 888,
                "title": "Data Engineer",
                "department": {"name": "Data Analytics"},
                "location": {"city": "New York", "remote": True},
                "url": "https://cleo.pinpointhq.com/postings/888",
                "description": "SQL, Apache Airflow, Snowflake pipelines.",
                "employment_type": "permanent_full_time",
                "employment_type_text": "Permanent - Full Time",
                "workplace_type": "remote",
                "job": {"department": {"name": "Data Analytics"}}
            }]
        }
        mock_get.return_value = mock_resp

        scraper = PinpointScraper()
        jobs = scraper.scrape_company({"token": "cleo", "name": "Cleo"})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["platform"], "pinpoint")
        self.assertIn("Snowflake", jobs[0]["extracted_skills"])
        self.assertEqual(jobs[0]["department"], "Data Analytics")
        self.assertEqual(jobs[0]["employment_type"], "Permanent - Full Time")
        self.assertTrue(jobs[0]["is_remote"])

if __name__ == "__main__":
    unittest.main()

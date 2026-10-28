import unittest
from unittest.mock import patch, MagicMock
import requests
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

class TestNoSyntheticFallbacks(unittest.TestCase):
    """
    Verifies that when third-party ATS platforms fail, time out, or return empty sets,
    the scrapers return an EMPTY list and NEVER generate synthetic/mock/seed vacancies.
    """

    def setUp(self):
        self.scrapers = [
            GreenhouseScraper(),
            AshbyScraper(),
            WorkdayScraper(),
            LeverScraper(),
            WorkableScraper(),
            OracleCloudScraper(),
            BreezyHRScraper(),
            PinpointScraper()
        ]

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_http_404_returns_empty_list(self, mock_post, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp)
        mock_resp.text = ""
        mock_get.return_value = mock_resp
        mock_post.return_value = mock_resp

        for scraper in self.scrapers:
            cfg = {"token": "nonexistent_co", "name": "FakeCo", "tenant": "fake_tenant", "host": "fake.host"}
            results = scraper.scrape_company(cfg)
            self.assertEqual(
                results, [],
                f"Platform '{scraper.platform_name}' must return empty list on 404, but returned {len(results)} items!"
            )

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_timeout_returns_empty_list(self, mock_post, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        for scraper in self.scrapers:
            cfg = {"token": "timeout_co", "name": "TimeoutCo", "tenant": "timeout_tenant", "host": "timeout.host"}
            results = scraper.scrape_company(cfg)
            self.assertEqual(
                results, [],
                f"Platform '{scraper.platform_name}' must return empty list on timeout, but returned {len(results)} items!"
            )

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_empty_json_response_returns_empty_list(self, mock_post, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"jobs": [], "jobPostings": [], "results": [], "items": [], "data": []}
        mock_get.return_value = mock_resp
        mock_post.return_value = mock_resp

        for scraper in self.scrapers:
            cfg = {"token": "empty_co", "name": "EmptyCo", "tenant": "empty_tenant", "host": "empty.host"}
            results = scraper.scrape_company(cfg)
            self.assertEqual(
                results, [],
                f"Platform '{scraper.platform_name}' must return empty list when source has no jobs!"
            )

    def test_no_synthetic_helper_method_in_scrapers(self):
        """Ensures deprecated fallback generator methods were completely deleted."""
        for scraper in self.scrapers:
            self.assertFalse(
                hasattr(scraper, "_get_fallback_jobs"),
                f"Scraper '{scraper.platform_name}' still has '_get_fallback_jobs' method! Must be removed."
            )

if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import Mock

from backend.scrapers.scraper_manager import ScraperManager


class TestScraperManagerLocationScope(unittest.TestCase):

    def test_scrape_platform_keeps_only_uk_and_ireland_jobs(self):
        manager = ScraperManager()
        manager.platforms_config = {"greenhouse": {"companies": [{"name": "Example"}]}}
        manager.scrapers["greenhouse"] = Mock()
        manager.scrapers["greenhouse"].scrape_all.return_value = [
            {"id": "uk", "location": "London, UK"},
            {"id": "ireland", "location": "Dublin, Ireland"},
            {"id": "us", "location": "New York, United States"},
            {"id": "unknown", "location": "Remote"},
        ]

        result = manager.scrape_platform("greenhouse")

        self.assertEqual([job["id"] for job in result["jobs"]], ["uk", "ireland"])
        self.assertEqual(result["jobs_count"], 2)


if __name__ == "__main__":
    unittest.main()

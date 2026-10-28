import unittest
from unittest.mock import MagicMock, patch

from backend.scrapers.workable import WorkableScraper


class TestWorkableScraper(unittest.TestCase):

    @patch("requests.Session.post")
    def test_v3_payload_normalizes_department_lists(self, mock_post):
        response = MagicMock()
        response.json.return_value = {
            "results": [{
                "id": 6201643,
                "shortcode": "WK123",
                "title": "Account Manager",
                "department": ["Revenue", "Sales"],
                "location": {"city": "Toronto", "country": "Canada"},
                "remote": False,
                "type": "full",
                "url": "https://apply.workable.com/j/WK123",
                "published": "2026-10-15T00:00:00Z"
            }]
        }
        mock_post.return_value = response

        jobs = WorkableScraper().scrape_company({
            "token": "cloudtalk",
            "name": "Cloudtalk"
        })

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["department"], "Revenue, Sales")
        self.assertEqual(jobs[0]["employment_type"], "Full-time")
        self.assertEqual(jobs[0]["location"], "Toronto, Canada")
        self.assertEqual(jobs[0]["url"], "https://apply.workable.com/j/WK123")
        self.assertEqual(jobs[0]["posted_at"], "2026-10-15T00:00:00Z")


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from pathlib import Path
from unittest import mock

from backend.resume_generation_service import ResumeGenerationError, ResumeGenerationService

RESUME = {
    "experience": [{"title": "Backend Engineer", "organization": "Acme", "dates": "2021 - 2024", "bullets": ["Built billing API"]}],
    "education": [{"degree": "BSc Computer Science", "institution": "UCD"}],
    "skills": ["Python", "SQL"],
}


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"choices": [{"message": {"content": "Backend engineer with Python and SQL experience."}}]}


class TestRewriteSectionDraft(unittest.TestCase):
    def setUp(self):
        self.service = ResumeGenerationService(Path(__file__).resolve().parent.parent)
        patcher = mock.patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_empty_summary_is_drafted_from_existing_resume_facts(self):
        with mock.patch("backend.resume_generation_service.requests.post", return_value=FakeResponse()) as post:
            out = self.service.rewrite_section("professional_summary", "  ", {"title": "Engineer"}, RESUME)
        self.assertIn("Python", out)
        sent = post.call_args.kwargs["json"]["messages"]
        self.assertIn("ONLY the facts provided", sent[0]["content"])
        self.assertIn("Backend Engineer, Acme", sent[1]["content"])
        self.assertIn("Skills: Python, SQL", sent[1]["content"])

    def test_empty_summary_with_no_resume_facts_is_refused(self):
        with mock.patch("backend.resume_generation_service.requests.post") as post:
            with self.assertRaises(ResumeGenerationError):
                self.service.rewrite_section("professional_summary", "", {}, {})
        post.assert_not_called()

    def test_empty_bullet_is_never_invented(self):
        with mock.patch("backend.resume_generation_service.requests.post") as post:
            with self.assertRaisesRegex(ResumeGenerationError, "rough first draft"):
                self.service.rewrite_section("bullet", "", {}, RESUME)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

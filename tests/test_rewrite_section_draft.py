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
            out = self.service.rewrite_section(
                "professional_summary",
                "  ",
                {"title": "Engineer", "description": "Python role", "extracted_skills": ["Python"]},
                RESUME,
                improvement_goals=["Mention the target role where supported."],
            )
        self.assertIn("Python", out)
        sent = post.call_args.kwargs["json"]["messages"]
        self.assertIn("ONLY the facts provided", sent[0]["content"])
        self.assertIn('"title": "Engineer"', sent[1]["content"])
        self.assertIn('"skills_from_job_listing": ["Python"]', sent[1]["content"])
        self.assertIn('"score_improvement_goals": ["Mention the target role where supported."]', sent[1]["content"])
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

    def test_gpt_oss_section_rewrite_uses_supported_parameters(self):
        with mock.patch.dict(os.environ, {"GROQ_MODEL": "openai/gpt-oss-20b"}), \
             mock.patch("backend.resume_generation_service.requests.post", return_value=FakeResponse()) as post:
            self.service.rewrite_section(
                "professional_summary",
                "Backend engineer with Python and SQL experience.",
                {"title": "Engineer"},
                RESUME,
            )

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["temperature"], 1)
        self.assertEqual(payload["max_completion_tokens"], 1000)
        self.assertNotIn("max_tokens", payload)

    def test_section_rewrite_includes_provider_error_without_leaking_api_key(self):
        response = mock.Mock(status_code=400)
        response.json.return_value = {
            "error": {"message": "Bad request for test-key"}
        }

        with mock.patch("backend.resume_generation_service.requests.post", return_value=response):
            with self.assertRaisesRegex(ResumeGenerationError, "Bad request for \\[redacted\\]"):
                self.service.rewrite_section(
                    "professional_summary",
                    "Backend engineer with Python and SQL experience.",
                    {"title": "Engineer"},
                    RESUME,
                )


if __name__ == "__main__":
    unittest.main()

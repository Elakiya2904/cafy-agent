import os
import unittest
from unittest.mock import MagicMock, patch

from backend.career_chat_service import (
    CareerChatError,
    CareerChatService,
    build_career_context,
)


class TestCareerChatService(unittest.TestCase):
    def setUp(self):
        self.resume = {
            "skills": ["Python", "SQL", "PyTorch"],
            "target_roles": ["AI Engineer"],
            "seniority_level": "Junior / Entry",
            "years_of_experience": 1,
        }
        self.jobs = [
            {
                "id": "ai-uk",
                "title": "Junior AI Engineer",
                "company": "Example AI",
                "location": "London, United Kingdom",
                "url": "https://jobs.example.com/ai-uk",
                "department": "Engineering",
                "employment_type": "Full-time",
                "extracted_skills": ["Python", "SQL", "PyTorch", "AWS"],
                "description": "Graduate role using Python, SQL, PyTorch, and AWS.",
                "visa_sponsored": True,
                "visa_sponsor_registered_names": ["Example AI Limited"],
            },
            {
                "id": "ai-us",
                "title": "AI Engineer",
                "company": "Other AI",
                "location": "Austin, TX",
                "url": "https://jobs.example.com/ai-us",
                "department": "Engineering",
                "employment_type": "Full-time",
                "extracted_skills": ["Python", "PyTorch"],
                "description": "Build machine learning systems.",
                "visa_sponsored": False,
                "visa_sponsor_registered_names": [],
            },
            {
                "id": "data-uk",
                "title": "Graduate Data Analyst",
                "company": "Data Co",
                "location": "London, United Kingdom",
                "url": "https://jobs.example.com/data-uk",
                "department": "Data",
                "employment_type": "Full-time",
                "extracted_skills": ["Python", "SQL"],
                "description": "Graduate role analyzing data.",
                "visa_sponsored": False,
                "visa_sponsor_registered_names": [],
            },
        ]

    def test_market_filters_retrieve_matching_jobs_only(self):
        context, cards, intent = build_career_context(
            "What entry-level AI jobs are available in the UK?",
            "market",
            self.resume,
            self.jobs,
            [],
            [],
        )

        self.assertIn("ai-uk", [job["id"] for job in cards])
        self.assertEqual(intent, "market")

    def test_progress_context_discloses_tracked_count(self):
        context, cards, intent = build_career_context(
            "How many roles have I saved?",
            "progress",
            self.resume,
            self.jobs,
            [],
            ["ai-uk"],
        )

        self.assertEqual(context["database_summary"]["tracked_pipeline_count"], 1)
        self.assertEqual(intent, "progress")

    def test_context_does_not_infer_sponsor_status(self):
        jobs = [dict(job) for job in self.jobs]
        jobs[0]["visa_sponsored"] = False
        context, cards, _ = build_career_context(
            "Tell me about this job",
            "opportunities",
            self.resume,
            jobs,
            [],
            [],
            "ai-uk",
        )

        self.assertFalse(cards[0]["visa_sponsored"])

    def test_groq_request_uses_server_key_and_evidence(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "Review the verified match evidence."}}]
        }
        cards = [{"title": "AI Engineer", "company": "Example AI", "match_score": 89}]
        context = {"database_summary": {"total_active_jobs": 1}}
        with patch.dict(os.environ, {"groq_api_key": "test-server-key"}), patch(
            "backend.career_chat_service.requests.post", return_value=response
        ) as post:
            answer = CareerChatService().answer("Which job fits?", "opportunities", context, cards, "strategy")

        self.assertEqual(answer, "Review the verified match evidence.")
        request = post.call_args.kwargs
        self.assertEqual(request["headers"]["Authorization"], "Bearer test-server-key")
        self.assertIn("Example AI", request["json"]["messages"][-1]["content"])

    def test_missing_groq_key_returns_deterministic_fallback(self):
        with patch.dict(os.environ, {"groq_api_key": "", "GROQ_API_KEY": ""}, clear=True), patch(
            "backend.career_chat_service.requests.post"
        ) as post:
            cards = [{"title": "AI Engineer", "company": "Example AI", "match_score": 89}]
            answer = CareerChatService().answer("Which jobs should I apply to?", "opportunities", {}, cards, "strategy")
        post.assert_not_called()
        self.assertIn("recommend you apply", answer)


if __name__ == "__main__":
    unittest.main()

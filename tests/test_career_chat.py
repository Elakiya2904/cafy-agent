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

    def test_strategy_does_not_recommend_unmatched_jobs_without_a_resume(self):
        _, cards, _ = build_career_context(
            "Which jobs should I prioritise this week?",
            "opportunities",
            None,
            self.jobs,
            [],
            [],
        )

        self.assertEqual(cards, [])

    def test_unmatched_listing_has_no_invented_score_or_resume_gaps(self):
        context, cards, _ = build_career_context(
            "What graduate roles are available?",
            "market",
            None,
            self.jobs,
            [],
            [],
        )

        self.assertTrue(cards)
        self.assertIsNone(cards[0]["match_score"])
        self.assertEqual(cards[0]["recommendation"], "Not scored")
        self.assertFalse(any("resume" in bullet.casefold() for bullet in cards[0]["bullets"]))
        self.assertEqual(context["top_skill_gaps"], [])

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

    def test_missing_groq_key_returns_configuration_error(self):
        with patch.dict(os.environ, {"groq_api_key": "", "GROQ_API_KEY": ""}, clear=True), patch(
            "backend.career_chat_service.requests.post"
        ) as post:
            cards = [{"title": "AI Engineer", "company": "Example AI", "match_score": 89}]
            with self.assertRaisesRegex(CareerChatError, "not configured"):
                CareerChatService().answer("Which jobs should I apply to?", "opportunities", {}, cards, "strategy")
        post.assert_not_called()

    def test_groq_http_error_does_not_return_a_fallback(self):
        response = MagicMock(status_code=401)
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-server-key"}), patch(
            "backend.career_chat_service.requests.post", return_value=response
        ):
            with self.assertRaisesRegex(CareerChatError, "could not complete"):
                CareerChatService().answer("Which job fits?", "opportunities", {}, [], "strategy")

    def test_invalid_groq_response_does_not_return_a_fallback(self):
        response = MagicMock(status_code=200)
        response.json.side_effect = ValueError("invalid json")
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-server-key"}), patch(
            "backend.career_chat_service.requests.post", return_value=response
        ):
            with self.assertRaisesRegex(CareerChatError, "invalid response"):
                CareerChatService().answer("Which job fits?", "opportunities", {}, [], "strategy")


if __name__ == "__main__":
    unittest.main()

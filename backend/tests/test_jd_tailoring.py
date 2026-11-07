"""Tailored resume generation for one selected job: automatic, job-description-driven, truthful."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, ".")

from backend.resume_generation_service import ResumeGenerationService
from backend.resume_service import ResumeService
from backend.resume_structure import standardize_dates
from backend.tests.test_resume_tailoring_e2e import GRADUATE_RESUME, PROJECT_ROOT, TRADING_JOB, parse

DATA_JOB = {
    "id": "job-data",
    "title": "Junior Data Analyst",
    "company": "Example Retail",
    "description": (
        "<p><strong>Essential</strong></p><ul><li>SQL and Excel</li><li>Python for analysis</li>"
        "<li>Tableau</li></ul><p><strong>Desirable</strong></p><ul><li>VBA</li><li>Power BI</li></ul>"
    ),
}


class TestAutomaticJobTailoring(unittest.TestCase):
    def setUp(self):
        self.service = ResumeGenerationService(PROJECT_ROOT)
        self.profile = parse(GRADUATE_RESUME)

    def generate(self, job):
        # No AI key: generation must still finish on its own (no human step, no error).
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "", "groq_api_key": ""}):
            return self.service.generate(self.profile, job, skill_extractor=ResumeService())

    def test_finishes_without_ai_and_says_how_it_was_tailored(self):
        result = self.generate(DATA_JOB)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["validation"]["tailoring_mode"], "rules")
        self.assertIn("not configured", result["validation"]["ai_error"])

    def test_about_me_targets_the_selected_job_with_verified_facts(self):
        about = self.generate(DATA_JOB)["resume"]["professional_summary"]
        self.assertIn("Junior Data Analyst role at Example Retail", about)
        self.assertIn("BSc Economics and Finance", about)
        self.assertIn("2 internships at Barclays and HSBC", about)
        self.assertIn("Hands-on experience with", about)
        for word in ("SQL", "Excel", "Python"):
            self.assertIn(word, about)
        # Never claimed: not on the resume.
        self.assertNotIn("Tableau", about)
        self.assertNotIn("Power BI", about)
        self.assertNotIn("years of full-time experience", about)  # a graduate, not experienced

    def test_keywords_only_when_the_resume_shows_them(self):
        result = self.generate(DATA_JOB)
        skills = result["resume"]["skills"]
        for proven in ("SQL", "Excel", "Python", "VBA"):
            self.assertIn(proven, skills)
        for unproven in ("Tableau", "Power BI"):
            self.assertNotIn(unproven, skills)
        self.assertIn("Tableau", result["validation"]["essential_requirements_not_claimed"])
        # Essential job skills lead the Skills section.
        self.assertEqual(set(skills[:3]), {"SQL", "Excel", "Python"})

    def test_education_and_facts_copied_unchanged(self):
        resume = self.generate(DATA_JOB)["resume"]
        self.assertEqual([e.get("degree") or e.get("title") for e in resume["education"]], ["BSc Economics and Finance"])
        self.assertEqual([e["title"] for e in resume["internships"]], ["Trade Support Intern", "Operations Intern"])
        self.assertEqual([e["dates"] for e in resume["internships"]],
                         [standardize_dates(e["dates"]) for e in self.profile["internships"]])

    def test_most_relevant_bullet_first(self):
        resume = self.generate(DATA_JOB)["resume"]
        barclays = resume["internships"][0]
        self.assertIn("Excel and SQL", barclays["bullets"][0])
        self.assertEqual(sorted(barclays["bullets"]), sorted(self.profile["internships"][0]["bullets"]))

    def test_different_jobs_get_different_resumes(self):
        data = self.generate(DATA_JOB)["resume"]
        trading = self.generate(TRADING_JOB)["resume"]
        self.assertNotEqual(data["professional_summary"], trading["professional_summary"])
        self.assertIn("Graduate Trading Operations Analyst", trading["professional_summary"])

    def test_scores_the_tailored_resume_against_the_job(self):
        scores = self.generate(DATA_JOB)["generation_scores"]
        self.assertIn("jd_match_score", scores)
        self.assertEqual(scores["jd_match"]["method"], "requirement-coverage-v1")


if __name__ == "__main__":
    unittest.main()

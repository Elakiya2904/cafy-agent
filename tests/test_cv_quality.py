import unittest

from backend.cv_quality_service import evaluate_cv_quality


class TestCvQuality(unittest.TestCase):
    def test_quality_checks_are_transparent_and_exclude_empty_optional_sections(self):
        profile = {
            "candidate_name": "A. Candidate",
            "email": "candidate@example.com",
            "summary": "A concise profile.",
            "skills": ["Python", "SQL"],
            "experience": [{
                "title": "Engineer",
                "company": "Example Ltd",
                "dates": "2022-Present",
                "bullets": ["Developed a service used by 20 teams."],
            }],
            "education": [],
            "projects": [],
            "certifications": [],
        }

        result = evaluate_cv_quality(profile)

        self.assertEqual(result["score"], 100)
        self.assertEqual(result["passed_checks"], result["total_checks"])
        self.assertIn("layout", result["scope"])
        self.assertNotIn("education_details", {check["key"] for check in result["checks"]})
        self.assertNotIn("project_details", {check["key"] for check in result["checks"]})
        self.assertNotIn("certification_details", {check["key"] for check in result["checks"]})

    def test_missing_content_lowers_score_with_actionable_checks(self):
        result = evaluate_cv_quality({
            "candidate_name": "Candidate",
            "email": "not-an-email",
            "skills": [],
            "experience": [{"title": "Engineer", "company": "Example", "dates": "2022"}],
            "education": [{"degree": "", "institution": "Example University"}],
            "projects": [{"title": "Tool", "description": ""}],
            "certifications": [{"name": "Cloud Certificate", "issuer": ""}],
        })

        checks = {check["key"]: check for check in result["checks"]}
        self.assertLess(result["score"], 100)
        self.assertFalse(checks["contact_details"]["passed"])
        self.assertFalse(checks["profile_summary"]["passed"])
        self.assertFalse(checks["education_details"]["passed"])
        self.assertFalse(checks["project_details"]["passed"])
        self.assertFalse(checks["certification_details"]["passed"])
        self.assertTrue(all(check["advice"] for check in checks.values() if not check["passed"]))

    def test_job_analysis_returns_cv_quality_separately_from_match(self):
        from backend.job_match_analysis_service import analyze_profile_for_job

        result = analyze_profile_for_job(
            {"candidate_name": "Candidate", "email": "candidate@example.com"},
            {"title": "Engineer", "description": "Python required"},
        )

        self.assertIn("cv_quality", result)
        self.assertIn("job_match_score", result)
        self.assertIn("score", result["cv_quality"])


if __name__ == "__main__":
    unittest.main()

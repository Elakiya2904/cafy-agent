"""Test job recommendation ranking, filtering, and match evidence.

Uses representative profiles and vacancies to validate ordering and reported
skill, role, and location signals.
"""
import copy
import sys
import unittest

sys.path.insert(0, ".")

from backend.recommendation_service import RecommendationService


PROFILE = {
    "candidate_name": "Candidate",
    "summary": "DevOps engineer with 6 years running Kubernetes on AWS.",
    "skills": ["AWS", "Kubernetes", "Docker", "Terraform", "Python"],
    "years_of_experience": 6,
    "experience": [{
        "title": "DevOps Engineer",
        "company": "Example",
        "dates": "2019 - 2025",
        "bullets": [
            "Managed Kubernetes clusters on AWS with Terraform",
            "Reduced deployment time by 40% using Python automation",
        ],
    }],
    "education": [{"degree": "BSc Computer Science", "institution": "UCL", "dates": "2018"}],
    "projects": [{"title": "Platform automation", "bullets": ["Automated AWS deployments with Python"]}],
    "certifications": [],
}

JOB = {
    "id": "job-1",
    "title": "DevOps Engineer",
    "company": "Example",
    "extracted_skills": ["AWS", "Kubernetes", "Terraform", "Docker", "Python"],
    "description": (
        "We need 5+ years of experience with AWS, Kubernetes, Terraform, Docker and Python. "
        "Bachelor's degree in Computer Science."
    ),
}


class TestRecommendations(unittest.TestCase):
    def setUp(self):
        self.service = RecommendationService()

    def test_card_score_uses_legacy_high_confidence_range(self):
        recommendation = self.service.recommend_jobs(PROFILE, [JOB], min_score=0)[0]

        self.assertGreaterEqual(recommendation["match_score"], 85)
        self.assertLessEqual(recommendation["match_score"], 98)
        self.assertEqual(recommendation["fit_level"], "Exceptional Match")
        self.assertEqual(recommendation["matched_skills"], JOB["extracted_skills"])
        self.assertEqual(recommendation["missing_skills"], [])

    def test_minimum_score_filters_legacy_card_score(self):
        score = self.service.recommend_jobs(PROFILE, [JOB], min_score=0)[0]["match_score"]
        self.assertTrue(self.service.recommend_jobs(PROFILE, [JOB], min_score=score))
        self.assertEqual(
            self.service.recommend_jobs(PROFILE, [JOB], min_score=score + 1),
            [],
        )

    def test_different_jobs_get_different_scores_for_same_resume(self):
        unrelated_job = {
            "id": "job-2",
            "title": "Cloud Data Engineer",
            "description": "Requires AWS, Kubernetes, Docker, Python and PostgreSQL.",
            "extracted_skills": ["AWS", "Kubernetes", "Docker", "Python", "PostgreSQL"],
        }
        scores = {
            item["id"]: item["match_score"]
            for item in self.service.recommend_jobs(PROFILE, [JOB, unrelated_job], min_score=0)
        }

        self.assertGreaterEqual(scores["job-1"], 85)
        # job-2 requires PostgreSQL, which the resume does not show: a missing essential skill
        # keeps it out of the top band.
        self.assertLess(scores["job-2"], 85)
        self.assertGreater(scores["job-1"], scores["job-2"])

    def test_skill_overlap_changes_the_legacy_card_score(self):
        before_profile = copy.deepcopy(PROFILE)
        before_profile["skills"].remove("Terraform")
        # Skills are read from the whole resume, so the skill must leave the bullets too.
        before_profile["experience"][0]["bullets"][0] = "Managed Kubernetes clusters on AWS"

        before = self.service.recommend_jobs(before_profile, [JOB], min_score=0)[0]["match_score"]
        after = self.service.recommend_jobs(PROFILE, [JOB], min_score=0)[0]["match_score"]

        self.assertLess(before, after)

    def test_experience_filter_and_threshold_zero(self):
        matching = dict(JOB, id="matching", description="Requires 5-7 years of experience with AWS, Kubernetes, Terraform, Docker and Python.")
        too_senior = dict(JOB, id="too-senior", description="Requires 8+ years of experience with AWS, Kubernetes, Terraform, Docker and Python.")

        recommendations = self.service.recommend_jobs(PROFILE, [matching, too_senior], min_score=0)

        self.assertEqual([item["id"] for item in recommendations], ["matching"])

    def test_platform_filter_and_empty_jobs(self):
        greenhouse_job = dict(JOB, platform="greenhouse")
        lever_job = dict(JOB, id="lever", platform="lever")

        recommendations = self.service.recommend_jobs(
            PROFILE, [greenhouse_job, lever_job], min_score=0, platform_filter="greenhouse"
        )

        self.assertEqual([item["id"] for item in recommendations], ["job-1"])
        self.assertEqual(self.service.recommend_jobs(PROFILE, []), [])

    def test_missing_resume_does_not_create_recommendations(self):
        self.assertEqual(self.service.recommend_jobs({}, [JOB], min_score=0), [])


if __name__ == "__main__":
    unittest.main()

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.resume_service import ResumeService
from backend.recommendation_service import RecommendationService

class TestRecommendations(unittest.TestCase):

    def setUp(self):
        self.resume_svc = ResumeService()
        self.rec_svc = RecommendationService()

    def test_recommendation_ranking_and_explanations(self):
        resume_text = """
Alex Chen
Senior Full Stack Engineer
Skills: Python, React, TypeScript, FastAPI, AWS, Docker, PostgreSQL
Experience: 6+ years building microservices and web apps.
"""
        parsed_resume = self.resume_svc.analyze_text(resume_text, "Alex.pdf")

        real_jobs = [
            {
                "id": "greenhouse_stripe_1",
                "title": "Senior Full Stack Engineer",
                "company": "Stripe",
                "platform": "greenhouse",
                "location": "San Francisco, CA / Remote",
                "is_remote": True,
                "url": "https://boards.greenhouse.io/stripe/jobs/1",
                "description": "Build web applications with React, TypeScript, Python, FastAPI, and PostgreSQL on AWS.",
                "extracted_skills": ["React", "TypeScript", "Python", "FastAPI", "PostgreSQL", "AWS"]
            },
            {
                "id": "lever_netflix_2",
                "title": "iOS Mobile Developer",
                "company": "Netflix",
                "platform": "lever",
                "location": "Los Gatos, CA",
                "is_remote": False,
                "url": "https://jobs.lever.co/netflix/2",
                "description": "Swift and Objective-C mobile app development.",
                "extracted_skills": ["Swift", "iOS Developer"]
            }
        ]

        # A caller cannot lower the hard 85% minimum.
        recs_80 = self.rec_svc.recommend_jobs(parsed_resume, real_jobs, min_score=80)
        self.assertEqual(len(recs_80), 1)
        self.assertEqual(recs_80[0]["id"], "greenhouse_stripe_1")
        self.assertGreaterEqual(recs_80[0]["match_score"], 85)

        # A lower threshold still excludes jobs without five matching skills.
        recs = self.rec_svc.recommend_jobs(parsed_resume, real_jobs, min_score=0)
        self.assertEqual(len(recs), 1)

        # First job should be top ranked due to 100% skill overlap + title alignment
        top_job = recs[0]
        self.assertEqual(top_job["id"], "greenhouse_stripe_1")
        self.assertGreaterEqual(top_job["match_score"], 85)
        self.assertEqual(top_job["fit_level"], "Exceptional Match")
        self.assertIn("React", top_job["matched_skills"])
        self.assertIn("Python", top_job["matched_skills"])
        self.assertEqual(top_job["url"], "https://boards.greenhouse.io/stripe/jobs/1")


    def test_requires_four_matching_skills_and_at_least_85_percent(self):
        resume = {
            "skills": ["Python", "React", "AWS", "Docker", "SQL"],
            "target_roles": ["Software Engineer"],
            "seniority_level": "Senior",
            "summary": "Software Engineer Python React AWS Docker SQL",
        }
        jobs = [
            {
                "id": "five-skills",
                "title": "Senior Software Engineer",
                "description": "Python React AWS Docker SQL",
                "extracted_skills": [
                    "Python", "React", "AWS", "Docker", "SQL", "Java", "Go",
                    "Kubernetes", "Terraform", "C++", "JavaScript", "Azure",
                    "Ruby", "PHP", "Swift", "Kotlin", "Scala", "R", "C#", "Rust",
                ],
            },
            {
                "id": "four-skills",
                "title": "Software Engineer",
                "description": "Python React AWS Docker",
                "extracted_skills": ["Python", "React", "AWS", "Docker"],
            },
            {
                "id": "three-skills",
                "title": "Junior Developer",
                "description": "Python React AWS",
                "extracted_skills": ["Python", "React", "AWS"],
            },
        ]

        recommendations = self.rec_svc.recommend_jobs(resume, jobs, min_score=85)

        # Both 4-skill and 5-skill jobs must qualify with score >= 85%
        rec_ids = [job["id"] for job in recommendations]
        self.assertIn("five-skills", rec_ids)
        self.assertIn("four-skills", rec_ids)
        self.assertNotIn("three-skills", rec_ids)
        for job in recommendations:
            self.assertGreaterEqual(job["match_score"], 85)
            self.assertGreaterEqual(len(job["matched_skills"]), 4)

    def test_fresher_only_gets_experience_appropriate_matches(self):
        resume = {
            "skills": ["Python", "React", "AWS", "Docker"],
            "target_roles": ["Software Engineer"],
            "seniority_level": "Junior / Entry",
            "years_of_experience": 0,
            "summary": "Graduate software engineer",
        }
        shared_skills = ["Python", "React", "AWS", "Docker"]
        jobs = [
            {
                "id": "graduate",
                "title": "Graduate Software Engineer",
                "description": "0-2 years of experience. Python React AWS Docker",
                "extracted_skills": shared_skills,
            },
            {
                "id": "junior",
                "title": "Junior Software Engineer",
                "description": "Python React AWS Docker",
                "extracted_skills": shared_skills,
            },
            {
                "id": "experienced",
                "title": "Software Engineer",
                "description": "Requires 3+ years of experience. Python React AWS Docker",
                "extracted_skills": shared_skills,
            },
            {
                "id": "senior",
                "title": "Senior Software Engineer",
                "description": "5+ years of professional experience. Python React AWS Docker",
                "extracted_skills": shared_skills,
            },
        ]

        recommendations = self.rec_svc.recommend_jobs(resume, jobs)
        recommendation_ids = {job["id"] for job in recommendations}

        self.assertEqual(recommendation_ids, {"graduate", "junior"})
        self.assertTrue(all(job["match_score"] >= 85 for job in recommendations))
        self.assertTrue(all(len(job["matched_skills"]) >= 4 for job in recommendations))

    def test_experienced_candidate_is_matched_using_years_not_fresher_roles(self):
        resume = {
            "skills": ["Python", "React", "AWS", "Docker"],
            "target_roles": ["Software Engineer"],
            "seniority_level": "Mid-Level",
            "years_of_experience": 4,
            "summary": "Software engineer with 4 years of experience",
        }
        shared_skills = ["Python", "React", "AWS", "Docker"]
        jobs = [
            {
                "id": "matching-years",
                "title": "Software Engineer",
                "description": "3-5 years of experience. Python React AWS Docker",
                "extracted_skills": shared_skills,
            },
            {
                "id": "too-many-years",
                "title": "Software Engineer",
                "description": "5+ years of experience. Python React AWS Docker",
                "extracted_skills": shared_skills,
            },
            {
                "id": "graduate-role",
                "title": "Graduate Software Engineer",
                "description": "Python React AWS Docker",
                "extracted_skills": shared_skills,
            },
        ]

        recommendations = self.rec_svc.recommend_jobs(resume, jobs)

        self.assertEqual([job["id"] for job in recommendations], ["matching-years"])
        self.assertIn("Listing asks for 3-5 years of experience", recommendations[0]["match_reasons"])

    def test_empty_database_returns_empty_recommendations(self):
        resume_text = "Software Engineer with Python skills."
        parsed_resume = self.resume_svc.analyze_text(resume_text, "Dev.pdf")
        recs = self.rec_svc.recommend_jobs(parsed_resume, [])
        self.assertEqual(recs, [])

if __name__ == "__main__":
    unittest.main()

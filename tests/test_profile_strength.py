import sys
import unittest
sys.path.insert(0, ".")
from backend.resume_service import ResumeService
from backend.profile_strength_service import evaluate_profile_strength


class TestProfileStrengthMeter(unittest.TestCase):
    def setUp(self):
        self.svc = ResumeService()

    def test_empty_profile_strength(self):
        strength = evaluate_profile_strength(None)
        self.assertEqual(strength["overall_score"], 0)
        self.assertIn("incomplete_sections", strength)
        self.assertEqual(len(strength["incomplete_sections"]), 6)
        self.assertTrue(len(strength["suggestions"]) > 0)

    def test_sample_devops_strength(self):
        with open("tests/sample_devops_resume.txt", "rb") as f:
            parsed = self.svc.parse_resume("sample_devops_resume.txt", f.read())

        self.assertIn("profile_strength", parsed)
        strength = parsed["profile_strength"]
        
        # Verify score is in valid range
        self.assertGreaterEqual(strength["overall_score"], 40)
        self.assertLessEqual(strength["overall_score"], 100)
        
        # Skills should be high
        sections = strength["sections"]
        self.assertEqual(sections["skills"]["score"], 100)
        self.assertEqual(sections["skills"]["status"], "complete")
        
        # Incomplete sections should be highlighted
        self.assertIn("incomplete_sections", strength)
        self.assertIn("education", strength["incomplete_sections"])
        
        # Suggestions should advise adding missing areas
        suggestions = strength["suggestions"]
        suggestion_titles = [s["title"] for s in suggestions]
        self.assertTrue(any("Education" in t or "Degree" in t for t in suggestion_titles))

    def test_dynamic_score_updates_when_profile_changes(self):
        profile = {
            "candidate_name": "Test Candidate",
            "email": "test@example.com",
            "phone": "+1 555-0192",
            "linkedin": "linkedin.com/in/test",
            "skills": ["Python", "FastAPI", "Docker", "PostgreSQL", "React"],
            "summary": "Experienced full-stack engineer building high-performance web applications and APIs.",
            "experience": [],
            "education": [],
            "projects": [],
            "certifications": [],
        }
        
        score_initial = evaluate_profile_strength(profile)["overall_score"]
        
        # Add Education
        profile["education"] = [{
            "degree": "B.Sc. in Computer Science",
            "institution": "University of Tech",
            "dates": "2018 - 2022"
        }]
        score_after_edu = evaluate_profile_strength(profile)["overall_score"]
        self.assertGreater(score_after_edu, score_initial, "Score must increase when education is added")
        
        # Add Experience with quantifiable metrics
        profile["experience"] = [{
            "title": "Software Engineer",
            "company": "Cloud Corp",
            "dates": "2022 - Present",
            "bullets": ["Scaled backend APIs serving 50k users", "Reduced query latency by 40%"]
        }]
        score_after_exp = evaluate_profile_strength(profile)["overall_score"]
        self.assertGreater(score_after_exp, score_after_edu, "Score must increase when work experience is added")
        
        # Add Project
        profile["projects"] = [{
            "title": "Distributed Cache Engine",
            "description": "High-throughput key-value store in Go with Raft consensus",
            "bullets": ["Handled 100k QPS with sub-millisecond p99 latency"]
        }]
        score_after_proj = evaluate_profile_strength(profile)["overall_score"]
        self.assertGreater(score_after_proj, score_after_exp, "Score must increase when project is added")
        
        # Add Certification
        profile["certifications"] = [{
            "name": "AWS Certified Solutions Architect",
            "issuer": "Amazon Web Services",
            "dates": "2023"
        }]
        score_after_cert = evaluate_profile_strength(profile)["overall_score"]
        self.assertGreater(score_after_cert, score_after_proj, "Score must increase when certification is added")


if __name__ == "__main__":
    unittest.main()

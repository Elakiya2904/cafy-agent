import unittest
from pathlib import Path
from backend.resume_generation_service import ResumeGenerationService
from backend.database import JobDatabase


class TestResumeGeneration(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.service = ResumeGenerationService(self.project_root)
        self.db = JobDatabase()

    def test_normalize_bullets_stringified_list(self):
        # Python-style stringified list
        raw = "['Built microservices with FastAPI', 'Optimized SQL queries with indexing']"
        bullets = self.service._normalize_bullets(raw)
        self.assertEqual(len(bullets), 2)
        self.assertEqual(bullets[0], "Built microservices with FastAPI")
        self.assertEqual(bullets[1], "Optimized SQL queries with indexing")

    def test_normalize_bullets_markdown_bullets(self):
        raw = "- Implemented CI/CD pipelines\n* Reduced deployment times by 40%\n• Collaborated with UX team"
        bullets = self.service._normalize_bullets(raw)
        self.assertEqual(len(bullets), 3)
        self.assertEqual(bullets[0], "Implemented CI/CD pipelines")
        self.assertEqual(bullets[1], "Reduced deployment times by 40%")
        self.assertEqual(bullets[2], "Collaborated with UX team")

    def test_normalize_entries_structure(self):
        entries = [
            {
                "title": "Senior Engineer",
                "organization": "FinTech Corp",
                "dates": "2022 - Present",
                "location": "London, UK",
                "description": "Led backend architecture team",
                "bullets": "['Engineered high-throughput event pipeline', 'Mentored 4 junior engineers']",
            }
        ]
        normalized = self.service._normalize_entries(entries, section="experience")
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["title"], "Senior Engineer")
        self.assertEqual(normalized[0]["organization"], "FinTech Corp")
        self.assertEqual(len(normalized[0]["bullets"]), 2)
        self.assertEqual(normalized[0]["bullets"][0], "Engineered high-throughput event pipeline")

    def test_database_persistence(self):
        job_id = "test-job-persist-123"
        resume_id = "test-res-persist-456"
        data = {
            "personal_info": {"name": "Test Candidate", "email": "test@candidate.com"},
            "professional_summary": "Experienced engineer.",
            "skills": ["Python", "Docker"],
            "experience": [],
            "projects": [],
            "education": [],
            "certifications": [],
        }
        self.db.save_tailored_resume(job_id, resume_id, data)
        retrieved = self.db.get_tailored_resume(job_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["resume_id"], resume_id)
        self.assertEqual(retrieved["resume"]["personal_info"]["name"], "Test Candidate")


if __name__ == "__main__":
    unittest.main()

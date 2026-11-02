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

    def test_blank_generated_summary_falls_back_to_uploaded_profile(self):
        normalized = self.service._validate_and_normalize(
            {"professional_summary": "   "},
            {"summary": "Experienced engineer with a proven delivery record."},
            {},
        )
        self.assertEqual(
            normalized["professional_summary"],
            "Experienced engineer with a proven delivery record.",
        )

    def test_normalization_keeps_projects_publications_and_achievements_separate(self):
        source = {
            "projects": [{"title": "Project One"}, {"title": "Project Two"}],
            "internships": [{"title": "Research Intern", "organization": "Lab"}],
            "publications": [{"title": "Paper One", "organization": "Research Journal"}],
            "achievements": [{"title": "Finalist, Data Challenge"}],
        }

        normalized = self.service._validate_and_normalize({}, source, {})

        self.assertEqual([item["title"] for item in normalized["projects"]], ["Project One", "Project Two"])
        self.assertEqual(normalized["internships"][0]["title"], "Research Intern")
        self.assertEqual(normalized["publications"][0]["title"], "Paper One")
        self.assertEqual(normalized["achievements"][0]["title"], "Finalist, Data Challenge")
        latex = self.service._render_latex(normalized)
        self.assertIn(r"\section*{Projects}", latex)
        self.assertIn(r"\section*{Publications}", latex)
        self.assertNotIn("Paper One", latex.split(r"\section*{Projects}", 1)[1].split(r"\section*{Publications}", 1)[0])

    def test_database_persistence(self):
        job_id = "test-job-persist-123"
        resume_id = "test-res-persist-456"
        data = {
            "personal_info": {"name": "Test Candidate", "email": "test@candidate.com"},
            "professional_summary": "Experienced engineer.",
            "skills": ["Python", "Docker"],
            "experience": [],
            "projects": [],
            "publications": [{"title": "Paper One"}],
            "education": [],
            "certifications": [],
        }
        self.db.save_tailored_resume(job_id, resume_id, data)
        retrieved = self.db.get_tailored_resume(job_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["resume_id"], resume_id)
        self.assertEqual(retrieved["resume"]["personal_info"]["name"], "Test Candidate")
        self.assertEqual(retrieved["resume"]["publications"], [{"title": "Paper One"}])


if __name__ == "__main__":
    unittest.main()

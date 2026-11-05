"""Test AI resume tailoring, factual validation, and document export.

Covers generated content, invented-fact guards, education descriptions, and
downloadable resume formats.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import docx

from backend.resume_generation_service import ResumeGenerationError, ResumeGenerationService
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

    def test_allowed_sections_render_without_discarding_extra_resume_data(self):
        source = {
            "summary": "Experienced engineer with a proven delivery record.",
            "education": [{
                "degree": "BSc Computer Science",
                "institution": "University of Leeds",
                "dates": "2020–2023",
                "description": "First complete sentence.\nSecond complete sentence.",
            }],
            "experience": [{
                "title": "Engineer",
                "company": "Example Ltd",
                "description": "Built reliable services.",
            }],
            "skills": ["Distributed systems"],
            "projects": [{"title": "Project One"}, {"title": "Project Two"}],
            "internships": [{"title": "Research Intern", "organization": "Lab"}],
            "publications": [{"title": "Paper One", "organization": "Research Journal"}],
            "certifications": [{"name": "Private Certification"}],
            "achievements": [{"title": "Finalist, Data Challenge"}],
            "activities": [{"title": "Student Society"}],
            "leadership": [{"title": "Club President"}],
            "awards": [{"title": "Research Prize"}],
        }

        normalized = self.service._validate_and_normalize({}, source, {})

        self.assertEqual([item["title"] for item in normalized["projects"]], ["Project One", "Project Two"])
        self.assertEqual(normalized["internships"][0]["title"], "Research Intern")
        self.assertEqual(normalized["publications"][0]["title"], "Paper One")
        self.assertEqual(normalized["certifications"][0]["name"], "Private Certification")
        self.assertEqual(normalized["achievements"][0]["title"], "Finalist, Data Challenge")
        self.assertEqual(normalized["activities"], source["activities"])
        self.assertEqual(normalized["leadership"], source["leadership"])
        self.assertEqual(normalized["awards"], source["awards"])
        latex = self.service._render_latex(normalized)
        self.assertEqual(
            re.findall(r"\\section\*\{([^}]+)\}", latex),
            ["About Me", "Education", "Work Experience", "Projects", "Skills"],
        )
        self.assertTrue(latex.lstrip().startswith(r"\documentclass"))
        self.assertIn("First complete sentence. Second complete sentence.", latex)
        self.assertIn("Distributed systems", latex)
        for excluded in (
            "Research Intern", "Paper One", "Finalist, Data Challenge", "Student Society",
            "Club President", "Research Prize",
        ):
            self.assertNotIn(excluded, latex)
        self.assertIn("Project One", latex)
        self.assertIn("Project Two", latex)
        self.assertNotIn("Private Certification", latex)

    def test_education_description_is_not_generated_from_degree_alone(self):
        class SkillExtractor:
            @staticmethod
            def extract_skills(text):
                return []

        tailored = {
            "professional_summary": "",
            "education": [
                {"degree": "BSc Computer Science", "institution": "University of Leeds",
                 "dates": "2020–2023", "location": "Leeds", "description": ""},
                {"degree": "A levels", "institution": "Example College", "description": "Existing description."},
            ],
            "experience": [],
            "projects": [],
        }
        rewritten = {
            "professional_summary": "Computer science graduate from the University of Leeds.",
            "experience": [],
            "projects": [],
        }
        response = mock.Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": json.dumps(rewritten)}}]}

        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "openai/gpt-oss-20b"}), \
             mock.patch("backend.resume_generation_service.requests.post", return_value=response) as post:
            result = self.service.rewrite_full(tailored, {"title": "Engineer"}, SkillExtractor())

        sent = post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertEqual(post.call_args.kwargs["json"]["temperature"], 1)
        self.assertNotIn('"degree": "BSc Computer Science"', sent)
        self.assertEqual(result["resume"]["education"][0]["description"], "")
        self.assertEqual(result["resume"]["education"][1]["description"], "Existing description.")

    def test_rewrite_full_surfaces_provider_error_for_bad_request(self):
        class SkillExtractor:
            @staticmethod
            def extract_skills(text):
                return []

        response = mock.Mock(status_code=400)
        response.json.return_value = {
            "error": {"message": "temperature must be 1 for this model"}
        }

        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), \
             mock.patch("backend.resume_generation_service.requests.post", return_value=response):
            with self.assertRaisesRegex(
                ResumeGenerationError,
                "status 400.*temperature must be 1",
            ):
                self.service.rewrite_full(
                    {"professional_summary": "Experienced engineer", "experience": [], "projects": []},
                    {"title": "Engineer"},
                    SkillExtractor(),
                )

    def test_rewrite_full_drafts_a_missing_summary_from_verified_profile_facts(self):
        class SkillExtractor:
            @staticmethod
            def extract_skills(text):
                return ["Python"] if "python" in text.lower() else []

        tailored = {
            "professional_summary": "",
            "skills": ["Python"],
            "experience": [{
                "title": "Engineer",
                "organization": "Example Ltd",
                "dates": "2022-Present",
                "description": "Built internal tools with Python.",
                "bullets": ["Built internal tools with Python."],
            }],
            "projects": [],
            "education": [],
        }
        rewritten = {
            "professional_summary": "Engineer experienced in Python, now targeting a software engineer role.",
            "experience": [{"index": 0, "description": "Built internal tools with Python.", "bullets": ["Built internal tools with Python."]}],
            "projects": [],
            "education": [],
        }
        response = mock.Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": json.dumps(rewritten)}}]}

        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), \
             mock.patch("backend.resume_generation_service.requests.post", return_value=response) as post:
            result = self.service.rewrite_full(tailored, {"title": "Software Engineer"}, SkillExtractor())

        prompt = post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn('"verified_summary_facts"', prompt)
        self.assertIn("Built internal tools with Python.", prompt)
        self.assertEqual(result["resume"]["professional_summary"], rewritten["professional_summary"])

    def test_generation_surfaces_tailoring_failures_instead_of_returning_untailored_resume(self):
        with mock.patch.object(
            self.service, "rewrite_full", side_effect=ResumeGenerationError("AI rewriting is unavailable.")
        ):
            with self.assertRaisesRegex(ResumeGenerationError, "AI rewriting is unavailable"):
                self.service.generate(
                    {"summary": "Engineer", "experience": [{"title": "Engineer", "company": "Example"}]},
                    {"title": "Software Engineer"},
                    skill_extractor=object(),
                )

    def test_generated_education_does_not_invent_coursework(self):
        normalized = self.service._validate_and_normalize(
            {},
            {"education": [{"degree": "BSc Computer Science", "institution": "Example University"}]},
            {},
        )
        education = normalized["education"][0]
        self.assertEqual(education["degree"], "BSc Computer Science")
        self.assertEqual(education["institution"], "Example University")
        self.assertEqual(education["description"], "")

    def test_docx_includes_projects_and_excludes_certifications(self):
        data = {
            "personal_info": {"name": "Test Candidate"},
            "professional_summary": "Experienced engineer.",
            "education": [{
                "degree": "BSc Computer Science",
                "institution": "Leeds",
                "description": "Focused on software engineering and distributed systems.",
            }],
            "experience": [{"title": "Engineer", "company": "Example Ltd"}],
            "skills": ["Python"],
            "projects": [{"title": "Included Project"}],
            "internships": [{"title": "Hidden Internship"}],
            "publications": [{"title": "Hidden Publication"}],
            "certifications": [{"name": "Included Certification"}],
            "achievements": [{"title": "Hidden Award"}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "resume.docx"
            self.service._export_docx(data, path)
            paragraphs = [p.text for p in docx.Document(path).paragraphs]

        text = "\n".join(paragraphs)
        self.assertIn("ABOUT ME", text)
        self.assertIn("Focused on software engineering and distributed systems.", text)
        self.assertIn("Included Project", text)
        self.assertNotIn("Included Certification", text)
        for excluded in ("Hidden Internship", "Hidden Publication", "Hidden Award"):
            self.assertNotIn(excluded, text)

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

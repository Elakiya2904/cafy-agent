"""Test extraction and classification of sections from uploaded resumes.

Checks parsed profile sections and upload persistence for sample PDF/DOCX-style
resume text.
"""
import asyncio
import io
import os
import tempfile
import unittest
from unittest import mock

from starlette.datastructures import UploadFile

from backend import main
from backend.database import JobDatabase
from backend.resume_service import ResumeService
from backend.user_store import UserSession, UserStore


class ResumeSectionExtractionTests(unittest.TestCase):
    def setUp(self):
        self.service = ResumeService()

    def test_all_sections_are_classified_and_keep_separate_publications(self):
        text = """ALEX MORGAN
PROFESSIONAL SUMMARY
Product engineer with experience building data products.
TECHNICAL SKILLS: Python, FastAPI, SQL
WORK EXPERIENCE
Software Engineer | Acme | 2021 - 2024
Built a reliable data API.
INTERNSHIP EXPERIENCE
Research Intern | Lab | 2020
Prepared experiment reports.
ACADEMIC PROJECTS
Forecasting System | Python | 2020
Built a forecasting pipeline for public data.
Open Data Portal | React | 2021
Created a searchable open-data application.
RESEARCH PUBLICATIONS
Demand Forecasting | Data Science Journal, 2022
Peer-reviewed analysis of regional demand.
Smart Shopping Cart | ACM, 2023
Published research on RFID-based billing.
EDUCATION
BSc Computer Science | City University | 2017 - 2020
CERTIFICATIONS
AWS Solutions Architect - AWS - 2024
ACHIEVEMENTS & AWARDS
Finalist, National Data Challenge
"""

        parsed = self.service.analyze_text(text)

        self.assertEqual(parsed["summary"], "Product engineer with experience building data products.")
        self.assertEqual(parsed["skills"], ["FastAPI", "Python", "SQL"])
        self.assertEqual(len(parsed["experience"]), 1)
        self.assertEqual(len(parsed["internships"]), 1)
        self.assertEqual(len(parsed["projects"]), 2)
        self.assertEqual(len(parsed["publications"]), 2)
        self.assertEqual(len(parsed["achievements"]), 1)
        self.assertIn("regional demand", parsed["publications"][0]["description"])
        self.assertIn("open-data application", parsed["projects"][1]["description"])
        self.assertNotIn("publications", parsed["projects"][0]["description"].lower())

    def test_projects_without_publications_stay_in_projects(self):
        parsed = self.service.analyze_text(
            """SUMMARY
Engineer.
KEY PROJECTS
Inventory Dashboard
Built a dashboard for inventory teams.
Task API
Implemented a task API for internal users.
"""
        )

        self.assertEqual(len(parsed["projects"]), 2)
        self.assertEqual(parsed["publications"], [])
        self.assertEqual(parsed["projects"][0]["title"], "Inventory Dashboard")
        self.assertEqual(parsed["projects"][0]["description"], "Built a dashboard for inventory teams.")

    def test_publications_without_projects_stay_in_publications(self):
        parsed = self.service.analyze_text(
            """PAPERS PUBLISHED
Reliable Scheduling | Systems Journal, 2022
Research on resilient scheduling.
"""
        )

        self.assertEqual(parsed["projects"], [])
        self.assertEqual(len(parsed["publications"]), 1)
        self.assertEqual(parsed["publications"][0]["title"], "Reliable Scheduling")
        self.assertEqual(parsed["publications"][0]["dates"], "2022")

    def test_alternative_headings_and_inline_objective_are_supported(self):
        parsed = self.service.analyze_text(
            """CAREER OBJECTIVE: Seeking a research engineering role.
SKILLS & TECHNOLOGIES
Python, PyTorch
PERSONAL PROJECTS
Vision Classifier | PyTorch
Built image classification tools.
PUBLICATIONS
Vision Models | Research Review, 2024
ACHIEVEMENTS
Best Poster Award
"""
        )

        self.assertEqual(parsed["summary"], "Seeking a research engineering role.")
        self.assertEqual(parsed["skills"], ["PyTorch", "Python"])
        self.assertEqual(len(parsed["projects"]), 1)
        self.assertEqual(len(parsed["publications"]), 1)
        self.assertEqual(len(parsed["achievements"]), 1)

    def test_skills_are_not_inferred_from_unrelated_sections(self):
        parsed = self.service.analyze_text(
            """WORK EXPERIENCE
Software Engineer | Acme | 2021 - 2024
Built APIs with Python, Django, PostgreSQL, and Docker.
"""
        )

        self.assertEqual(parsed["skills"], [])

    def test_pdf_pages_join_without_losing_section_boundaries(self):
        first_page = mock.Mock()
        first_page.extract_text.return_value = "PROJECTS\nForecasting System | Python\nBuilt a forecast."
        second_page = mock.Mock()
        second_page.extract_text.return_value = "PUBLICATIONS\nForecasting Results | Data Journal, 2023\nResearch results."
        reader = mock.Mock(pages=[first_page, second_page])
        with mock.patch("backend.resume_service.pypdf.PdfReader", return_value=reader):
            parsed = self.service.parse_resume("sample.pdf", b"pdf bytes")

        self.assertEqual(len(parsed["projects"]), 1)
        self.assertEqual(len(parsed["publications"]), 1)
        self.assertEqual(parsed["publications"][0]["title"], "Forecasting Results")
        self.assertEqual(
            first_page.extract_text.call_args_list,
            [mock.call(extraction_mode="layout"), mock.call()],
        )
        self.assertEqual(
            second_page.extract_text.call_args_list,
            [mock.call(extraction_mode="layout"), mock.call()],
        )

    def test_pdf_extraction_prefers_layout_when_its_lines_are_well_formed(self):
        page = mock.Mock()
        page.extract_text.return_value = "EDUCATION\nB.Tech. in Artificial Intelligence"
        reader = mock.Mock(pages=[page])
        with mock.patch("backend.resume_service.pypdf.PdfReader", return_value=reader):
            result = self.service._read_pdf(b"pdf bytes")

        self.assertIn("B.Tech. in Artificial Intelligence", result)
        self.assertEqual(
            page.extract_text.call_args_list,
            [mock.call(extraction_mode="layout"), mock.call()],
        )

    def test_pdf_extraction_uses_plain_text_when_layout_fragments_each_word(self):
        page = mock.Mock()
        page.extract_text.side_effect = [
            "WORK\nEXPERIENCE\nSoftware\nEngineer\nBuilt\nreliable\nAPIs",
            "WORK EXPERIENCE\nSoftware Engineer\nBuilt reliable APIs",
        ]
        reader = mock.Mock(pages=[page])
        with mock.patch("backend.resume_service.pypdf.PdfReader", return_value=reader):
            result = self.service._read_pdf(b"pdf bytes")

        self.assertEqual(result, "WORK EXPERIENCE\nSoftware Engineer\nBuilt reliable APIs")

    def test_wrapped_degree_and_project_metadata_do_not_become_separate_entries(self):
        parsed = self.service.analyze_text(
            """EDUCATION
B.Tech.
in Artificial Intelligence
B.Tech. in Artificial Intelligence
• Artificial Intelligence
PROJECTS
CloudSense
Coimbatore, Tamil Nadu
AI Developer
Jun 2025 – Apr 2026
Built a U-Net segmentation model with MobileNetV2 encoder.
"""
        )

        self.assertEqual(len(parsed["education"]), 1)
        self.assertEqual(parsed["education"][0]["degree"], "B.Tech. in Artificial Intelligence")
        self.assertEqual(parsed["education"][0]["bullets"], [])
        self.assertEqual(len(parsed["projects"]), 1)
        self.assertEqual(parsed["projects"][0]["title"], "CloudSense")
        self.assertEqual(parsed["projects"][0]["dates"], "Jun 2025 – Apr 2026")
        self.assertIn("Coimbatore, Tamil Nadu", parsed["projects"][0]["description"])
        self.assertIn("AI Developer", parsed["projects"][0]["description"])
        self.assertIn("Built a U-Net segmentation model", parsed["projects"][0]["description"])

    def test_upload_api_response_and_database_keep_publications_separate(self):
        source = b"""SUMMARY
Engineer.
PROJECTS
Inventory Dashboard | Python
Built an inventory dashboard.
PUBLICATIONS
Inventory Forecasting | Data Journal, 2024
Peer-reviewed forecasting paper.
ACHIEVEMENTS
Finalist, Data Challenge
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            database = JobDatabase(db_path=os.path.join(temp_dir, "resume.db"))
            store = UserStore(database)
            session = UserSession(store)
            with (
                mock.patch.object(main, "db", database),
                mock.patch.object(main, "user_store", store),
                mock.patch.object(main, "ACTIVE_SESSION", session),
                mock.patch.object(main.rec_svc, "recommend_jobs", return_value=[]),
            ):
                response = asyncio.run(
                    main.upload_resume(
                        UploadFile(filename="resume.txt", file=io.BytesIO(source))
                    )
                )
                uploaded_saved = store.get_resume("local")
                uploaded_profile = store.file_meta("local")["resume"]
                updated = main.update_resume_profile(
                    main.ProfileUpdateRequest(
                        projects=[],
                        publications=[{"title": "Updated Paper", "organization": "New Journal"}],
                    )
                )
                saved = store.get_resume("local")
                current = main.get_current_resume()

        self.assertEqual(response["status"], "success")
        self.assertEqual(len(response["resume"]["projects"]), 1)
        self.assertEqual(len(response["resume"]["publications"]), 1)
        self.assertEqual(len(response["resume"]["achievements"]), 1)
        self.assertEqual(uploaded_saved["publications"], response["resume"]["publications"])
        self.assertEqual(uploaded_profile["publications"], response["resume"]["publications"])
        self.assertEqual(updated["resume"]["projects"], [])
        self.assertEqual(saved["projects"], [])
        self.assertEqual(saved["publications"][0]["title"], "Updated Paper")
        self.assertEqual(current["resume"]["publications"], saved["publications"])


if __name__ == "__main__":
    unittest.main()

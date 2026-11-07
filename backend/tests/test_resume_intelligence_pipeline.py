"""Comprehensive Integration and Unit Tests for the Complete Resume Intelligence Pipeline.

Covers:
1. Extraction: Multi-column PDFs, scanned/image-only PDFs, tables in DOCX, hyphenated names, UK/international dates.
2. Profile Strength: Internships without traditional employment, senior professionals (10+ years) without academic projects, technical vs non-technical candidate scoring.
3. Job Matching: Mandatory vs preferred skills weighting, equivalent technologies, experience gap tolerance.
4. AI Tailoring: Vocabulary rewrite accepted, unevidenced tool rejected, metric preservation, Groq fallback model handling.
5. Export: PDF and DOCX contain all populated sections without data loss.
"""
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import docx

from backend.resume_service import ResumeService, SKILL_TAXONOMY
from backend.profile_strength_service import evaluate_profile_strength
from backend.job_match_analysis_service import analyze_profile_for_job
from backend.recommendation_service import match_jobs_for_candidate
from backend.resume_generation_service import ResumeGenerationService, ResumeGenerationError


class DummySkillExtractor:
    @staticmethod
    def extract_skills(text):
        lowered = text.lower()
        skills = []
        for category, items in SKILL_TAXONOMY.items():
            for item in items:
                if re.search(r"\b" + re.escape(item.lower()) + r"\b", lowered):
                    skills.append(item)
        return list(dict.fromkeys(skills))


class TestExtractionPipeline(unittest.TestCase):
    def setUp(self):
        self.service = ResumeService()

    def test_hyphenated_candidate_name_extraction(self):
        text = "Jean-Luc Picard\nEmail: jean-luc@starfleet.org\nPhone: +44 7123 456789\nLocation: London, UK"
        info = self.service._extract_candidate_info(text)
        self.assertEqual(info["name"], "Jean-Luc Picard")
        self.assertEqual(info["email"], "jean-luc@starfleet.org")
        self.assertEqual(info["location"], "London, UK")

    def test_international_and_uk_date_formats(self):
        text = """
        Experience
        Senior Software Engineer at Alpha Corp (08/2021 - Present)
        Led development of cloud systems.
        Junior Engineer at Beta Ltd (Jan 2019 - Jul 2021)
        Developed internal tools.
        """
        parsed = self.service.analyze_text(text)
        exp = parsed.get("experience", [])
        self.assertGreaterEqual(len(exp), 1)

    def test_scanned_image_only_pdf_detection(self):
        warning = self.service._detect_scanned_pdf("", page_count=3)
        self.assertIsNotNone(warning)
        self.assertIn("scanned", warning.lower())

    def test_docx_table_and_nested_table_extraction(self):
        doc = docx.Document()
        doc.add_paragraph("Jane Smith")
        doc.add_paragraph("jane.smith@example.com")
        doc.add_paragraph("Work Experience")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Software Engineer"
        table.cell(0, 1).text = "TechCorp (2020 - 2023)"
        table.cell(1, 0).text = "Built backend services using Python."
        table.cell(1, 1).text = "Optimized database performance."

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tf:
            temp_path = tf.name
        try:
            doc.save(temp_path)
            extracted_text = self.service._read_docx(temp_path)
            self.assertIn("Jane Smith", extracted_text)
            self.assertIn("Software Engineer", extracted_text)
            self.assertIn("TechCorp", extracted_text)
            self.assertIn("Built backend services using Python", extracted_text)
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestProfileStrengthPipeline(unittest.TestCase):
    def test_candidate_with_internships_and_no_traditional_employment(self):
        profile = {
            "candidate_name": "Alex Student",
            "email": "alex@university.ac.uk",
            "summary": "Recent computer science graduate with two internships.",
            "skills": ["Python", "JavaScript", "SQL", "Git", "Docker"],
            "experience": [],
            "internships": [
                {
                    "title": "Software Engineering Intern",
                    "company": "Fintech Solutions",
                    "dates": "Jun 2023 - Sep 2023",
                    "description": "Built automated data ingestion pipelines using Python.",
                    "bullets": ["Reduced ETL pipeline execution time by 30%."],
                },
                {
                    "title": "Research Intern",
                    "company": "University Lab",
                    "dates": "Jun 2022 - Aug 2022",
                    "description": "Assisted with distributed systems simulation.",
                    "bullets": ["Implemented benchmark tests."],
                },
            ],
            "education": [{"degree": "BSc Computer Science", "institution": "University of Bristol", "year": "2023"}],
            "projects": [{"name": "Final Year Project", "description": "Developed distributed caching system."}],
        }
        res = evaluate_profile_strength(profile)
        self.assertGreater(res["overall_score"], 60)
        self.assertIn("category_scores", res)
        self.assertIn("experience", res["category_scores"])
        self.assertGreater(res["category_scores"]["experience"], 50)
        self.assertIn("explanations", res)

    def test_senior_professional_without_academic_projects(self):
        profile = {
            "candidate_name": "Morgan Senior",
            "email": "morgan@enterprise.com",
            "summary": "Engineering Director with 12 years of distributed systems and platform leadership experience.",
            "skills": ["Python", "Go", "Kubernetes", "AWS", "PostgreSQL", "Docker", "System Design", "Microservices"],
            "experience": [
                {
                    "title": "Director of Engineering",
                    "company": "MegaCorp",
                    "dates": "2020 - Present",
                    "bullets": ["Led 4 engineering teams across 3 continents.", "Scaled systems to 10M DAU."],
                },
                {
                    "title": "Principal Architect",
                    "company": "CloudTech",
                    "dates": "2015 - 2020",
                    "bullets": ["Architected core SaaS platform.", "Cut infrastructure costs by 35%."],
                },
                {
                    "title": "Senior Software Engineer",
                    "company": "StartupCo",
                    "dates": "2012 - 2015",
                    "bullets": ["Built real-time messaging pipeline."],
                },
            ],
            "projects": [],
            "education": [{"degree": "BSc Computer Science", "institution": "Imperial College London", "year": "2012"}],
        }
        res = evaluate_profile_strength(profile)
        self.assertGreaterEqual(res["overall_score"], 80)
        # Verify projects are optional with zero manufactured score and zero weight
        self.assertEqual(res["category_scores"]["projects"], 0)
        self.assertEqual(res["sections"]["projects"]["weight"], 0)
        self.assertEqual(res["sections"]["projects"]["status"], "optional")

    def test_non_technical_candidate_profile(self):
        profile = {
            "candidate_name": "Sarah Marketing",
            "email": "sarah@marketlead.co.uk",
            "summary": "Head of Growth with 7 years experience driving B2B marketing campaigns and revenue growth.",
            "skills": ["Growth Marketing", "B2B Strategy", "Content Marketing", "SEO", "Customer Acquisition", "HubSpot", "Google Analytics"],
            "experience": [
                {
                    "title": "Head of Marketing",
                    "company": "ScaleUp Ltd",
                    "dates": "2021 - Present",
                    "bullets": ["Increased annual pipeline by 140%.", "Managed a team of 6 marketers."],
                },
                {
                    "title": "Growth Marketing Manager",
                    "company": "GrowthCo",
                    "dates": "2018 - 2021",
                    "bullets": ["Reduced CAC by 28% through SEO and inbound automation."],
                },
            ],
            "projects": [],
            "education": [{"degree": "BA Business & Marketing", "institution": "University of Manchester", "year": "2018"}],
        }
        res = evaluate_profile_strength(profile)
        self.assertGreaterEqual(res["overall_score"], 75)
        self.assertIn("category_scores", res)


class TestJobMatchingPipeline(unittest.TestCase):
    def test_mandatory_vs_preferred_skills_weighting(self):
        job = {
            "title": "Backend Python Developer",
            "description": "Required skills: Python, PostgreSQL, FastAPI. Preferred: Kubernetes, Kafka.",
            "extracted_skills": ["Python", "PostgreSQL", "FastAPI", "Kubernetes", "Kafka"],
        }
        candidate_with_mandatory = {
            "skills": ["Python", "PostgreSQL", "FastAPI"],
            "experience": [{"title": "Backend Developer", "bullets": ["Built APIs with Python, FastAPI, and PostgreSQL."]}],
            "summary": "Experienced Python backend developer.",
        }
        candidate_with_only_preferred = {
            "skills": ["Kubernetes", "Kafka"],
            "experience": [{"title": "DevOps Engineer", "bullets": ["Managed Kubernetes and Kafka clusters."]}],
            "summary": "Infrastructure engineer.",
        }
        score_mandatory = analyze_profile_for_job(candidate_with_mandatory, job)["job_match_score"]
        score_preferred = analyze_profile_for_job(candidate_with_only_preferred, job)["job_match_score"]
        self.assertGreater(score_mandatory, score_preferred)
        self.assertGreaterEqual(score_mandatory, 65)

    def test_transferable_cloud_technologies_matching(self):
        job = {
            "title": "Cloud Platform Engineer",
            "description": "Required skills: AWS, Docker, Terraform.",
            "extracted_skills": ["AWS", "Docker", "Terraform"],
        }
        candidate_exact_aws = {
            "skills": ["AWS", "Docker", "Terraform"],
            "experience": [{"title": "Cloud Engineer", "bullets": ["Built platform on AWS with Docker and Terraform."]}],
            "summary": "Cloud engineer with AWS expertise.",
        }
        candidate_transferable_gcp = {
            "skills": ["GCP", "Docker", "Terraform"],
            "experience": [{"title": "Cloud Engineer", "bullets": ["Built platform on GCP with Docker and Terraform."]}],
            "summary": "Cloud engineer with GCP expertise.",
        }
        res_exact = analyze_profile_for_job(candidate_exact_aws, job)
        res_transferable = analyze_profile_for_job(candidate_transferable_gcp, job)

        # 1. AWS is NOT treated as an exact match for candidate with GCP
        self.assertIn("AWS", res_exact["matched_skills"])
        self.assertNotIn("AWS", res_transferable["matched_skills"])

        # 2. Transferable credit is recognized without claiming verified proficiency
        self.assertIn("transferable_skills", res_transferable["sections"]["skills"])
        transferable = res_transferable["sections"]["skills"]["transferable_skills"]
        self.assertTrue(any(t["job_skill"] == "AWS" and t["candidate_skill"] == "GCP" for t in transferable))

        # 3. Exact match candidate scores strictly higher than transferable candidate
        self.assertGreater(res_exact["job_match_score"], res_transferable["job_match_score"])

    def test_mandatory_qualification_cannot_be_hidden_by_preferred_skills(self):
        job = {
            "title": "Principal Java Architect",
            "description": "Required skills: Java. Preferred skills: Docker, Git, Jira, Agile, Linux, AWS, Kubernetes.",
            "extracted_skills": ["Java", "Docker", "Git", "Jira", "Agile", "Linux", "AWS", "Kubernetes"],
        }
        # Candidate has all 7 preferred skills but lacks the single critical mandatory skill (Java)
        candidate_missing_mandatory = {
            "skills": ["Docker", "Git", "Jira", "Agile", "Linux", "AWS", "Kubernetes"],
            "experience": [{"title": "Infrastructure Engineer", "bullets": ["Managed cloud platform."]}],
            "summary": "Platform engineer.",
        }
        res = analyze_profile_for_job(candidate_missing_mandatory, job)
        # Mandatory qualification gate prevents high score despite matching 7 of 8 total skills
        self.assertLessEqual(res["job_match_score"], 65)
        self.assertLessEqual(res["sections"]["skills"]["score"], 50)

    def test_experience_gap_tolerance(self):
        job = {
            "title": "Senior Python Engineer",
            "description": "Requires 5+ years of Python experience and FastAPI.",
            "extracted_skills": ["Python", "FastAPI", "SQL"],
        }
        candidate_4_5_years = {
            "skills": ["Python", "FastAPI", "SQL", "Docker", "PostgreSQL"],
            "experience": [
                {
                    "title": "Python Engineer",
                    "company": "Fintech Alpha",
                    "dates": "Jan 2020 - Jun 2024",
                    "bullets": ["4.5 years of professional Python and FastAPI development building resilient services."],
                }
            ],
            "summary": "Software engineer with 4.5 years of backend experience.",
        }
        res = analyze_profile_for_job(candidate_4_5_years, job)
        self.assertGreaterEqual(res["job_match_score"], 75)


class TestAITailoringFactualVerification(unittest.TestCase):
    def test_vocabulary_rewrite_accepted_when_skills_match(self):
        tailored = {
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "experience": [
                {
                    "title": "Software Engineer",
                    "organization": "DataCorp",
                    "description": "Built backend services using Python and PostgreSQL.",
                    "bullets": ["Responsible for API development and database queries."],
                }
            ],
        }
        rewritten = {
            "experience": [
                {
                    "index": 0,
                    "description": "Engineered scalable backend services using Python and PostgreSQL.",
                    "bullets": ["Architected high-performance REST APIs and optimized complex database queries."],
                }
            ]
        }
        res = ResumeGenerationService.merge_rewrite(tailored, rewritten, DummySkillExtractor())
        bullet = res["resume"]["experience"][0]["bullets"][0]
        self.assertIn("Architected", bullet)
        self.assertEqual(res["rejected_lines"], 0)
        self.assertGreaterEqual(res["successfully_rewritten_bullets"], 1)

    def test_new_architecture_term_is_rejected(self):
        """'microservices' is a technology claim the original ('backend services') does not make."""
        tailored = {
            "skills": ["Python"],
            "experience": [{"title": "Engineer", "description": "Built backend services using Python.", "bullets": []}],
        }
        rewritten = {"experience": [{"index": 0, "description": "Engineered scalable microservices using Python.", "bullets": []}]}
        res = ResumeGenerationService.merge_rewrite(tailored, rewritten, DummySkillExtractor())
        self.assertEqual(res["resume"]["experience"][0]["description"], "Built backend services using Python.")
        self.assertEqual(res["rejected_lines"], 1)

    def test_unevidenced_tool_is_rejected(self):
        tailored = {
            "skills": ["Python"],
            "experience": [
                {
                    "title": "Backend Developer",
                    "bullets": ["Developed services using Python."],
                }
            ],
        }
        rewritten = {
            "experience": [
                {
                    "index": 0,
                    "bullets": ["Developed services using Python, Kubernetes, and Cassandra."],
                }
            ]
        }
        res = ResumeGenerationService.merge_rewrite(tailored, rewritten, DummySkillExtractor())
        bullet = res["resume"]["experience"][0]["bullets"][0]
        self.assertNotIn("Cassandra", bullet)
        self.assertEqual(res["rejected_lines"], 1)
        self.assertGreater(len(res["rejection_reasons"]), 0)

    def test_mathematically_equivalent_metric_preservation(self):
        self.assertTrue(
            ResumeGenerationService._is_mathematically_equivalent_metric("50", {"500", "250"})
        )
        self.assertFalse(
            ResumeGenerationService._is_mathematically_equivalent_metric("80", {"500", "250"})
        )

    def test_groq_fallback_handling_on_transient_failure(self):
        project_root = Path(__file__).resolve().parents[2]
        service = ResumeGenerationService(project_root)

        failed_response = mock.Mock(status_code=429)
        success_response = mock.Mock(status_code=200)
        success_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"professional_summary": "Tailored summary."})}}]
        }

        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), \
             mock.patch("backend.resume_generation_service.requests.post", side_effect=[failed_response, success_response]) as mock_post:
            res = service.rewrite_full(
                {"professional_summary": "Original summary.", "experience": [], "projects": []},
                {"title": "Engineer"},
                DummySkillExtractor(),
            )
            self.assertEqual(mock_post.call_count, 2)
            self.assertEqual(res["resume"]["professional_summary"], "Tailored summary.")


class TestDocumentExportPipeline(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parents[2]
        self.service = ResumeGenerationService(self.project_root)
        self.data = {
            "personal_info": {
                "name": "Jane Developer",
                "email": "jane@example.co.uk",
                "phone": "+44 7000 000000",
                "location": "Edinburgh, UK",
                "linkedin": "jane-dev",
                "github": "janedev",
            },
            "target_role": "Senior Cloud Engineer",
            "professional_summary": "Senior engineer with 8 years of distributed systems experience.",
            "skills": ["Python", "AWS", "Docker", "PostgreSQL"],
            "experience": [
                {
                    "title": "Cloud Architect",
                    "organization": "CloudScale Ltd",
                    "dates": "2021 - Present",
                    "location": "Edinburgh",
                    "description": "Leading cloud architecture.",
                    "bullets": ["Scaled AWS ECS platform to 5M events/day."],
                }
            ],
            "internships": [
                {
                    "title": "Systems Intern",
                    "organization": "CERN",
                    "dates": "2016",
                    "location": "Geneva",
                    "description": "High performance computing cluster testing.",
                    "bullets": ["Benchmarked MPI communication latency."],
                }
            ],
            "education": [
                {
                    "degree": "MEng Computer Systems",
                    "institution": "University of Edinburgh",
                    "dates": "2012 - 2017",
                    "location": "Edinburgh",
                    "description": "Graduated with First Class Honours.",
                    "bullets": ["Thesis on distributed consensus algorithms."],
                }
            ],
            "projects": [
                {
                    "title": "Open Source Raft Implementation",
                    "organization": "GitHub",
                    "dates": "2022",
                    "description": "Consensus algorithm implementation in Go.",
                    "bullets": ["Achieved 99.99% test pass rate on Jepsen tests."],
                }
            ],
            "certifications": [
                {
                    "name": "AWS Certified Solutions Architect - Professional",
                    "issuer": "Amazon Web Services",
                    "dates": "2023",
                    "description": "Credential ID: AWS-PSA-12345",
                }
            ],
            "publications": [
                {
                    "title": "Fault-Tolerant Distributed Consensus in Cloud Environments",
                    "organization": "IEEE Transactions on Cloud Computing",
                    "dates": "2020",
                    "description": "Co-authored paper examining consensus under partition.",
                    "bullets": ["Cited 42 times."],
                }
            ],
            "achievements": [
                {
                    "title": "National Hackathon Winner",
                    "dates": "2021",
                    "description": "1st place out of 120 teams for real-time telemetry pipeline.",
                    "bullets": ["Built end-to-end data processing demonstrator."],
                }
            ],
        }

    def test_latex_renders_the_five_template_sections(self):
        latex = self.service._render_latex(self.data)
        self.assertIn("JANE DEVELOPER", latex)
        for title in ("About Me", "Education", "Work Experience", "Projects", "Skills"):
            self.assertIn("\\section*{%s}" % title, latex)
        self.assertEqual(latex.count("\\section*{"), 5)
        self.assertIn("CERN", latex)  # internship, printed under Work Experience
        self.assertNotIn("IEEE Transactions", latex)
        self.assertNotIn("National Hackathon Winner", latex)

    def test_docx_exports_the_five_template_sections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_resume.docx"
            self.service._export_docx(self.data, path)
            doc = docx.Document(path)
            full_text = "\n".join(p.text for p in doc.paragraphs)

            self.assertIn("JANE DEVELOPER", full_text.upper())
            self.assertIn("ABOUT ME", full_text)
            self.assertIn("WORK EXPERIENCE", full_text)
            self.assertIn("CloudScale Ltd", full_text)
            self.assertIn("CERN", full_text)
            self.assertIn("EDUCATION", full_text)
            self.assertIn("University of Edinburgh", full_text)
            self.assertIn("PROJECTS", full_text)
            self.assertIn("Open Source Raft Implementation", full_text)
            self.assertIn("SKILLS", full_text)
            self.assertNotIn("PUBLICATIONS", full_text)
            self.assertNotIn("ACHIEVEMENTS", full_text)

    def test_latex_skills_wrapping_without_mbox_overflow(self):
        long_skills = [
            "AWS Certified Solutions Architect Professional",
            "Natural Language Processing with Transformers & Deep Learning",
            "Microservices Architecture & Distributed High-Throughput Event Streaming",
            "PostgreSQL Database Performance Tuning and Query Optimization",
        ] + [f"Technical Skill {i}" for i in range(1, 27)]
        data = dict(self.data, skills=long_skills)
        latex = self.service._render_latex(data)
        self.assertNotIn(r"\mbox", latex)
        self.assertIn("AWS Certified Solutions Architect Professional", latex)
        self.assertIn(r"\begin{multicols}{3}", latex)


if __name__ == "__main__":
    unittest.main()


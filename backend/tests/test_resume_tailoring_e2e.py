"""End-to-end tests for the resume tailoring workflow.

Upload text -> parsing -> structured data -> job matching -> AI tailoring (Groq mocked) ->
factual validation -> save (editor) -> DOCX / LaTeX export, plus the API endpoints that join
them. Covers fresh graduates with internships, full-time candidates, duplicate records, empty
AI internship arrays, unsupported AI claims, long multi-page resumes and export consistency.
"""
import copy
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import docx

sys.path.insert(0, ".")
from backend.job_match_analysis_service import analyze_profile_for_job
from backend.resume_generation_service import (
    FALLBACK_GROQ_MODELS,
    ResumeGenerationError,
    ResumeGenerationService,
)
from backend.resume_service import ResumeService
from backend.resume_structure import SECTION_TITLES, render_sections, standardize_dates

PROJECT_ROOT = Path(__file__).resolve().parents[2]

GRADUATE_RESUME = """Priya Raman
priya.raman@example.ac.uk | +44 7700 900123 | London, UK
linkedin.com/in/priya-raman

Profile
Final-year Economics and Finance student with two internships in trade support and operations.

Education
BSc Economics and Finance | University of Warwick | Sep 2022 - Jun 2025
- First Class Honours (predicted)
BSc Economics and Finance | University of Warwick | Sep 2022 - Jun 2025

Internship Experience
Trade Support Intern | Barclays | London | Jun 2024 - Aug 2024
- Reconciled daily equity trade breaks using Excel and SQL, clearing 95% within T+1.
- Built a VBA macro to automate settlement status reports.
Operations Intern | HSBC | London | Jul 2023 - Sep 2023
- Monitored trade settlement queues and escalated failed trades to counterparties.

Work Experience
Retail Assistant | Tesco | Coventry | 2021 - 2022
- Handled cash reconciliation at the end of each shift.

Projects
Portfolio Risk Dashboard | 2024
- Built a Python and Pandas dashboard to track value at risk for a mock portfolio.

Skills
Communication, Teamwork, Attention to detail
"""

# Internships written under a plain "Experience" heading, as many graduates do.
INTERNS_UNDER_EXPERIENCE = """Sam Lee
sam.lee@example.com | Manchester, UK

Experience
Software Engineering Intern | Monzo | London | Jun 2024 - Sep 2024
- Built internal dashboards with React and TypeScript.
Data Analyst Intern | Ocado | Hatfield | Jun 2023 - Aug 2023
- Wrote SQL reports for warehouse throughput.

Education
BSc Computer Science | University of Manchester | 2021 - 2025

Skills
Python, React, TypeScript, SQL
"""

TRADING_JOB = {
    "id": "job-trading",
    "title": "Graduate Trading Operations Analyst",
    "company": "Example Bank",
    "description": (
        "Join our trading operations team in London. Required skills: Excel, SQL, trade settlement and "
        "reconciliation, strong communication. Preferred: Python, VBA. "
        "A bachelor's degree in Finance, Economics or Mathematics."
    ),
}

SENIOR_JOB = {
    "id": "job-senior",
    "title": "Senior Backend Engineer",
    "company": "Example Ltd",
    "description": "Requires 5+ years of experience with Python, PostgreSQL and AWS. Preferred: Kubernetes.",
}


def parse(text: str) -> dict:
    return ResumeService().analyze_text(text, "resume.txt")


def groq_reply(payload: dict, status: int = 200) -> mock.Mock:
    response = mock.Mock(status_code=status)
    response.json.return_value = (
        {"choices": [{"message": {"content": json.dumps(payload)}}]} if status == 200
        else {"error": {"message": f"provider error {status}"}}
    )
    return response


def docx_text(path: Path) -> str:
    return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)


class TestParsingKeepsInternshipsSeparate(unittest.TestCase):
    def test_graduate_resume_sections(self):
        profile = parse(GRADUATE_RESUME)
        self.assertEqual([e["title"] for e in profile["internships"]], ["Trade Support Intern", "Operations Intern"])
        self.assertEqual([e["company"] for e in profile["internships"]], ["Barclays", "HSBC"])
        self.assertEqual(profile["internships"][0]["dates"], "Jun 2024 - Aug 2024")
        self.assertEqual(profile["internships"][0]["location"], "London")
        self.assertEqual(len(profile["internships"][0]["bullets"]), 2)
        # The part-time job stays a work entry; no internship is relabelled as employment.
        self.assertEqual([e["title"] for e in profile["experience"]], ["Retail Assistant"])

    def test_duplicate_education_is_merged_without_losing_details(self):
        education = parse(GRADUATE_RESUME)["education"]
        self.assertEqual(len(education), 1)
        self.assertEqual(education[0]["degree"], "BSc Economics and Finance")
        self.assertEqual(education[0]["institution"], "University of Warwick")
        self.assertEqual(education[0]["dates"], "Sep 2022 - Jun 2025")
        self.assertEqual(education[0]["bullets"], ["First Class Honours (predicted)"])

    def test_project_year_is_a_date_not_an_organisation(self):
        project = parse(GRADUATE_RESUME)["projects"][0]
        self.assertEqual(project["title"], "Portfolio Risk Dashboard")
        self.assertEqual(project["dates"], "2024")
        self.assertEqual(project["organization"], "")

    def test_internships_listed_under_experience_heading_are_moved(self):
        profile = parse(INTERNS_UNDER_EXPERIENCE)
        self.assertEqual(profile["experience"], [])
        self.assertEqual(
            [e["title"] for e in profile["internships"]],
            ["Software Engineering Intern", "Data Analyst Intern"],
        )


class TestJobMatchingWholeResume(unittest.TestCase):
    def setUp(self):
        self.profile = parse(GRADUATE_RESUME)
        self.result = analyze_profile_for_job(self.profile, TRADING_JOB)

    def test_skills_outside_the_skills_section_count_with_evidence(self):
        # The Skills section lists only soft skills; Excel/SQL/VBA/Python come from internships and projects.
        self.assertNotIn("Excel", self.profile["skills"])
        reqs = {r["skill"]: r for r in self.result["requirements"]}
        for skill, section in (("Excel", "internships"), ("SQL", "internships"), ("VBA", "internships"), ("Python", "projects")):
            self.assertEqual(reqs[skill]["status"], "matched", skill)
            self.assertIn(section, {e["section"] for e in reqs[skill]["evidence"]}, skill)
        self.assertEqual(reqs["Python"]["importance"], "preferred")
        self.assertEqual(reqs["Excel"]["importance"], "mandatory")

    def test_internships_count_as_relevant_experience_not_years(self):
        exp = self.result["sections"]["experience"]
        self.assertGreater(exp["score"], 0)
        self.assertEqual(exp["internship_roles"], 2)
        self.assertEqual(exp["full_time_roles"], 1)
        self.assertFalse(exp["years_requirement_applied"])

    def test_graduate_role_uses_entry_level_weights_and_is_explained(self):
        self.assertTrue(self.result["entry_level_job"])
        weights = {b["section"]: b["weight"] for b in self.result["score_breakdown"]}
        self.assertEqual(weights["experience"], 20)
        self.assertEqual(weights["education"], 15)
        total = sum(b["contribution"] for b in self.result["score_breakdown"])
        self.assertAlmostEqual(total, self.result["job_match_score"], delta=1.0)

    def test_score_is_far_above_the_old_skills_list_only_result(self):
        # Old behaviour: only the Skills list counted and internships were invisible to the editor score.
        old_style = analyze_profile_for_job(
            {**self.profile, "internships": [], "projects": [], "experience": []}, TRADING_JOB
        )
        self.assertGreaterEqual(self.result["job_match_score"], 55)
        self.assertGreater(self.result["job_match_score"], old_style["job_match_score"] + 20)
        self.assertGreaterEqual(self.result["sections"]["skills"]["score"], 70)

    def test_no_duplicate_skill_counting(self):
        self.assertEqual(len(self.result["job_skills"]), len({s.casefold() for s in self.result["job_skills"]}))
        self.assertEqual(len(self.result["matched_skills"]), len(set(self.result["matched_skills"])))

    def test_missing_requirement_is_reported_as_missing(self):
        job = {**TRADING_JOB, "description": TRADING_JOB["description"] + " Required: Bloomberg terminal, Murex."}
        reqs = {r["skill"]: r for r in analyze_profile_for_job(self.profile, job)["requirements"]}
        self.assertTrue(any(r["status"] == "missing" and not r["evidence"] for r in reqs.values()))

    def test_full_time_candidate_years_from_role_dates(self):
        profile = {
            "summary": "Backend engineer.",
            "skills": ["Python", "PostgreSQL", "AWS"],
            "experience": [
                {"title": "Backend Engineer", "company": "A", "dates": "Jan 2017 - Dec 2020", "bullets": ["Built Python APIs on AWS"]},
                {"title": "Senior Backend Engineer", "company": "B", "dates": "Jan 2021 - Present", "bullets": ["Ran PostgreSQL at scale"]},
            ],
            "internships": [{"title": "Intern", "company": "C", "dates": "2015 - 2016"}],
        }
        exp = analyze_profile_for_job(profile, SENIOR_JOB)["sections"]["experience"]
        self.assertTrue(exp["years_requirement_applied"])
        self.assertGreaterEqual(exp["candidate_years"], 9)  # internship years are not added
        self.assertLess(exp["candidate_years"], 11)


class TestTailoringPreservesFacts(unittest.TestCase):
    def setUp(self):
        self.service = ResumeGenerationService(PROJECT_ROOT)
        self.profile = parse(GRADUATE_RESUME)
        self.extractor = ResumeService()

    def generate(self, ai_payload: dict) -> dict:
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), \
             mock.patch("backend.resume_generation_service.requests.post", return_value=groq_reply(ai_payload)), \
             mock.patch.object(self.service, "update_artifacts", return_value={"resume_id": "x"}):
            return self.service.generate(self.profile, TRADING_JOB, self.extractor)

    def test_empty_ai_internship_array_never_drops_internships(self):
        original = copy.deepcopy(self.profile)
        result = self.generate({
            "professional_summary": "Economics and Finance student with trade support and operations internships.",
            "experience": [], "internships": [], "projects": [], "education": [],
        })
        internships = result["resume"]["internships"]
        self.assertEqual([i["title"] for i in internships], ["Trade Support Intern", "Operations Intern"])
        self.assertEqual(internships[0]["bullets"], original["internships"][0]["bullets"])
        self.assertEqual([e["title"] for e in result["resume"]["experience"]], ["Retail Assistant"])
        self.assertTrue(result["validation"]["internships_preserved"])
        # Internships print under Work Experience in the UK template.
        self.assertIn("experience", result["validation"]["sections"])
        # The uploaded profile itself is never modified.
        self.assertEqual(self.profile, original)

    def test_internship_bullets_are_tailored_but_unsupported_claims_rejected(self):
        result = self.generate({
            "professional_summary": "Graduate with 5 years of Bloomberg experience.",
            "internships": [
                {"index": 0, "description": "", "bullets": [
                    "Reconciled daily equity trade breaks in Excel and SQL, clearing 95% within T+1.",
                    "Built a Murex and Kafka pipeline to automate settlement reports.",
                ]},
            ],
        })
        bullets = result["resume"]["internships"][0]["bullets"]
        self.assertEqual(bullets[0], "Reconciled daily equity trade breaks in Excel and SQL, clearing 95% within T+1.")
        self.assertEqual(bullets[1], "Built a VBA macro to automate settlement status reports.")  # original kept
        self.assertNotIn("5 years", result["resume"]["professional_summary"])
        self.assertGreaterEqual(result["validation"]["rejected_ai_lines"], 2)
        self.assertTrue(result["validation"]["unsupported_claims"])

    def test_ai_payload_includes_internships_and_experience_level_rules(self):
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), \
             mock.patch("backend.resume_generation_service.requests.post", return_value=groq_reply({})) as post, \
             mock.patch.object(self.service, "update_artifacts", return_value={}):
            self.service.generate(self.profile, TRADING_JOB, self.extractor)
        body = post.call_args.kwargs["json"]
        payload = json.loads(body["messages"][1]["content"])
        self.assertEqual(len(payload["resume"]["internships"]), 2)
        self.assertIn("internships are internships", body["messages"][0]["content"])

    def test_no_generic_education_text_is_invented(self):
        result = self.generate({})
        self.assertEqual(result["resume"]["education"][0]["description"], "")

    def test_long_resume_keeps_every_record(self):
        profile = copy.deepcopy(self.profile)
        profile["experience"] = [
            {"title": f"Analyst {i}", "company": f"Firm {i}", "dates": f"{2010 + i} - {2011 + i}",
             "bullets": [f"Delivered report {i}.{j} for the operations desk." for j in range(5)]}
            for i in range(8)
        ]
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), \
             mock.patch("backend.resume_generation_service.requests.post", return_value=groq_reply({})), \
             mock.patch.object(self.service, "update_artifacts", return_value={}):
            result = self.service.generate(profile, TRADING_JOB, self.extractor)
        self.assertEqual(len(result["resume"]["experience"]), 8)
        self.assertEqual([len(e["bullets"]) for e in result["resume"]["experience"]], [5] * 8)
        self.assertEqual(len(result["resume"]["internships"]), 2)


class TestGroqModelFallback(unittest.TestCase):
    def setUp(self):
        self.service = ResumeGenerationService(PROJECT_ROOT)

    def test_retired_model_404_moves_to_the_next_model(self):
        replies = [groq_reply({}, 404), groq_reply({}, 429), groq_reply({"professional_summary": "Tailored."})]
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k", "GROQ_MODEL": ""}), \
             mock.patch("backend.resume_generation_service.requests.post", side_effect=replies) as post:
            result = self.service.rewrite_full({"professional_summary": "Original.", "experience": []}, {"title": "X"}, ResumeService())
        self.assertEqual([c.kwargs["json"]["model"] for c in post.call_args_list], FALLBACK_GROQ_MODELS)
        self.assertEqual(result["resume"]["professional_summary"], "Tailored.")

    def test_invalid_json_and_timeouts_fall_back(self):
        import requests
        bad = mock.Mock(status_code=200)
        bad.json.return_value = {"choices": [{"message": {"content": "Sure! here is text, not JSON"}}]}
        good = groq_reply({"professional_summary": "Tailored."})
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k", "GROQ_MODEL": ""}), \
             mock.patch("backend.resume_generation_service.requests.post",
                        side_effect=[requests.Timeout("slow"), bad, good]):
            result = self.service.rewrite_full({"professional_summary": "Original.", "experience": []}, {"title": "X"}, ResumeService())
        self.assertEqual(result["resume"]["professional_summary"], "Tailored.")

    def test_fenced_json_reply_is_accepted(self):
        fenced = mock.Mock(status_code=200)
        fenced.json.return_value = {"choices": [{"message": {"content": "```json\n{\"professional_summary\": \"Tailored.\"}\n```"}}]}
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k"}), \
             mock.patch("backend.resume_generation_service.requests.post", return_value=fenced):
            result = self.service.rewrite_full({"professional_summary": "Original.", "experience": []}, {"title": "X"}, ResumeService())
        self.assertEqual(result["resume"]["professional_summary"], "Tailored.")

    def test_rejected_api_key_stops_immediately(self):
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k"}), \
             mock.patch("backend.resume_generation_service.requests.post", return_value=groq_reply({}, 401)) as post:
            with self.assertRaisesRegex(ResumeGenerationError, "status 401"):
                self.service.rewrite_full({"professional_summary": "x", "experience": []}, {"title": "X"}, ResumeService())
        self.assertEqual(post.call_count, 1)

    def test_all_models_failing_raises_instead_of_returning_untailored(self):
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k", "GROQ_MODEL": ""}), \
             mock.patch("backend.resume_generation_service.requests.post", return_value=groq_reply({}, 503)):
            with self.assertRaisesRegex(ResumeGenerationError, "status 503"):
                self.service.rewrite_full({"professional_summary": "x", "experience": []}, {"title": "X"}, ResumeService())


class TestEditorSaveRules(unittest.TestCase):
    def setUp(self):
        self.service = ResumeGenerationService(PROJECT_ROOT)
        self.profile = parse(GRADUATE_RESUME)

    def test_user_can_remove_internships_explicitly(self):
        saved = self.service._validate_and_normalize({"internships": []}, self.profile, TRADING_JOB, keep_edits=True)
        self.assertEqual(saved["internships"], [])

    def test_internship_copied_into_work_experience_is_removed_once(self):
        intern = self.profile["internships"][0]
        edited = {"experience": [intern, {"title": "Retail Assistant", "company": "Tesco"}], "internships": [intern]}
        saved = self.service._validate_and_normalize(edited, self.profile, TRADING_JOB, keep_edits=True)
        self.assertEqual([e["title"] for e in saved["experience"]], ["Retail Assistant"])
        self.assertEqual([e["title"] for e in saved["internships"]], ["Trade Support Intern"])

    def test_missing_internships_key_falls_back_to_profile(self):
        saved = self.service._validate_and_normalize({"experience": []}, self.profile, TRADING_JOB, keep_edits=True)
        self.assertEqual(len(saved["internships"]), 2)


class TestExportConsistency(unittest.TestCase):
    def setUp(self):
        self.service = ResumeGenerationService(PROJECT_ROOT)
        self.resume = self.service._validate_and_normalize({}, parse(GRADUATE_RESUME), TRADING_JOB)

    def test_section_order_and_headings(self):
        # UK template: About Me, Education, Work Experience, Projects, Skills - always this order.
        keys = [s["key"] for s in render_sections(self.resume)]
        self.assertEqual(keys, ["summary", "education", "experience", "projects", "skills"])
        # Full-time roles first, then internships, all under Work Experience.
        work = next(s for s in render_sections(self.resume) if s["key"] == "experience")
        self.assertEqual([e["heading"] for e in work["entries"]],
                         ["Retail Assistant", "Trade Support Intern", "Operations Intern"])
        early = dict(self.resume, experience=[])
        self.assertEqual([s["key"] for s in render_sections(early)], keys)
        self.assertEqual(SECTION_TITLES["summary"], "About Me")
        # Entry first line is "Organisation, Location | dates".
        self.assertEqual(work["entries"][1]["meta"], "Barclays, London | Jun 2024 \u2013 Aug 2024")

    def test_docx_and_latex_carry_the_same_sections_and_entries(self):
        sections = render_sections(self.resume)
        latex = self.service._render_latex(self.resume)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.docx"
            self.service._export_docx(self.resume, path)
            text = docx_text(path)
            section_obj = docx.Document(str(path)).sections[0]
        self.assertEqual(re.findall(r"\\section\*\{([^}]+)\}", latex), [s["title"] for s in sections])
        for s in sections:
            self.assertIn(s["title"].upper(), text)
            for entry in s.get("entries", []):
                self.assertIn(entry["heading"], text)
                self.assertIn(self.service._texescape(entry["heading"]), latex)
                for bullet in entry["bullets"]:
                    self.assertIn(bullet, text)
                    self.assertIn(self.service._texescape(bullet), latex)
        # A4, not US Letter.
        self.assertAlmostEqual(section_obj.page_width.mm, 210, delta=1)
        self.assertAlmostEqual(section_obj.page_height.mm, 297, delta=1)
        self.assertIn("a4paper", latex)

    def test_skills_render_as_three_columns(self):
        latex = self.service._render_latex(self.resume)
        self.assertIn(r"\begin{multicols}{3}", latex)
        for skill in self.resume["skills"]:
            self.assertIn("\\item " + self.service._texescape(skill), latex)

    def test_dates_are_standardised(self):
        self.assertEqual(standardize_dates("September 2023 - present"), "Sep 2023 – Present")
        self.assertEqual(standardize_dates("08/2021 to date"), "Aug 2021 – Present")
        self.assertEqual(standardize_dates("2019-2022"), "2019 – 2022")
        self.assertEqual(standardize_dates("2019/20"), "2019/20")


class TestApiWorkflow(unittest.TestCase):
    """Generate -> save edits -> download: the stored resume and exports always match the editor."""

    def setUp(self):
        from backend import main
        from backend.database import JobDatabase
        from backend.tests.helpers import authed_client
        from backend.tests.test_resume_versions_export import bind_main_to_db

        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = JobDatabase(db_path=os.path.join(self.tmp.name, "e2e.db"))
        self.profile = parse(GRADUATE_RESUME)
        self.patches = bind_main_to_db(main, self.db, self.profile) + [
            mock.patch.object(self.db, "get_job", return_value=dict(TRADING_JOB)),
            mock.patch.object(main.resume_generation_svc, "output_dir", Path(self.tmp.name)),
            mock.patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}),
        ]
        for p in self.patches:
            p.start()
        self.client = authed_client()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_generate_save_and_download(self):
        ai = {"professional_summary": "Economics and Finance student with trade support and operations internships.",
              "internships": [], "experience": [], "projects": [], "education": []}
        with mock.patch("backend.resume_generation_service.requests.post", return_value=groq_reply(ai)):
            generated = self.client.post("/api/resumes/generate", json={"job_id": TRADING_JOB["id"]})
        self.assertEqual(generated.status_code, 200, generated.text)
        body = generated.json()
        self.assertEqual(len(body["resume"]["internships"]), 2)
        self.assertEqual(len(body["resume"]["education"]), 1)
        self.assertGreater(body["generation_scores"]["job_match_score"], 0)

        # The editor changes a bullet and removes the part-time job, then saves.
        edited = copy.deepcopy(body["resume"])
        edited["internships"][1]["bullets"] = ["Monitored settlement queues and escalated failed trades."]
        edited["experience"] = []
        saved = self.client.post("/api/resumes/save", json={
            "job_id": TRADING_JOB["id"], "resume_id": body["resume_id"], "resume": edited,
        })
        self.assertEqual(saved.status_code, 200, saved.text)

        stored = self.client.get(f"/api/resumes/job/{TRADING_JOB['id']}").json()["tailored_resume"]
        self.assertEqual(stored["experience"], [])
        self.assertEqual(stored["internships"][1]["bullets"], ["Monitored settlement queues and escalated failed trades."])

        download = self.client.get(f"/api/resumes/{body['resume_id']}/docx")
        self.assertEqual(download.status_code, 200)
        text = "\n".join(p.text for p in docx.Document(io.BytesIO(download.content)).paragraphs)
        self.assertIn("WORK EXPERIENCE", text)  # internships print under Work Experience
        self.assertIn("Monitored settlement queues and escalated failed trades.", text)
        self.assertNotIn("Retail Assistant", text)
        self.assertEqual(text.count("BSc Economics and Finance"), 1)

        latex = self.client.get(f"/api/resumes/{body['resume_id']}/latex").text
        self.assertIn("Monitored settlement queues and escalated failed trades.", latex)
        self.assertIn(r"\section*{Work Experience}", latex)

    def test_pre_analysis_endpoint_scores_internships(self):
        response = self.client.post("/api/resumes/pre-analysis", json={"job_id": TRADING_JOB["id"]})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertGreater(result["sections"]["experience"]["score"], 0)
        self.assertEqual(result["sections"]["experience"]["internship_roles"], 2)


if __name__ == "__main__":
    unittest.main()


# Layout of a common two-column PDF template after text extraction: a wide run of spaces
# separates the left text from the dates/grade on the right, lines end with "\r", the
# summary has no heading and "ﬁ" is a ligature. (Synthetic data.)
LAYOUT_RESUME = (
    "ASHA KUMAR\r\n"
    "Pune, India  |  asha.k@example.com  |  +91 90000 00000  |  linkedin.com/in/asha-k\r\n"
    "Computer Science undergraduate with practical skills in React and FastAPI web development, cloud with AWS and\r\n"
    "Docker, and machine learning. Looking for a role as a Software Engineer.\r\n"
    "\r\n"
    "EDUCATION\r\n"
    "Example Institute of Technology, Pune" + " " * 60 + "Expected May 2027\r\n"
    "B.Tech, Computer Science" + " " * 70 + "CGPA: 8.4/10\r\n"
    "\r\n"
    "INTERNSHIP EXPERIENCE\r\n"
    "Acme Labs – Software Developer Intern" + " " * 70 + "Jan 2025 – Apr 2025\r\n"
    "Bengaluru, India\r\n"
    " •Built 8 REST APIs in FastAPI for the order service and wrote integration tests for back-\r\n"
    "    end and front-end contracts.\r\n"
    "\r\n"
    "PROJECTS\r\n"
    "Queue Runner" + " " * 80 + "FastAPI, Redis\r\n"
    " •Built a background job runner with retries for reliable, at least\r\n"
    "    once delivery.\r\n"
    "\r\n"
    "PUBLICATIONS\r\n"
    "Smart Parking with Edge SensorsICONIP 2024, Dec 2024\r\n"
    " •Designed the sensor network and the in-\r\n"
    "    formation pipeline.\r\n"
    "\r\n"
    "CERTIFICATIONS\r\n"
    " •Cloud Practitioner Professional Certiﬁcate – Coursera\r\n"
    "\r\n"
    "ACHIEVEMENTS & LEADERSHIP\r\n"
    " •Winner, campus hackathon 2024.\r\n"
    " •President, coding club.\r\n"
)


class TestPdfLayoutParsing(unittest.TestCase):
    def setUp(self):
        self.profile = parse(LAYOUT_RESUME)

    def test_internship_header_with_column_gap_is_found(self):
        self.assertEqual(len(self.profile["internships"]), 1)
        intern = self.profile["internships"][0]
        self.assertEqual((intern["title"], intern["company"]), ("Software Developer Intern", "Acme Labs"))
        self.assertEqual(intern["dates"], "Jan 2025 – Apr 2025")
        self.assertEqual(intern["location"], "Bengaluru, India")
        self.assertEqual(intern["bullets"], [
            "Built 8 REST APIs in FastAPI for the order service and wrote integration tests for backend and front-end contracts."
        ])

    def test_two_line_education_is_one_clean_entry(self):
        self.assertEqual(len(self.profile["education"]), 1)
        edu = self.profile["education"][0]
        self.assertEqual(edu["degree"], "B.Tech, Computer Science")
        self.assertEqual(edu["institution"], "Example Institute of Technology")
        self.assertEqual(edu["location"], "Pune")
        self.assertEqual(edu["dates"], "May 2027")
        self.assertEqual(edu["bullets"], ["CGPA: 8.4/10"])

    def test_wrapped_project_bullet_is_not_a_second_description(self):
        project = self.profile["projects"][0]
        self.assertEqual(project["title"], "Queue Runner")
        self.assertEqual(project["organization"], "FastAPI, Redis")
        self.assertFalse(project.get("description"))
        self.assertEqual(project["bullets"], ["Built a background job runner with retries for reliable, at least once delivery."])

    def test_publication_venue_and_details(self):
        pubs = self.profile["publications"]
        self.assertEqual(len(pubs), 1)
        self.assertEqual(pubs[0]["title"], "Smart Parking with Edge Sensors")
        self.assertEqual(pubs[0]["organization"], "ICONIP 2024")
        self.assertEqual(pubs[0]["dates"], "Dec 2024")
        self.assertEqual(pubs[0]["bullets"], ["Designed the sensor network and the information pipeline."])

    def test_unheaded_summary_ligatures_certifications_and_achievements(self):
        self.assertTrue(self.profile["summary"].startswith("Computer Science undergraduate"))
        self.assertTrue(self.profile["summary"].endswith("Software Engineer."))
        cert = self.profile["certifications"][0]
        self.assertEqual((cert["name"], cert["issuer"]), ("Cloud Practitioner Professional Certificate", "Coursera"))
        self.assertEqual([a["title"] for a in self.profile["achievements"]],
                         ["Winner, campus hackathon 2024.", "President, coding club."])


class TestNoRepeatedContent(unittest.TestCase):
    def test_education_description_restating_the_heading_is_dropped(self):
        from backend.resume_structure import without_repeats
        entry = {"degree": "B.Tech", "institution": "Information Technology CGPA: 8.1/10",
                 "description": "B.Tech in Information Technology, CGPA: 8.1/10", "bullets": []}
        self.assertEqual(without_repeats(entry)["description"], "")

    def test_description_summarising_its_bullets_and_repeated_bullets_are_dropped(self):
        from backend.resume_structure import without_repeats
        entry = {"title": "Queue Runner", "organization": "FastAPI, Redis",
                 "description": "Built a background job runner with retries using FastAPI and Redis.",
                 "bullets": ["Built a background job runner with retries for reliable delivery using FastAPI and Redis.",
                             "Built the background job runner with retries for reliable delivery using FastAPI and Redis.",
                             "Added a dashboard for failed jobs."]}
        cleaned = without_repeats(entry)
        self.assertEqual(cleaned["description"], "")
        self.assertEqual(cleaned["bullets"], [entry["bullets"][0], "Added a dashboard for failed jobs."])

    def test_distinct_description_is_kept(self):
        from backend.resume_structure import without_repeats
        entry = {"title": "Engineer", "organization": "Acme", "description": "Platform team serving 40 internal users.",
                 "bullets": ["Built CI pipelines in GitHub Actions."]}
        self.assertEqual(without_repeats(entry), {**entry})

    def test_exports_never_print_repeats(self):
        service = ResumeGenerationService(PROJECT_ROOT)
        resume = service._validate_and_normalize({}, {
            "education": [{"degree": "B.Tech", "institution": "Example Institute",
                           "description": "B.Tech at Example Institute"}],
        }, {})
        self.assertEqual(resume["education"][0]["description"], "")
        self.assertEqual(service._render_latex(resume).count("Example Institute"), 1)

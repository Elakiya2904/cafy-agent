import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import JobDatabase
from backend.job_intelligence import analysis
from backend.job_intelligence.fetcher import FetchResult, SafeFetcher, host_is_public
from backend.job_intelligence.research import (HiringResearcher, SearchProvider, extract_duration, extract_round_count,
                                               extract_rounds, extract_stage_evidence)
from backend.job_intelligence.service import UNAVAILABLE, JobIntelligenceService
from backend.job_match_analysis_service import analyze_profile_for_job

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
JD = """About the role
You will build and maintain backend services in Python and SQL, working with Docker and AWS.
Responsibilities
- Design and build REST APIs used by our payments products
- Write automated tests and review code from teammates
Requirements
- 3+ years of professional experience with Python
- Bachelor's degree in Computer Science or equivalent practical experience
- Experience with SQL and AWS
Our process: we start with an application review, then a recruiter call, followed by a technical interview with the team. Salary £60,000 - £75,000 per year."""
JOB = {"id": "j1", "company": "Fintechly", "title": "Software Engineer", "description": JD, "url": "https://boards.greenhouse.io/fintechly/jobs/1",
       "location": "London, UK", "extracted_skills": ["Python", "SQL", "Docker", "AWS", "Kubernetes"], "posted_at": "2026-10-01"}
PROFILE = {"candidate_name": "Alex", "skills": ["Python", "SQL", "Docker"],
           "experience": [{"title": "Developer", "company": "Initech", "dates": "2021 - Present", "bullets": ["Built Python APIs backed by SQL databases"]}],
           "projects": [{"title": "Docker Deployer", "description": "Docker based deployment tool"}],
           "education": [{"degree": "BSc Computer Science", "institution": "Leeds"}]}

CAREERS_HTML = """<html><head><title>Fintechly Careers</title><meta name="description" content="Fintechly builds payment software."></head><body>
<h1>Careers at Fintechly</h1><p>Our interview process: a recruiter call, then an online assessment, then a final interview with senior engineers.</p>
<a href="/careers/how-we-hire">How we hire</a></body></html>"""
REVIEW_HTML = """<html><head><title>Fintechly software engineer interview</title><meta property="article:published_time" content="%s"></head>
<body><p>I interviewed at Fintechly for a software engineer role. There was a take-home assignment and then a technical interview.</p></body></html>"""


class FakeFetcher:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url):
        self.calls.append(url)
        for k, v in self.pages.items():
            if url.rstrip("/") == k.rstrip("/"):
                return FetchResult(url, url, 200, v)
        return FetchResult(url, error=None, status=404)


class FakeSearch(SearchProvider):
    name = "fake"

    def __init__(self, results):
        self.results = results

    def search(self, q, count=6):
        return self.results


def make(pages=None, results=None, llm=None, db_path=None):
    db = JobDatabase(db_path=db_path)
    fetcher = FakeFetcher(pages or {})
    researcher = HiringResearcher(fetcher, FakeSearch(results or []) if results is not None else SearchProvider(), now=lambda: NOW, community=lambda company: [])
    return JobIntelligenceService(db, researcher, analyze_profile_for_job, llm=llm, now=lambda: NOW), fetcher


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, self.path)


class EvidenceTests(unittest.TestCase):
    def test_stage_evidence_and_negation(self):
        ev = extract_stage_evidence("Our interview process includes a recruiter call and an online assessment. We do not use a take-home assignment.")
        by = {(e["stage"], e["negated"]) for e in ev}
        self.assertIn(("recruiter_screen", False), by)
        self.assertIn(("online_assessment", False), by)
        self.assertIn(("technical_assessment", True), by)

    def test_no_context_no_stage(self):
        self.assertEqual(extract_stage_evidence("We love our final product launch party."), [])

    def test_ssrf_guard(self):
        self.assertFalse(host_is_public("localhost"))
        self.assertFalse(host_is_public("127.0.0.1"))
        self.assertFalse(host_is_public("169.254.169.254"))
        self.assertEqual(SafeFetcher().get("http://127.0.0.1/admin").error, "blocked_host")
        self.assertEqual(SafeFetcher().get("file:///etc/passwd").error, "invalid_url")


class AnalysisTests(unittest.TestCase):
    def test_role_parsing(self):
        role = analysis.analyze_role(JOB, JOB["extracted_skills"])
        self.assertTrue(any("REST APIs" in r for r in role["responsibilities"]))
        self.assertTrue(any("3+ years" in y for y in role["experience_requirements"]))
        self.assertEqual(role["salary"].replace(" ", "")[:7], "£60,000")
        self.assertEqual(role["source"], "job_description")

    def test_no_description(self):
        role = analysis.analyze_role({"title": "Engineer", "description": ""}, [])
        self.assertFalse(role["has_description"])
        self.assertEqual(role["responsibilities"], [])

    def test_compatibility_never_claims_unsupported(self):
        role = analysis.analyze_role(JOB, JOB["extracted_skills"])
        c = analysis.compatibility(PROFILE, role, {}, ["behavioural_interview"])
        st = {r["requirement"]: r["status"] for r in c["rows"]}
        self.assertEqual(st["Python"], "strong_match")
        self.assertEqual(st["Docker"], "strong_match")
        self.assertEqual(st["AWS"], "missing_evidence")
        self.assertEqual(st["Kubernetes"], "missing_evidence")
        self.assertIn("AWS", c["missing_skills"])
        self.assertTrue(any(r["kind"] == "behavioural" for r in c["rows"]))
        self.assertEqual(analysis.compatibility(None, role, {}, [])["available"], False)


class ServiceTests(Base):
    def run_job(self, **kw):
        svc, fetcher = make(**{**kw, "db_path": self.path})
        return svc, fetcher, svc.get("c1", JOB, PROFILE)

    def test_no_evidence_means_no_fabricated_process(self):
        job = {**JOB, "description": "We need a software engineer to write Python code."}
        svc, _ = make(db_path=self.path)
        out = svc.get("c1", job, PROFILE)
        self.assertEqual(out["hiring_process"]["stages"], [])
        self.assertFalse(out["hiring_process"]["available"])
        self.assertEqual(out["hiring_process"]["message"], UNAVAILABLE)
        self.assertTrue(any("search provider" in n for n in out["hiring_process"]["notes"]))
        self.assertTrue(out["interview_preparation"]["practice_questions"])  # prep guidance is still given

    def test_job_posting_is_official_role_specific_evidence(self):
        _, _, out = self.run_job()
        stages = {s["stage_key"]: s for s in out["hiring_process"]["stages"]}
        self.assertEqual(set(stages), {"application_screening", "recruiter_screen", "technical_interview"})
        for s in stages.values():
            self.assertEqual((s["status"], s["scope"]), ("officially_confirmed", "role_specific"))
            self.assertTrue(s["sources"] and s["sources"][0]["evidence"])
            self.assertEqual(s["sources"][0]["last_verified"][:10], "2026-10-30")

    def test_official_pages_and_public_reports_classified(self):
        pages = {"https://www.fintechly.com": CAREERS_HTML, "https://www.fintechly.com/careers": CAREERS_HTML,
                 "https://reviews.example.org/fintechly": REVIEW_HTML % "2026-03-01"}
        results = [{"url": "https://reviews.example.org/fintechly", "title": "Fintechly interview", "snippet": "", "published": None},
                   {"url": "https://other.example.org/wrong", "title": "Acme interview", "snippet": "Acme online assessment", "published": None}]
        job = {**JOB, "company_website": "https://www.fintechly.com"}
        svc, _ = make(pages, results, db_path=self.path)
        out = svc.get("c1", job, PROFILE)
        st = {s["stage_key"]: s for s in out["hiring_process"]["stages"]}
        self.assertEqual(st["online_assessment"]["status"], "officially_confirmed")   # official careers page
        self.assertEqual(st["online_assessment"]["scope"], "company_wide")
        self.assertEqual(st["technical_assessment"]["status"], "publicly_reported")   # review, engineer role matches
        self.assertEqual(st["final_interview"]["status"], "officially_confirmed")
        urls = {s["url"] for x in st.values() for s in x["sources"]}
        self.assertNotIn("https://other.example.org/wrong", urls)                      # wrong company rejected
        self.assertTrue(any(c["type"] == "rejected_wrong_company" for c in out["sources"]["checked"]))
        self.assertTrue(out["company_overview"]["website_verified"])

    def test_outdated_report_downgraded_to_estimated(self):
        pages = {"https://reviews.example.org/f": REVIEW_HTML % "2019-01-01"}
        results = [{"url": "https://reviews.example.org/f", "title": "t", "snippet": "", "published": None}]
        svc, _ = make(pages, results, db_path=self.path)
        out = svc.get("c1", {**JOB, "description": "Write code."}, PROFILE)
        st = {s["stage_key"]: s for s in out["hiring_process"]["stages"]}
        self.assertEqual(st["technical_assessment"]["status"], "estimated")
        self.assertTrue(st["technical_assessment"]["sources"][0]["published"] == "2019-01-01")

    def test_conflicting_reports_flagged(self):
        pages = {"https://r.example.org/a": REVIEW_HTML % "2026-05-01",
                 "https://r.example.org/b": "<html><body><p>At Fintechly there is no take-home assignment in the interview process.</p></body></html>"}
        results = [{"url": u, "title": "", "snippet": "", "published": "2026-05-01"} for u in pages]
        svc, _ = make(pages, results, db_path=self.path)
        out = svc.get("c1", {**JOB, "description": "Write code."}, PROFILE)
        st = {s["stage_key"]: s for s in out["hiring_process"]["stages"]}
        self.assertTrue(st["technical_assessment"]["conflict"])

    def test_company_info_reused_across_jobs_and_hiring_cached(self):
        svc, fetcher = make(db_path=self.path)
        svc.get("c1", JOB, PROFILE)
        out2 = svc.get("c1", {**JOB, "id": "j2", "title": "Data Engineer"}, PROFILE)
        self.assertTrue(out2["reuse"]["company_reused"])
        self.assertFalse(out2["reuse"]["hiring_reused"])      # role-specific info is separate
        out3 = svc.get("c1", JOB, PROFILE)
        self.assertTrue(out3["reuse"]["hiring_reused"])
        out4 = svc.get("c1", JOB, PROFILE, refresh=True)
        self.assertFalse(out4["reuse"]["hiring_reused"])

    def test_unavailable_site_is_reported_not_invented(self):
        svc, _ = make(db_path=self.path)
        out = svc.get("c1", {**JOB, "company_website": "https://www.fintechly.com"}, PROFILE)
        co = out["company_overview"]
        self.assertFalse(co["website_verified"])
        self.assertIsNone(co["official_website"])
        self.assertIn("products_and_services", co["unavailable"])
        self.assertTrue(co["notes"])

    def test_llm_interpretation_labelled_and_optional(self):
        svc, _ = make(db_path=self.path, llm=lambda j, r: {"typical_day": "Likely coding.", "why_role_exists": "Likely growth."})
        out = svc.get("c1", JOB, PROFILE)
        self.assertEqual(out["role_overview"]["interpretation"]["source"], "ai_interpretation")
        def boom(j, r): raise RuntimeError("x")
        svc2, _ = make(db_path=self.path + "2", llm=boom)
        self.addCleanup(lambda: os.path.exists(self.path + "2") and os.remove(self.path + "2"))
        self.assertIsNone(svc2.get("c1", {**JOB, "id": "j9"}, PROFILE)["role_overview"]["interpretation"])

    def test_no_profile_and_reports(self):
        svc, _ = make(db_path=self.path)
        out = svc.get("c1", JOB, None)
        self.assertFalse(out["candidate_compatibility"]["available"])
        self.assertTrue(out["role_overview"]["required_skills"])
        svc.report_issue("c1", "j1", "hiring_process", "Wrong stage", "technical_interview")
        self.assertEqual(svc._one("SELECT COUNT(*) AS n FROM intelligence_reports")["n"], 1)

    def test_candidate_preparation_stored_per_candidate(self):
        svc, _ = make(db_path=self.path)
        svc.get("c1", JOB, PROFILE)
        row = svc._one("SELECT * FROM candidate_preparation WHERE candidate_id='c1' AND job_id='j1'")
        self.assertIn("AWS", row["missing_skills"])
        self.assertIsNone(svc._one("SELECT * FROM candidate_preparation WHERE candidate_id='c2'"))


if __name__ == "__main__":
    unittest.main()


class RoundExtractionTests(unittest.TestCase):
    def test_numbered_rounds_map_to_known_stages_and_keep_repeats(self):
        rounds = extract_rounds("Step 1: Recruiter Call\nStep 2: Technical Phone Screen\nStep 3: Second Recruiter Call\nStep 4: Onsite")
        self.assertEqual([r["stage"] for r in rounds],
                         ["recruiter_screen", "technical_interview", "custom:second-recruiter-call", "final_interview"])
        self.assertEqual(rounds[2]["after"], "recruiter_screen")

    def test_unknown_named_round_becomes_company_specific_round(self):
        rounds = extract_rounds("Round 4: Meet the founders chat")
        self.assertEqual(rounds[0]["stage"], "custom:meet-the-founders-chat")
        self.assertEqual(rounds[0]["label"], "Meet the founders chat")

    def test_non_round_lines_are_ignored(self):
        self.assertEqual(extract_rounds("1. Buy milk and eggs from the shop"), [])

    def test_duration_and_round_count(self):
        self.assertEqual(extract_duration("a 45-minute call"), "45 min")
        self.assertEqual(extract_duration("lasts 45 to 60 minutes"), "45–60 min")
        self.assertEqual(extract_round_count("The interview process has five rounds in total."), 5)
        self.assertIsNone(extract_round_count("We conduct two interviews."))


class CompanyProfileTests(Base):
    def test_public_profile_fills_missing_company_facts(self):
        profile = {"website": "https://www.example-co.com", "industry": "Travel", "headquarters": "Needham, United States",
                   "company_size": "Large company (about 2,909 employees)", "overview": "Example Co runs travel sites.",
                   "source_url": "https://www.wikidata.org/wiki/Q1"}
        svc, _ = make(db_path=self.path)
        svc.profile_fn = lambda company: profile
        co = svc.company_intelligence("Example Co", {"company": "Example Co"})
        self.assertEqual((co["industry"], co["headquarters"]), ("Travel", "Needham, United States"))
        self.assertIn("2,909", co["company_size"])
        self.assertEqual(co["overview"], "Example Co runs travel sites.")
        self.assertEqual(co["overview_source"], "Wikipedia")
        self.assertTrue(any("Wikidata" in n for n in co["notes"]))

    def test_profile_lookup_failure_is_reported_not_raised(self):
        svc, _ = make(db_path=self.path)
        def boom(company):
            raise RuntimeError("down")
        svc.profile_fn = boom
        co = svc.company_intelligence("Example Co", {"company": "Example Co"})
        self.assertTrue(any("lookup failed" in n for n in co["notes"]))

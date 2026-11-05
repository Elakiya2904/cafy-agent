import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import JobDatabase
from backend.email_agent.service import EmailAgentService
from backend.job_applications import mapper
from backend.job_applications.service import ApplicationError, JobApplicationService
from backend.job_applications.verifier import verify_submission

C = "cand-1"
PROFILE = {"candidate_name": "Alex Candidate Smith", "email": "alex@example.com", "phone": "+44 7700 900000",
           "linkedin": "linkedin.com/in/alex", "skills": ["Python", "Docker"],
           "education": [{"institution": "Uni of Leeds", "degree": "BSc Computer Science"}],
           "experience": [{"title": "Developer", "company": "Initech", "bullets": ["Built APIs in Python"]}], "certifications": []}
JOB = {"id": "job1", "company": "Acme", "title": "Software Engineer", "platform": "greenhouse", "location": "London, UK",
       "url": "https://boards.greenhouse.io/acme/jobs/1234567", "description": "Build things with Python."}

FIELDS = [
    {"key": "first_name", "label": "First Name", "type": "text", "required": True},
    {"key": "last_name", "label": "Last Name", "type": "text", "required": True},
    {"key": "email", "label": "Email", "type": "email", "required": True},
    {"key": "phone", "label": "Phone", "type": "tel", "required": False},
    {"key": "resume", "label": "Resume/CV", "type": "file", "required": True},
    {"key": "why", "label": "Why do you want to work at Acme?", "type": "textarea", "required": True},
    {"key": "visa", "label": "Do you require visa sponsorship?", "type": "select", "required": True, "options": ["Yes", "No"]},
]
CONFIRM = {"confirmation_text": "Thank you for applying! Your application has been submitted. Application ID: ACME-99871", "confirmation_url": "https://x/confirmation"}


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, self.path)
        self.db = JobDatabase(db_path=self.path)
        self.profile = dict(PROFILE)
        self.handed = []
        self.answer = lambda q, p, j: "I enjoy building Python services and my work at Initech built APIs, which fits the Software Engineer role at Acme."
        self.svc = JobApplicationService(
            self.db, lambda: self.profile, lambda: {"path": __file__, "filename": "cv.pdf", "content_type": "application/pdf"},
            lambda jid: JOB if jid == "job1" else None, lambda q, p, j: self.answer(q, p, j),
            lambda c, payload: self.handed.append(payload), now=lambda: datetime(2026, 10, 30, 10, 30, tzinfo=timezone.utc))

    def start(self):
        return self.svc.start(C, "job1")["application"]["id"]

    def ready(self, app_id):
        """Detect form, answer everything, grant + report upload; returns review."""
        rev = self.svc.detect_form(C, app_id, {"ats": "greenhouse", "fields": FIELDS})
        by = {f["field_key"]: f for f in rev["fields"]}
        self.svc.edit_field(C, app_id, by["visa"]["id"], "No")
        self.svc.approve_field(C, app_id, by["why"]["id"])
        self.svc.set_document_permission(C, app_id, "resume", True)
        doc = self.svc.documents(app_id)[0]
        return self.svc.report_document(C, app_id, doc["id"], "uploaded", None)


class MapperTests(unittest.TestCase):
    def test_classification(self):
        c = mapper.classify_field
        self.assertEqual(c({"label": "First Name"}), "first_name")
        self.assertEqual(c({"label": "Surname"}), "last_name")
        self.assertEqual(c({"label": "Mobile number"}), "phone")
        self.assertEqual(c({"label": "Upload your CV", "type": "file"}), "document:resume")
        self.assertEqual(c({"label": "Are you legally authorized to work in the UK?"}), "sensitive")
        self.assertEqual(c({"label": "What is your expected salary?"}), "sensitive")
        self.assertEqual(c({"label": "Why do you want to work here?", "type": "textarea"}), "open_question")
        self.assertEqual(c({"label": "Favourite colour"}), "unknown")

    def test_no_invented_values(self):
        m = mapper.map_field({"label": "Location", "type": "text"}, PROFILE)  # profile has no location
        self.assertIsNone(m["value"])
        self.assertEqual(m["completion_status"], "needs_input")
        m = mapper.map_field({"label": "Country", "name": "location", "options": ["France", "Spain"]}, {**PROFILE, "location": "London, UK"})
        self.assertIsNone(m["value"])


class VerifierTests(unittest.TestCase):
    def test_click_alone_is_not_submitted(self):
        self.assertEqual(verify_submission({"clicked_at": "x"})["result"], "confirmation_pending")

    def test_confirmation_and_reference(self):
        v = verify_submission(CONFIRM)
        self.assertEqual((v["result"], v["reference"]), ("submitted", "ACME-99871"))

    def test_validation_errors_fail_even_with_thank_you_text(self):
        self.assertEqual(verify_submission({**CONFIRM, "validation_errors": ["Email is invalid"]})["result"], "submission_failed")

    def test_form_still_present_not_confirmed(self):
        self.assertNotEqual(verify_submission({**CONFIRM, "form_still_present": True})["result"], "submitted")


class FlowTests(Base):
    def test_start_requires_profile_and_prevents_duplicates(self):
        self.profile = None
        with self.assertRaises(ApplicationError):
            self.svc.start(C, "job1")
        self.profile = dict(PROFILE)
        first = self.svc.start(C, "job1")
        self.assertFalse(first["resumed"])
        again = self.svc.start(C, "job1")
        self.assertTrue(again["resumed"])
        self.assertEqual(again["application"]["id"], first["application"]["id"])
        self.assertEqual(len(self.svc.list_applications(C)), 1)

    def test_autofill_mapping_and_unknowns_flagged(self):
        rev = self.svc.detect_form(C, self.start(), {"ats": "greenhouse", "fields": FIELDS})
        by = {f["field_key"]: f for f in rev["fields"]}
        self.assertEqual((by["first_name"]["field_value"], by["last_name"]["field_value"]), ("Alex", "Candidate Smith"))
        self.assertEqual(by["email"]["field_source"], "profile")
        self.assertIsNone(by["visa"]["field_value"])           # sensitive: never auto-answered
        self.assertEqual(by["why"]["field_source"], "ai_suggestion")
        self.assertEqual(by["why"]["completion_status"], "awaiting_review")
        self.assertTrue(rev["blockers"])
        self.assertEqual(rev["application"]["status"], "in_progress")

    def test_fabricated_numbers_in_ai_answer_discarded(self):
        self.answer = lambda q, p, j: "I have 12 years of experience and increased revenue by 300%."
        rev = self.svc.detect_form(C, self.start(), {"fields": FIELDS})
        why = next(f for f in rev["fields"] if f["field_key"] == "why")
        self.assertIsNone(why["field_value"])
        self.assertEqual(why["completion_status"], "needs_input")

    def test_generator_failure_does_not_block(self):
        def boom(q, p, j): raise RuntimeError("down")
        self.answer = boom
        rev = self.svc.detect_form(C, self.start(), {"fields": FIELDS})
        self.assertEqual(next(f for f in rev["fields"] if f["field_key"] == "why")["completion_status"], "needs_input")

    def test_unsupported_form(self):
        app_id = self.start()
        with self.assertRaises(ApplicationError):
            self.svc.detect_form(C, app_id, {"fields": []})
        self.assertEqual(self.svc.review(C, app_id)["application"]["blocked_reason"], "unsupported_form")

    def test_resume_requires_permission(self):
        app_id = self.start()
        self.svc.detect_form(C, app_id, {"fields": FIELDS})
        with self.assertRaises(ApplicationError) as cm:
            self.svc.resume_file(C, app_id)
        self.assertEqual(cm.exception.status, 403)
        doc = self.svc.documents(app_id)[0]
        with self.assertRaises(ApplicationError):
            self.svc.report_document(C, app_id, doc["id"], "uploaded", None)
        self.svc.set_document_permission(C, app_id, "resume", True)
        self.assertEqual(self.svc.resume_file(C, app_id)["filename"], "cv.pdf")

    def test_cannot_approve_until_everything_reviewed(self):
        app_id = self.start()
        self.svc.detect_form(C, app_id, {"fields": FIELDS})
        with self.assertRaises(ApplicationError) as cm:
            self.svc.approve(C, app_id)
        self.assertEqual(cm.exception.status, 409)
        self.assertFalse(self.svc.submit_permission(C, app_id)["allowed"])

    def test_full_happy_path_with_handoff(self):
        app_id = self.start()
        rev = self.ready(app_id)
        self.assertEqual(rev["application"]["status"], "ready_for_review")
        self.assertFalse(self.svc.submit_permission(C, app_id)["allowed"])  # not yet approved
        self.svc.approve(C, app_id)
        self.assertTrue(self.svc.submit_permission(C, app_id)["allowed"])
        res = self.svc.record_submission(C, app_id, CONFIRM)
        self.assertEqual(res["result"], "submitted")
        app = self.svc.detail(C, app_id)
        self.assertEqual(app["application"]["external_reference_id"], "ACME-99871")
        self.assertTrue(app["application"]["applied_at"])
        self.assertEqual(self.handed[0]["application_status"], "submitted")
        self.assertEqual(self.handed[0]["source"], "Greenhouse")
        # duplicate submission report is ignored; duplicate start is refused
        self.assertTrue(self.svc.record_submission(C, app_id, CONFIRM)["duplicate"])
        self.assertEqual(len(self.svc.detail(C, app_id)["submissions"]), 1)
        self.assertEqual(len(self.handed), 1)
        with self.assertRaises(ApplicationError) as cm:
            self.svc.start(C, "job1")
        self.assertEqual(cm.exception.status, 409)

    def test_edit_after_approval_revokes_it(self):
        app_id = self.start()
        rev = self.ready(app_id)
        self.svc.approve(C, app_id)
        fid = next(f["id"] for f in rev["fields"] if f["field_key"] == "phone")
        self.svc.edit_field(C, app_id, fid, "+44 1")
        self.assertFalse(self.svc.submit_permission(C, app_id)["allowed"])

    def test_submission_without_approval_rejected(self):
        app_id = self.start()
        self.ready(app_id)
        with self.assertRaises(ApplicationError) as cm:
            self.svc.record_submission(C, app_id, CONFIRM)
        self.assertEqual(cm.exception.status, 403)
        self.assertEqual(self.handed, [])

    def test_click_without_confirmation_is_pending_not_submitted(self):
        app_id = self.start()
        self.ready(app_id)
        self.svc.approve(C, app_id)
        res = self.svc.record_submission(C, app_id, {"clicked_at": "2026-10-30T10:31:00Z"})
        self.assertEqual(res["result"], "confirmation_pending")
        self.assertEqual(self.handed, [])
        self.assertFalse(self.svc.submit_permission(C, app_id)["allowed"])
        self.svc.confirm_submitted(C, app_id)  # candidate verifies manually
        self.assertEqual(self.handed[0]["application_status"], "submitted")

    def test_failed_submission_and_retry_needs_reapproval(self):
        app_id = self.start()
        self.ready(app_id)
        self.svc.approve(C, app_id)
        res = self.svc.record_submission(C, app_id, {"validation_errors": ["Phone is invalid"]})
        self.assertEqual(res["result"], "submission_failed")
        self.svc.retry(C, app_id)
        self.assertFalse(self.svc.submit_permission(C, app_id)["allowed"])
        self.assertEqual(self.handed, [])

    def test_captcha_pauses_and_blocks_until_cleared(self):
        app_id = self.start()
        self.ready(app_id)
        self.svc.approve(C, app_id)
        res = self.svc.record_submission(C, app_id, {"captcha": True})
        self.assertTrue(res["paused"])
        self.assertFalse(self.svc.submit_permission(C, app_id)["allowed"])
        self.svc.resume_after_block(C, app_id)
        self.svc.approve(C, app_id)
        self.assertEqual(self.svc.record_submission(C, app_id, CONFIRM)["result"], "submitted")

    def test_upload_failure_blocks_approval(self):
        app_id = self.start()
        self.ready(app_id)
        doc = self.svc.documents(app_id)[0]
        self.svc.report_document(C, app_id, doc["id"], "failed", "file too large")
        with self.assertRaises(ApplicationError):
            self.svc.approve(C, app_id)

    def test_scoping_filters_and_lookup(self):
        app_id = self.start()
        with self.assertRaises(ApplicationError):
            self.svc.review("other", app_id)
        self.assertEqual(self.svc.list_applications("other"), [])
        self.assertEqual(len(self.svc.list_applications(C, company="acm")), 1)
        self.assertEqual(self.svc.list_applications(C, company="zzz"), [])
        self.assertEqual(self.svc.lookup_by_url(C, "https://job-boards.greenhouse.io/acme/jobs/1234567?gh_src=x")[0]["id"], app_id)
        self.assertEqual(self.svc.lookup_by_url(C, "https://boards.greenhouse.io/other/jobs/999"), [])
        self.svc.cancel(C, app_id)
        self.assertEqual(self.svc.lookup_by_url(C, JOB["url"]), [])

    def test_pipeline3_integration(self):
        email = EmailAgentService(self.db, {}, secret="s")
        self.svc.on_submitted = lambda c, p: email.upsert_application(c, p["company"], p["job_title"], p.get("job_id"), p["applied_at"], None, p["reference_id"])
        app_id = self.start()
        self.ready(app_id)
        self.svc.approve(C, app_id)
        self.svc.record_submission(C, app_id, CONFIRM)
        apps = email.list_applications(C)
        self.assertEqual((apps[0]["company"], apps[0]["application_ref"]), ("Acme", "ACME-99871"))


if __name__ == "__main__":
    unittest.main()

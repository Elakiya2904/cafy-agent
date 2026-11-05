import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("EMAIL_AGENT_SECRET", "test-secret")

from backend.database import JobDatabase
from backend.email_agent import classifier as clf
from backend.email_agent.providers import BaseProvider, ProviderAuthError, ProviderError
from backend.email_agent.monitor import EmailMonitor
from backend.email_agent.service import AgentError, EmailAgentService

C = "cand-1"
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


class FakeProvider(BaseProvider):
    name = "gmail"

    def __init__(self):
        super().__init__("id", "secret")
        self.sent, self.events, self.busy, self.inbox = [], [], [], []
        self.fail_send = self.fail_event = self.fail_refresh = self.fail_calendar = False
        self.revoked = []

    def authorization_url(self, redirect_uri, state):
        return f"https://auth.example/?state={state}"

    def exchange_code(self, code, redirect_uri):
        return {"access_token": "at", "refresh_token": "rt", "token_expires_at": (NOW + timedelta(hours=1)).isoformat(),
                "scopes": "x", "email": "me@example.com", "display_name": "Alex Candidate"}

    def refresh(self, refresh_token):
        if self.fail_refresh:
            raise ProviderAuthError("invalid_grant")
        return {"access_token": "at2", "refresh_token": refresh_token, "token_expires_at": (NOW + timedelta(hours=1)).isoformat()}

    def revoke(self, token): self.revoked.append(token)
    def list_messages(self, token, since, limit=50): return list(self.inbox)

    def send_email(self, token, to, subject, body, thread_id):
        if self.fail_send:
            raise ProviderError("smtp down")
        self.sent.append((to, subject, body))
        return "sent-1"

    def busy_intervals(self, token, start, end, email):
        if self.fail_calendar:
            raise ProviderError("calendar down")
        return self.busy

    def create_event(self, token, ev):
        if self.fail_event:
            raise ProviderError("cal write failed")
        self.events.append(ev)
        return "evt-1"


def mail(i, sender, subject, body, thread="t1", **kw):
    return {"message_id": f"m{i}", "thread_id": thread, "sender": sender, "subject": subject, "body": body,
            "received_at": (NOW - timedelta(hours=1)).isoformat(), "labels": [], **kw}


INVITE = ("Hi Alex, we would like to invite you to a technical interview for the Software Engineer role at Acme. "
          "Date: 5 November 2026 at 10:30 AM GMT. Duration: 45 minutes on Google Meet https://meet.google.com/abc-defg-hij.")


class EmailAgentTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, self.path)
        self.prov = FakeProvider()
        self.svc = EmailAgentService(JobDatabase(db_path=self.path), {"gmail": self.prov}, secret="s", now=lambda: NOW)
        url = self.svc.start_oauth(C, "gmail", "http://x/cb")
        state = url.split("state=")[1]
        self.acc = self.svc.complete_oauth("gmail", "code", state, "http://x/cb")
        self.app = self.svc.upsert_application(C, "Acme", "Software Engineer", "job1", (NOW - timedelta(days=10)).isoformat())

    def ingest(self, raw):
        acc = self.svc._account(C, self.acc["id"])
        return self.svc.ingest_message(C, acc, raw)

    def status(self):
        return self.svc._application(C, self.app["id"])["status"]

    # -- classification / matching
    def test_classifier_extracts_without_inventing(self):
        cat, conf = clf.classify("Interview Invitation – Software Engineer", INVITE)
        self.assertEqual(cat, "interview_invitation")
        d = clf.extract_details("Interview Invitation", INVITE, cat, "Sam <sam@acme.com>")
        self.assertEqual((d["interview_date"], d["interview_time"], d["duration_minutes"]), ("2026-11-05", "10:30", 45))
        self.assertEqual(d["platform"], "Google Meet")
        d2 = clf.extract_details("Interview", "We'd like to invite you to an interview next week.", cat, "a@b.com")
        self.assertIsNone(d2["interview_date"])
        self.assertIn("interview_time", clf.missing_interview_fields(d2))

    def test_promotions_not_job_related(self):
        r = self.ingest(mail(1, "Deals <offers@shop.com>", "50% off sale ends today", "unsubscribe here", thread="p"))
        self.assertFalse(r["job_related"])
        self.assertEqual(self.svc.dashboard(C)["inbox"], [])

    def test_status_updates_only_when_clear(self):
        self.ingest(mail(1, "Sam <sam@acme.com>", "Application received – Software Engineer",
                         "Thank you for applying for the Software Engineer role at Acme."))
        self.assertEqual(self.status(), "applied")
        self.ingest(mail(2, "Sam <sam@acme.com>", "Update", "We regret to inform you we will not be moving forward with your application at Acme.", thread="t2"))
        self.assertEqual(self.status(), "rejected")
        # a late acknowledgement must not move it back
        self.ingest(mail(3, "Sam <sam@acme.com>", "Application received", "We have received your application at Acme.", thread="t3"))
        self.assertEqual(self.status(), "rejected")

    def test_ambiguous_match_requires_confirmation_and_changes_nothing(self):
        other = self.svc.upsert_application(C, "Acme", "Data Engineer", "job2", NOW.isoformat())
        r = self.ingest(mail(1, "Sam <sam@acme.com>", "Your application", "We regret to inform you that we will not be moving forward with your application at Acme."))
        self.assertEqual(r["processing_status"], "needs_confirmation")
        self.assertEqual(self.status(), "applied")
        res = self.svc.confirm_match(C, r["message_row_id"], other["id"])
        self.assertEqual(res["processing_status"], "processed")
        self.assertEqual(self.svc._application(C, other["id"])["status"], "rejected")
        self.assertEqual(self.status(), "applied")

    def test_duplicate_messages_ignored(self):
        raw = mail(1, "Sam <sam@acme.com>", "Application received", "Thank you for applying to Acme.")
        self.assertFalse(self.ingest(raw).get("duplicate"))
        self.assertTrue(self.ingest(raw).get("duplicate"))
        self.assertTrue(self.ingest({**raw, "message_id": "other-id"}).get("duplicate"))

    # -- interviews / HITL / calendar
    def invite(self):
        r = self.ingest(mail(1, "Sam Recruiter <sam@acme.com>", "Interview Invitation – Software Engineer", INVITE))
        return self.svc.list_interviews(C)[0], r

    def test_interview_extracted_and_status_interview(self):
        iv, _ = self.invite()
        self.assertEqual((iv["interview_date"], iv["interview_time"], iv["timezone"]), ("2026-11-05", "10:30", "Europe/London"))
        self.assertEqual(self.status(), "interview")
        self.assertEqual(iv["scheduling_status"], "invitation_received")
        self.assertEqual(self.prov.sent, [])

    def test_nothing_sent_without_approval_and_failure_not_marked_sent(self):
        iv, _ = self.invite()
        d = self.svc.prepare_interview_reply(C, iv["id"], "accept")
        self.assertEqual((d["approval_status"], d["send_status"]), ("pending", "unsent"))
        self.assertEqual(self.prov.sent, [])
        self.prov.fail_send = True
        with self.assertRaises(AgentError) as cm:
            self.svc.approve_and_send(C, d["id"])
        self.assertIn("NOT sent", str(cm.exception))
        self.assertEqual(self.svc._draft(C, d["id"])["send_status"], "failed")
        self.prov.fail_send = False
        out = self.svc.approve_and_send(C, d["id"], body="Edited body")
        self.assertEqual(out["send_status"], "sent")
        self.svc.approve_and_send(C, d["id"])  # idempotent
        self.assertEqual(len(self.prov.sent), 1)
        self.assertEqual(self.prov.sent[0][2], "Edited body")

    def test_rejected_draft_cannot_send(self):
        iv, _ = self.invite()
        d = self.svc.prepare_interview_reply(C, iv["id"], "accept")
        self.svc.reject_draft(C, d["id"])
        with self.assertRaises(AgentError):
            self.svc.approve_and_send(C, d["id"])
        self.assertEqual(self.prov.sent, [])

    def test_conflict_blocks_accept_and_event(self):
        self.prov.busy = [{"start": datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc), "end": datetime(2026, 11, 5, 11, 0, tzinfo=timezone.utc)}]
        iv, _ = self.invite()
        self.assertEqual(iv["scheduling_status"], "conflict")
        self.assertTrue(iv["conflicts"] and iv["proposed_slots"])
        with self.assertRaises(AgentError) as cm:
            self.svc.prepare_interview_reply(C, iv["id"], "accept")
        self.assertEqual(cm.exception.status, 409)
        with self.assertRaises(AgentError) as cm:
            self.svc.confirm_interview(C, iv["id"])
        self.assertEqual(cm.exception.status, 409)
        self.assertEqual(self.prov.events, [])

    def test_confirm_creates_event_with_reminders(self):
        iv, _ = self.invite()
        res = self.svc.confirm_interview(C, iv["id"])
        self.assertEqual(res["interview"]["scheduling_status"], "scheduled")
        ev = self.prov.events[0]
        self.assertEqual((ev["start"], ev["timezone"]), ("2026-11-05T10:30:00", "Europe/London"))
        self.assertIn("meet.google.com", ev["description"])
        self.assertEqual(ev["reminder_minutes"], [1440, 60])

    def test_calendar_failure_not_marked_scheduled(self):
        iv, _ = self.invite()
        self.prov.fail_event = True
        with self.assertRaises(AgentError):
            self.svc.confirm_interview(C, iv["id"])
        self.assertEqual(self.svc.list_interviews(C)[0]["scheduling_status"], "calendar_failed")

    def test_unreadable_calendar_never_assumed_free(self):
        iv, _ = self.invite()
        self.prov.fail_calendar = True
        with self.assertRaises(AgentError):
            self.svc.confirm_interview(C, iv["id"])
        self.assertEqual(self.prov.events, [])

    def test_missing_details_reported_not_invented(self):
        self.ingest(mail(1, "Sam <sam@acme.com>", "Interview Invitation – Software Engineer",
                         "We would like to invite you to an interview for the Software Engineer role at Acme. Please confirm your availability."))
        iv = self.svc.list_interviews(C)[0]
        self.assertIsNone(iv["interview_date"])
        self.assertIn("interview_date", iv["missing_fields"])
        self.assertEqual(iv["scheduling_status"], "awaiting_slot_approval")
        self.assertTrue(iv["proposed_slots"])
        with self.assertRaises(AgentError):
            self.svc.confirm_interview(C, iv["id"])

    def test_recruiter_reschedule_after_scheduled_does_not_touch_calendar(self):
        iv, _ = self.invite()
        self.svc.confirm_interview(C, iv["id"])
        self.ingest(mail(2, "Sam <sam@acme.com>", "Interview rescheduled", "We need to reschedule your interview at Acme to 6 November 2026 at 2:00 PM GMT."))
        iv = self.svc.list_interviews(C)[0]
        self.assertEqual((iv["scheduling_status"], iv["interview_date"], iv["interview_time"]), ("rescheduled_by_recruiter", "2026-11-06", "14:00"))
        self.assertEqual(len(self.prov.events), 1)

    # -- follow-ups
    def test_follow_up_flow(self):
        drafts = self.svc.scan_follow_ups(C)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(self.svc.scan_follow_ups(C), [])  # no duplicates while pending
        d = drafts[0]
        with self.assertRaises(AgentError) as cm:
            self.svc.approve_and_send(C, d["id"])  # recruiter address unknown
        self.assertEqual(cm.exception.status, 422)
        self.svc.approve_and_send(C, d["id"], to_email="jobs@acme.com")
        self.assertEqual(self.svc.scan_follow_ups(C), [])  # inside the gap
        self.assertEqual(len(self.prov.sent), 1)

    def test_recruiter_reply_stops_follow_up(self):
        d = self.svc.scan_follow_ups(C)[0]
        self.ingest(mail(1, "Sam <sam@acme.com>", "Your application", "Could you please provide your CV for the Software Engineer role at Acme?"))
        self.assertEqual(self.svc._draft(C, d["id"])["approval_status"], "superseded")
        self.assertEqual(self.svc.scan_follow_ups(C), [])

    # -- accounts / tokens / scoping
    def test_expired_token_marks_account_and_logs(self):
        self.svc._update("connected_email_accounts", self.acc["id"], token_expires_at=(NOW - timedelta(hours=1)).isoformat())
        self.prov.fail_refresh = True
        with self.assertRaises(AgentError) as cm:
            self.svc.sync_account(C, self.acc["id"])
        self.assertEqual(cm.exception.status, 401)
        self.assertEqual(self.svc.list_accounts(C)[0]["status"], "expired")

    def test_disconnect_wipes_tokens(self):
        self.svc.disconnect_account(C, self.acc["id"])
        row = self.svc._one("SELECT * FROM connected_email_accounts WHERE id=?", (self.acc["id"],))
        self.assertEqual((row["status"], row["access_token"], row["refresh_token"]), ("disconnected", None, None))
        self.assertEqual(self.prov.revoked, ["rt"])
        with self.assertRaises(AgentError):
            self.svc.sync_account(C, self.acc["id"])

    def test_sync_ingests_and_candidate_scoping(self):
        self.prov.inbox = [mail(1, "Sam <sam@acme.com>", "Application received", "Thank you for applying for the Software Engineer role at Acme.")]
        stats = self.svc.sync_account(C, self.acc["id"])
        self.assertEqual(stats["job_related"], 1)
        self.assertEqual(self.svc.sync_account(C, self.acc["id"])["duplicates"], 1)
        with self.assertRaises(AgentError):
            self.svc.sync_account("someone-else", self.acc["id"])
        self.assertEqual(self.svc.dashboard("someone-else")["inbox"], [])
        self.assertTrue(self.svc.logs(C))

    def test_oauth_state_tampering_rejected(self):
        with self.assertRaises(AgentError):
            self.svc.complete_oauth("gmail", "code", "bogus.state", "http://x/cb")

    # -- background monitor
    def test_monitor_syncs_accounts_and_drafts_follow_ups_without_sending(self):
        self.prov.inbox = [mail(1, "Sam <sam@acme.com>", "Application received – Software Engineer",
                                "Thank you for applying for the Software Engineer role at Acme.")]
        monitor = EmailMonitor(self.svc, interval_minutes=1)
        stats = monitor.poll_once()
        self.assertEqual((stats["accounts"], stats["synced"], stats["failed"]), (1, 1, 0))
        self.assertEqual(len(self.svc.dashboard(C)["inbox"]), 1)
        self.assertEqual(stats["follow_up_drafts"], 1)  # applied 10 days ago, no recruiter reply
        self.assertEqual(self.prov.sent, [])  # drafts only; sending needs approval

    def test_monitor_isolates_failures_and_skips_disconnected(self):
        self.prov.fail_refresh = True
        acc = self.svc._account(C, self.acc["id"])
        self.svc._update("connected_email_accounts", acc["id"], token_expires_at=(NOW - timedelta(hours=1)).isoformat())
        stats = EmailMonitor(self.svc, interval_minutes=1).poll_once()
        self.assertEqual((stats["synced"], stats["failed"]), (0, 1))
        self.assertEqual(self.svc.connected_accounts(), [])  # expired accounts are no longer polled



if __name__ == "__main__":
    unittest.main()

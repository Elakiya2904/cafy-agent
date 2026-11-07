"""Mailboxes connected through Nango are read by the email agent (tokens come from Nango)."""
import os
import sys
import tempfile
import time
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("EMAIL_AGENT_SECRET", "test-secret")

from backend.database import JobDatabase
from backend.email_agent.monitor import EmailMonitor
from backend.email_agent.service import AgentError, EmailAgentService
from backend.tests.test_email_agent import C, NOW, INVITE, FakeProvider, mail


class FakeNango:
    configured = True

    def __init__(self, connections):
        self.connections = connections
        self.token_calls = []
        self.fail = False

    def list_connections(self, end_user_id):
        return [c for c in self.connections if c["end_user_id"] == end_user_id]

    def get_access_token(self, connection_id, integration_id):
        if self.fail:
            raise RuntimeError("Nango API unreachable")
        self.token_calls.append((connection_id, integration_id))
        return f"nango-token-{connection_id}"


class NangoGmail(FakeProvider):
    def __init__(self):
        super().__init__()
        self.tokens_used = []

    def fetch_profile(self, token):
        return {"email": "Me@Gmail.com", "display_name": "Alex"}

    def list_messages(self, token, since, limit=50):
        self.tokens_used.append(token)
        return list(self.inbox)

    def revoke(self, token):
        raise AssertionError("a Nango-held token must never be revoked by the email agent")


GMAIL_CONN = {"connection_id": "conn-1", "integration_id": "google-mail", "provider": "google-mail",
              "end_user_id": C}


class NangoMailboxTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, self.path)
        self.prov = NangoGmail()
        self.nango = FakeNango([GMAIL_CONN, {**GMAIL_CONN, "connection_id": "x", "end_user_id": "someone-else"},
                                {"connection_id": "cal", "integration_id": "google-calendar",
                                 "provider": "google-calendar", "end_user_id": C}])
        self.svc = EmailAgentService(JobDatabase(db_path=self.path), {"gmail": self.prov}, secret="s",
                                     now=lambda: NOW, nango=self.nango)
        self.svc.upsert_application(C, "Acme", "Software Engineer", "job1", NOW.isoformat())

    def test_nango_gmail_becomes_a_syncable_account(self):
        linked = self.svc.link_nango_accounts(C)
        self.assertEqual(len(linked), 1)  # not the other user's, not the calendar-only one
        accounts = self.svc.list_accounts(C)
        self.assertEqual([(a["provider"], a["email"], a["status"]) for a in accounts],
                         [("gmail", "me@gmail.com", "connected")])
        self.assertEqual(self.svc.link_nango_accounts(C), [])  # idempotent

    def test_sync_reads_todays_mail_with_a_nango_token(self):
        acc_id = self.svc.link_nango_accounts(C)[0]
        self.prov.inbox = [mail(1, "Jo <jo@acme.com>", "Interview invitation - Software Engineer", INVITE)]
        stats = self.svc.sync_account(C, acc_id)
        self.assertEqual(stats["fetched"], 1)
        self.assertEqual(stats["job_related"], 1)
        self.assertEqual(self.prov.tokens_used, ["nango-token-conn-1"])
        inbox = self.svc.dashboard(C)["inbox"]
        self.assertEqual(inbox[0]["subject"], "Interview invitation - Software Engineer")

    def test_background_monitor_picks_it_up(self):
        self.svc.link_nango_accounts(C)
        self.prov.inbox = [mail(1, "Jo <jo@acme.com>", "Interview invitation - Software Engineer", INVITE)]
        stats = EmailMonitor(self.svc).poll_once()
        self.assertEqual((stats["accounts"], stats["synced"], stats["failed"]), (1, 1, 0))

    def test_dashboard_links_and_starts_first_sync(self):
        self.prov.inbox = [mail(1, "Jo <jo@acme.com>", "Interview invitation - Software Engineer", INVITE)]
        self.svc.dashboard(C)
        for _ in range(50):  # first sync runs in a background thread
            if self.svc.dashboard(C)["inbox"]:
                break
            time.sleep(0.05)
        self.assertEqual(len(self.svc.dashboard(C)["inbox"]), 1)

    def test_nango_failure_is_reported_not_silent(self):
        acc_id = self.svc.link_nango_accounts(C)[0]
        self.nango.fail = True
        with self.assertRaises(AgentError) as ctx:
            self.svc.sync_account(C, acc_id)
        self.assertIn("Nango", str(ctx.exception))
        self.assertIn("unreachable", self.svc.list_accounts(C)[0]["last_error"])

    def test_google_calendar_connection_is_used_for_calendar_calls(self):
        acc_id = self.svc.link_nango_accounts(C)[0]
        acc = self.svc._account(C, acc_id)
        used = []
        self.prov.busy_intervals = lambda token, start, end, email: used.append(token) or []
        self.svc._calendar_busy(C, acc, NOW, NOW + timedelta(hours=8))
        # The fixture's "google-calendar" connection (id "cal") supplies the calendar token.
        self.assertEqual(used, ["nango-token-cal"])

    def test_without_calendar_connection_the_mail_token_is_used(self):
        self.nango.connections = [GMAIL_CONN]
        acc_id = self.svc.link_nango_accounts(C)[0]
        self.assertEqual(self.svc._calendar_token(C, self.svc._account(C, acc_id)), "nango-token-conn-1")

    def test_disconnect_stops_reading_without_revoking_the_nango_token(self):
        acc_id = self.svc.link_nango_accounts(C)[0]
        self.assertEqual(self.svc.disconnect_account(C, acc_id)["remote_revoked"], False)
        self.assertEqual(self.svc.connected_accounts(), [])
        self.assertEqual(self.svc.link_nango_accounts(C), [])  # stays disconnected


if __name__ == "__main__":
    unittest.main()

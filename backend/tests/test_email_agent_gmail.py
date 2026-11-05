"""Gmail/Calendar verification: the real GmailProvider against mocked Google HTTP,
OAuth scope enforcement, token refresh, and follow-up calendar reminders."""
import base64
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("EMAIL_AGENT_SECRET", "test-secret")

from backend.database import JobDatabase
from backend.email_agent import classifier as clf
from backend.email_agent.crypto import decrypt
from backend.email_agent.monitor import EmailMonitor
from backend.email_agent.providers import GmailProvider, ProviderAuthError, ProviderError
from backend.email_agent.service import AgentError, EmailAgentService

C = "cand-1"
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)  # a Friday
REDIRECT = "http://127.0.0.1:8000/api/email-agent/oauth/gmail/callback"


class Resp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else json.dumps(body or {})
        self.content = b"x" if (body is not None or text) else b""

    def json(self):
        return self._body


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode()


class GmailProviderHttpTests(unittest.TestCase):
    def setUp(self):
        self.g = GmailProvider("cid", "secret")

    def test_authorization_url_requests_offline_access_and_all_scopes(self):
        url = self.g.authorization_url(REDIRECT, "st")
        for part in ("access_type=offline", "prompt=consent", "gmail.readonly", "gmail.send", "calendar.events",
                     "calendar.freebusy", "client_id=cid", "state=st"):
            self.assertIn(part, url)
        self.assertTrue(set(GmailProvider.required_scopes) <= set(GmailProvider.scopes))

    def test_unconfigured_provider_refuses(self):
        with self.assertRaises(ProviderError):
            GmailProvider(None, None).authorization_url(REDIRECT, "s")

    def test_exchange_code_returns_tokens_and_profile(self):
        with mock.patch("backend.email_agent.providers.requests.post",
                        return_value=Resp(200, {"access_token": "a", "refresh_token": "r", "expires_in": 3599, "scope": "s1 s2"})) as post, \
             mock.patch("backend.email_agent.providers.requests.request",
                        return_value=Resp(200, {"email": "me@gmail.com", "name": "Me"})):
            t = self.g.exchange_code("code", REDIRECT)
        self.assertEqual((t["access_token"], t["refresh_token"], t["email"], t["scopes"]), ("a", "r", "me@gmail.com", "s1 s2"))
        self.assertEqual(post.call_args.kwargs["data"]["grant_type"], "authorization_code")
        self.assertEqual(post.call_args.kwargs["data"]["redirect_uri"], REDIRECT)

    def test_refresh_keeps_existing_refresh_token(self):
        with mock.patch("backend.email_agent.providers.requests.post", return_value=Resp(200, {"access_token": "new", "expires_in": 3600})):
            t = self.g.refresh("old-refresh")
        self.assertEqual((t["access_token"], t["refresh_token"]), ("new", "old-refresh"))

    def test_revoked_grant_is_auth_error(self):
        with mock.patch("backend.email_agent.providers.requests.post", return_value=Resp(400, text='{"error":"invalid_grant"}')):
            with self.assertRaises(ProviderAuthError):
                self.g.refresh("r")

    def test_api_401_is_auth_error_and_500_is_provider_error(self):
        with mock.patch("backend.email_agent.providers.requests.request", return_value=Resp(401, text="no")):
            with self.assertRaises(ProviderAuthError):
                self.g.busy_intervals("t", NOW, NOW + timedelta(hours=1), "me")
        with mock.patch("backend.email_agent.providers.requests.request", return_value=Resp(500, text="boom")):
            with self.assertRaises(ProviderError):
                self.g.busy_intervals("t", NOW, NOW + timedelta(hours=1), "me")

    def test_list_messages_decodes_multipart_and_headers(self):
        msg = {"id": "m1", "threadId": "t1", "internalDate": str(int(NOW.timestamp() * 1000)), "labelIds": ["INBOX"],
               "payload": {"headers": [{"name": "From", "value": "Jo <jo@acme.com>"}, {"name": "Subject", "value": "Interview"},
                                       {"name": "To", "value": "me@gmail.com"}],
                           "mimeType": "multipart/alternative",
                           "parts": [{"mimeType": "text/html", "body": {"data": b64("<p>HTML version</p>")}},
                                     {"mimeType": "text/plain", "body": {"data": b64("Plain version")}}]}}

        def fake(method, url, **kw):
            return Resp(200, {"messages": [{"id": "m1"}]}) if url.endswith("/messages") else Resp(200, msg)

        with mock.patch("backend.email_agent.providers.requests.request", side_effect=fake) as req:
            out = self.g.list_messages("tok", NOW - timedelta(days=1))
        self.assertEqual(len(out), 1)
        m = out[0]
        self.assertEqual((m["message_id"], m["thread_id"], m["sender"], m["subject"], m["body"]),
                         ("m1", "t1", "Jo <jo@acme.com>", "Interview", "Plain version"))
        self.assertEqual(req.call_args_list[0].kwargs["headers"]["Authorization"], "Bearer tok")
        self.assertIn("after:", req.call_args_list[0].kwargs["params"]["q"])

    def test_busy_intervals_parsed(self):
        body = {"calendars": {"primary": {"busy": [{"start": "2026-11-05T10:00:00Z", "end": "2026-11-05T11:00:00Z"}]}}}
        with mock.patch("backend.email_agent.providers.requests.request", return_value=Resp(200, body)) as req:
            busy = self.g.busy_intervals("t", NOW, NOW + timedelta(days=7), "me")
        self.assertEqual(busy[0]["start"], datetime(2026, 11, 5, 10, tzinfo=timezone.utc))
        self.assertTrue(req.call_args.args[1].endswith("/freeBusy"))

    def test_create_event_payload_has_reminders_and_timezone(self):
        ev = {"title": "T", "description": "D", "location": "", "start": "2026-11-02T10:00:00", "end": "2026-11-02T10:15:00",
              "timezone": "Europe/London", "reminder_minutes": [30]}
        with mock.patch("backend.email_agent.providers.requests.request", return_value=Resp(200, {"id": "evt9"})) as req:
            self.assertEqual(self.g.create_event("t", ev), "evt9")
        body = req.call_args.kwargs["json"]
        self.assertEqual(body["start"]["timeZone"], "Europe/London")
        self.assertEqual(body["reminders"]["overrides"], [{"method": "popup", "minutes": 30}])

    def test_send_email_posts_threaded_raw_message(self):
        with mock.patch("backend.email_agent.providers.requests.request", return_value=Resp(200, {"id": "s1"})) as req:
            self.assertEqual(self.g.send_email("t", "jo@acme.com", "Re: Hi", "Body", "thr1"), "s1")
        self.assertTrue(req.call_args.args[1].endswith("/messages/send"))
        sent = req.call_args.kwargs["json"]
        self.assertEqual(sent["threadId"], "thr1")
        raw = base64.urlsafe_b64decode(sent["raw"]).decode()
        self.assertIn("To: jo@acme.com", raw)
        self.assertIn("Subject: Re: Hi", raw)

    def test_delete_event_ignores_already_deleted(self):
        with mock.patch("backend.email_agent.providers.requests.request", return_value=Resp(410, text="gone")):
            self.g.delete_event("t", "e1")  # must not raise
        with mock.patch("backend.email_agent.providers.requests.request", return_value=Resp(500, text="boom")):
            with self.assertRaises(ProviderError):
                self.g.delete_event("t", "e1")


class StubGmail(GmailProvider):
    """Real GmailProvider rules (scopes) with the network replaced by in-memory recorders."""

    def __init__(self, granted=None):
        super().__init__("cid", "secret")
        self.granted = granted if granted is not None else " ".join(GmailProvider.scopes)
        self.events, self.deleted, self.sent, self.refreshes = [], [], [], 0
        self.fail_event = False

    def exchange_code(self, code, redirect_uri):
        return {"access_token": "at", "refresh_token": "rt", "token_expires_at": (NOW + timedelta(seconds=30)).isoformat(),
                "scopes": self.granted, "email": "me@gmail.com", "display_name": "Alex Candidate"}

    def refresh(self, refresh_token):
        self.refreshes += 1
        return {"access_token": f"at{self.refreshes}", "refresh_token": refresh_token,
                "token_expires_at": (NOW + timedelta(hours=1)).isoformat()}

    def list_messages(self, token, since, limit=50): return []
    def busy_intervals(self, token, start, end, email): return []

    def send_email(self, token, to, subject, body, thread_id):
        self.sent.append((to, subject))
        return "sent"

    def create_event(self, token, ev):
        if self.fail_event:
            raise ProviderError("calendar write failed")
        self.events.append(ev)
        return f"evt-{len(self.events)}"

    def delete_event(self, token, event_id): self.deleted.append(event_id)


class GmailServiceTests(unittest.TestCase):
    def build(self, granted=None, now=NOW):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, path)
        self.prov = StubGmail(granted)
        self.clock = [now]
        self.svc = EmailAgentService(JobDatabase(db_path=path), {"gmail": self.prov}, secret="s", now=lambda: self.clock[0])

    def connect(self):
        state = self.svc.start_oauth(C, "gmail", REDIRECT).split("state=")[1].split("&")[0]
        return self.svc.complete_oauth("gmail", "code", unquote(state), REDIRECT)

    def applied(self, days_ago=10):
        return self.svc.upsert_application(C, "Acme", "Software Engineer", "job1", (NOW - timedelta(days=days_ago)).isoformat(),
                                           "jo@acme.com")

    def reply(self, acc, i, subject, body, days_ago=0):
        return self.svc.ingest_message(C, self.svc._account(C, acc["id"]), {
            "message_id": f"m{i}", "thread_id": f"t{i}", "sender": "Jo <jo@acme.com>", "subject": subject, "body": body,
            "received_at": (NOW - timedelta(days=days_ago, hours=1)).isoformat(), "labels": []})

    # ---- scopes
    def test_missing_calendar_scope_blocks_connection(self):
        scopes = [s for s in GmailProvider.scopes if "calendar.events" not in s]
        self.build(granted=" ".join(scopes))
        with self.assertRaises(AgentError) as cm:
            self.connect()
        self.assertEqual(cm.exception.status, 403)
        self.assertIn("calendar.events", str(cm.exception))
        self.assertEqual(self.svc.list_accounts(C), [])

    def test_all_scopes_connect_and_tokens_not_exposed(self):
        self.build()
        acc = self.connect()
        self.assertEqual(acc["status"], "connected")
        self.assertNotIn("access_token", acc)
        self.assertNotIn("refresh_token", acc)

    def test_tokens_are_encrypted_at_rest(self):
        self.build()
        acc = self.connect()
        row = self.svc._account(C, acc["id"])
        for col, plain in (("access_token", "at"), ("refresh_token", "rt")):
            self.assertTrue(row[col].startswith("enc:v1:"))
            self.assertNotIn(plain + "\x00", row[col])
            self.assertEqual(decrypt(row[col]), plain)

    def test_legacy_plaintext_token_still_works(self):
        self.build()
        acc = self.connect()
        self.svc._update("connected_email_accounts", acc["id"], access_token="legacy-plain",
                         token_expires_at=(NOW + timedelta(hours=1)).isoformat())
        self.assertEqual(self.svc._token(C, self.svc._account(C, acc["id"])), "legacy-plain")

    def test_list_messages_follows_page_tokens(self):
        g = GmailProvider("cid", "secret")
        pages = [{"messages": [{"id": "a"}], "nextPageToken": "p2"}, {"messages": [{"id": "b"}]}]
        seen = []

        def fake(method, url, **kw):
            if url.endswith("/messages"):
                seen.append(kw["params"].get("pageToken"))
                return Resp(200, pages[len(seen) - 1])
            mid = url.rsplit("/", 1)[-1]
            return Resp(200, {"id": mid, "threadId": "t", "internalDate": "1000", "payload": {"headers": []}})

        with mock.patch("backend.email_agent.providers.requests.request", side_effect=fake):
            out = g.list_messages("t", NOW - timedelta(days=1))
        self.assertEqual([m["message_id"] for m in out], ["a", "b"])
        self.assertEqual(seen, [None, "p2"])

    # ---- token refresh
    def test_near_expiry_token_is_refreshed_and_persisted(self):
        self.build()
        acc = self.connect()  # token expires in 30s -> inside the 60s refresh margin
        self.assertEqual(self.svc._token(C, self.svc._account(C, acc["id"])), "at1")
        self.assertEqual(self.prov.refreshes, 1)
        stored = self.svc._account(C, acc["id"])["access_token"]
        self.assertTrue(stored.startswith("enc:v1:"))
        self.assertEqual(decrypt(stored), "at1")
        self.assertEqual(self.svc._token(C, self.svc._account(C, acc["id"])), "at1")  # fresh now: no second refresh
        self.assertEqual(self.prov.refreshes, 1)

    # ---- explicit approval
    def test_sync_and_monitor_never_send_email(self):
        self.build()
        self.connect()
        self.applied(days_ago=10)
        mon = EmailMonitor(self.svc)
        mon.poll_once()
        mon.poll_once()
        self.assertEqual(self.prov.sent, [])
        drafts = self.svc.list_drafts(C)
        self.assertEqual(len(drafts), 1)
        self.assertEqual((drafts[0]["approval_status"], drafts[0]["send_status"]), ("pending", "unsent"))
        self.svc.approve_and_send(C, drafts[0]["id"])
        self.assertEqual(len(self.prov.sent), 1)
        self.svc.approve_and_send(C, drafts[0]["id"])  # idempotent
        self.assertEqual(len(self.prov.sent), 1)

    # ---- response window extraction
    def test_response_window_extracted(self):
        self.assertEqual(clf.extract_response_window_days("We will get back to you within 2 weeks."), 14)
        self.assertEqual(clf.extract_response_window_days("You should hear from us in 5-7 business days"), 10)
        self.assertEqual(clf.extract_response_window_days("Expect a reply within 10 days."), 10)
        self.assertIsNone(clf.extract_response_window_days("Thanks for applying. We are hiring in 3 offices."))

    # ---- follow-up calendar
    def test_follow_up_scan_creates_calendar_reminder_from_application_mail(self):
        self.build()
        acc = self.connect()
        self.applied()
        self.reply(acc, 1, "Thank you for applying - Software Engineer",
                   "Thank you for applying for the Software Engineer role at Acme. We will get back to you within 1 week.", days_ago=9)
        drafts = self.svc.scan_follow_ups(C)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(len(self.prov.events), 1)
        ev = self.prov.events[0]
        self.assertEqual(ev["title"], "Follow up – Acme (Software Engineer)")
        self.assertIn("jo@acme.com", ev["description"])
        self.assertIn("Thank you for applying", ev["description"])
        self.assertIn("within ~7 days", ev["description"])
        self.assertIn("Nothing is sent until you approve", ev["description"])
        # NOW is Friday 12:00 UTC -> next working day Monday 10:00 London
        self.assertTrue(ev["start"].startswith("2026-11-02T10:00"), ev["start"])
        rec = self.svc.dashboard(C)["history"]["follow_ups"][0]
        self.assertEqual(rec["calendar_event_id"], "evt-1")
        self.assertEqual(self.prov.sent, [])

    def test_follow_up_scan_is_idempotent(self):
        self.build()
        self.connect()
        self.applied()
        self.svc.scan_follow_ups(C)
        self.svc.scan_follow_ups(C)
        self.assertEqual(len(self.prov.events), 1)
        self.assertEqual(len(self.svc.list_drafts(C)), 1)

    def test_employer_stated_window_delays_follow_up(self):
        self.build()
        acc = self.connect()
        self.applied(days_ago=10)
        self.reply(acc, 1, "Application received - Software Engineer",
                   "We have received your application for the Software Engineer role at Acme. You will hear from us within 3 weeks.", days_ago=9)
        self.assertEqual(self.svc.scan_follow_ups(C), [])  # 10 days < 21-day promise
        self.clock[0] = NOW + timedelta(days=12)
        self.assertEqual(len(self.svc.scan_follow_ups(C)), 1)

    def test_calendar_failure_keeps_draft_and_reports_error(self):
        self.build()
        self.connect()
        self.applied()
        self.prov.fail_event = True
        self.assertEqual(len(self.svc.scan_follow_ups(C)), 1)
        rec = self.svc.dashboard(C)["history"]["follow_ups"][0]
        self.assertIsNone(rec["calendar_event_id"])
        self.assertIn("calendar write failed", rec["calendar_error"])
        with self.assertRaises(AgentError) as cm:  # manual retry surfaces the failure, never claims success
            self.svc.schedule_follow_up_calendar(C, rec["id"])
        self.assertEqual(cm.exception.status, 502)
        self.prov.fail_event = False
        self.assertEqual(self.svc.schedule_follow_up_calendar(C, rec["id"])["calendar_event_id"], "evt-1")

    def test_reminder_removed_when_follow_up_sent(self):
        self.build()
        self.connect()
        self.applied()
        d = self.svc.scan_follow_ups(C)[0]
        self.svc.approve_and_send(C, d["id"])
        self.assertEqual(self.prov.deleted, ["evt-1"])
        self.assertIsNone(self.svc.dashboard(C)["history"]["follow_ups"][0]["calendar_event_id"])

    def test_reminder_removed_when_follow_up_rejected(self):
        self.build()
        self.connect()
        self.applied()
        d = self.svc.scan_follow_ups(C)[0]
        self.svc.reject_draft(C, d["id"])
        self.assertEqual(self.prov.deleted, ["evt-1"])

    def test_reminder_removed_when_recruiter_replies(self):
        self.build()
        acc = self.connect()
        self.applied()
        self.svc.scan_follow_ups(C)
        self.reply(acc, 9, "Interview invitation - Software Engineer at Acme",
                   "We would like to invite you to an interview for the Software Engineer role at Acme.")
        self.assertEqual(self.prov.deleted, ["evt-1"])


if __name__ == "__main__":
    unittest.main()

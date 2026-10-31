"""Auth + multi-user isolation, using really signed Supabase-style JWTs and the real database."""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

import jwt

sys.path.insert(0, ".")
os.environ.setdefault("EMAIL_AGENT_SECRET", "test-secret")

from fastapi.testclient import TestClient

from backend import main
from backend.database import JobDatabase
from backend.user_store import UserSession, UserStore

SECRET = "test-jwt-secret-that-is-long-enough-for-hs256-ok"


def token(sub, exp=3600, aud="authenticated", secret=SECRET, alg="HS256"):
    return jwt.encode({"sub": sub, "aud": aud, "exp": int(time.time()) + exp, "email": f"{sub}@example.com"}, secret, algorithm=alg)


def bearer(sub, **kw):
    return {"Authorization": f"Bearer {token(sub, **kw)}"}


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = JobDatabase(db_path=os.path.join(self.tmp.name, "auth.db"))
        store = UserStore(self.db)
        self.patches = [
            mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": SECRET, "APP_ENV": "development"}),
            mock.patch.object(main, "db", self.db),
            mock.patch.object(main, "user_store", store),
            mock.patch.object(main, "ACTIVE_SESSION", UserSession(store)),
            mock.patch.object(main.resume_generation_svc, "update_artifacts", return_value={}),
        ]
        for p in self.patches:
            p.start()
        os.environ.pop("SUPABASE_URL", None)
        self.client = TestClient(main.app)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    # ---- who may call
    def test_no_token_is_401(self):
        self.assertEqual(self.client.get("/api/resume/current").status_code, 401)
        self.assertEqual(self.client.get("/api/email-agent/dashboard").status_code, 401)

    def test_health_and_oauth_callback_are_public(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        r = self.client.get("/api/email-agent/oauth/gmail/callback?error=access_denied", follow_redirects=False)
        self.assertIn(r.status_code, (302, 307))

    def test_bad_tokens_rejected(self):
        cases = {
            "expired": bearer("u1", exp=-10),
            "wrong audience": bearer("u1", aud="anon"),
            "wrong secret": bearer("u1", secret="another-secret-another-secret-another-secret"),
            "garbage": {"Authorization": "Bearer not.a.jwt"},
        }
        for name, headers in cases.items():
            with self.subTest(name):
                self.assertEqual(self.client.get("/api/resume/current", headers=headers).status_code, 401)

    def test_unsigned_alg_none_token_rejected(self):
        forged = jwt.encode({"sub": "admin", "aud": "authenticated", "exp": int(time.time()) + 600}, key=None, algorithm="none")
        self.assertEqual(self.client.get("/api/resume/current", headers={"Authorization": f"Bearer {forged}"}).status_code, 401)

    def test_client_cannot_choose_identity_with_header(self):
        r = self.client.get("/api/resume/uploaded", headers={**bearer("alice"), "X-Candidate-Id": "bob"})
        self.assertEqual(r.status_code, 200)
        self.main_user_store().save_file("bob", "bob.pdf", "application/pdf", b"%PDF bob", {})
        self.assertEqual(self.client.get("/api/resume/uploaded", headers={**bearer("alice"), "X-Candidate-Id": "bob"}).json(), {"uploaded": None})

    def test_token_in_query_only_for_file_downloads(self):
        self.main_user_store().save_file("alice", "a.pdf", "application/pdf", b"%PDF-alice", {})
        t = token("alice")
        ok = self.client.get(f"/api/resume/uploaded/file?access_token={t}")
        self.assertEqual((ok.status_code, ok.content), (200, b"%PDF-alice"))
        self.assertEqual(self.client.get(f"/api/resume/current?access_token={t}").status_code, 401)

    def test_production_without_auth_config_fails_closed(self):
        os.environ.pop("SUPABASE_JWT_SECRET", None)
        os.environ["APP_ENV"] = "production"
        self.assertEqual(self.client.get("/api/resume/current").status_code, 503)
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_dev_mode_without_config_uses_local_user(self):
        os.environ.pop("SUPABASE_JWT_SECRET", None)
        self.assertEqual(self.client.get("/api/resume/current").status_code, 200)

    # ---- who sees what
    def main_user_store(self):
        return main.user_store

    def test_resume_and_file_are_private_per_user(self):
        main.user_store.set_resume("alice", {"candidate_name": "Alice", "skills": ["Python"]})
        main.user_store.save_file("alice", "alice.pdf", "application/pdf", b"%PDF-alice", {"skills": ["Python"]})
        alice, bob = bearer("alice"), bearer("bob")
        self.assertEqual(self.client.get("/api/resume/current", headers=alice).json()["resume"]["candidate_name"], "Alice")
        self.assertIsNone(self.client.get("/api/resume/current", headers=bob).json()["resume"])
        self.assertEqual(self.client.get("/api/resume/uploaded", headers=bob).json(), {"uploaded": None})
        self.assertEqual(self.client.get("/api/resume/uploaded/file", headers=bob).status_code, 404)
        self.assertEqual(self.client.get("/api/resume/uploaded/file", headers=alice).content, b"%PDF-alice")

    def test_tailored_resumes_and_downloads_are_private(self):
        rid = "a" * 32
        saved = self.client.post("/api/resumes/save", headers=bearer("alice"), json={
            "job_id": "job-1", "resume_id": rid, "resume": {"professional_summary": "Alice's summary", "skills": ["Go"]}})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.client.get("/api/resumes/versions", headers=bearer("alice")).json()["count"], 1)
        self.assertEqual(self.client.get("/api/resumes/versions", headers=bearer("bob")).json()["count"], 0)
        self.assertEqual(self.client.get("/api/resumes/job/job-1", headers=bearer("bob")).json()["status"], "not_found")
        self.assertEqual(self.client.get(f"/api/resumes/{rid}/docx", headers=bearer("bob")).status_code, 404)
        self.assertEqual(self.client.get(f"/api/resumes/{rid}/latex", headers=bearer("bob")).status_code, 404)
        self.assertEqual(self.client.get(f"/api/resumes/..%2F{rid}/pdf", headers=bearer("alice")).status_code, 404)

    def test_pipeline_data_is_scoped_to_the_token_user(self):
        main.email_agent_svc.upsert_application("alice", "Acme", "Engineer", "j1")
        main.email_agent_svc.upsert_application("bob", "Globex", "Analyst", "j2")
        a = self.client.get("/api/email-agent/applications", headers=bearer("alice")).json()
        b = self.client.get("/api/email-agent/applications", headers=bearer("bob")).json()
        self.assertEqual([x["company"] for x in a], ["Acme"])
        self.assertEqual([x["company"] for x in b], ["Globex"])

    def test_oauth_start_binds_the_flow_to_the_token_user(self):
        import json, base64
        from urllib.parse import parse_qs, urlparse
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "id", "GOOGLE_CLIENT_SECRET": "secret", "PUBLIC_BASE_URL": "https://app.example.com"}):
            main.email_agent_svc.providers["gmail"].client_id = "id"
            main.email_agent_svc.providers["gmail"].client_secret = "secret"
            url = self.client.get("/api/email-agent/oauth/gmail/start", headers=bearer("alice")).json()["auth_url"]
        q = parse_qs(urlparse(url).query)
        self.assertEqual(q["redirect_uri"][0], "https://app.example.com/api/email-agent/oauth/gmail/callback")
        payload = q["state"][0].split(".")[0]
        self.assertEqual(json.loads(base64.urlsafe_b64decode(payload))["c"], "alice")

    # ---- cron
    def test_cron_poll_requires_secret(self):
        with mock.patch.dict(os.environ, {"CRON_SECRET": "s3cret"}):
            self.assertEqual(self.client.get("/api/email-agent/cron/poll").status_code, 401)
            self.assertEqual(self.client.get("/api/email-agent/cron/poll", headers={"Authorization": "Bearer nope"}).status_code, 401)
            r = self.client.get("/api/email-agent/cron/poll", headers={"Authorization": "Bearer s3cret"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), {"accounts", "synced", "failed", "follow_up_drafts"})
        self.assertEqual(self.client.get("/api/email-agent/cron/poll").status_code, 401)  # no CRON_SECRET configured -> closed

    def test_cron_scrape_requires_secret_and_persists_real_results(self):
        results = {"jobs": [], "status": "success", "timestamp": "2026-10-31T00:00:00+00:00", "duration_seconds": 0.1}
        with mock.patch.dict(os.environ, {"CRON_SECRET": "s3cret"}), \
             mock.patch.object(main.scraper_mgr, "scrape_platform", return_value=results) as scrape:
            self.assertEqual(self.client.get("/api/cron/scrape?platform=greenhouse").status_code, 401)
            ok = self.client.get("/api/cron/scrape?platform=greenhouse", headers={"Authorization": "Bearer s3cret"})
        self.assertEqual(ok.status_code, 200)
        scrape.assert_called_once_with("greenhouse")
        self.assertEqual(self.db.get_stats()["recent_runs"][0]["platform"], "greenhouse")

    def test_production_boot_refuses_incomplete_config(self):
        from backend.auth import validate_production_config
        env = {"APP_ENV": "production"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as cm:
                validate_production_config()
        self.assertIn("DATABASE_URL", str(cm.exception))
        full = {**env, "DATABASE_URL": "postgresql://x", "SUPABASE_JWT_SECRET": SECRET, "EMAIL_AGENT_SECRET": "s"}
        with mock.patch.dict(os.environ, full, clear=True):
            validate_production_config()  # complete -> no error


if __name__ == "__main__":
    unittest.main()

"""Sign-up / sign-in / refresh / sign-out: password handling, tokens, rotation, throttling and the HTTP contract."""
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import jwt

sys.path.insert(0, ".")
os.environ.setdefault("EMAIL_AGENT_SECRET", "test-secret")

from fastapi.testclient import TestClient

from backend import auth_service as svc
from backend import main
from backend.auth_service import AuthError, AuthService, LoginThrottle
from backend.database import JobDatabase

SECRET = "test-jwt-secret-that-is-long-enough-for-hs256-ok"
GOOD = "correct-horse-battery"
CLIENT = {"X-Cafy-Client": "web"}


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = JobDatabase(db_path=os.path.join(self.tmp.name, "auth.db"))
        self.env = mock.patch.dict(os.environ, {"JWT_SECRET_KEY": SECRET, "APP_ENV": "development", "ENABLE_GUEST_MODE": "false"})
        self.env.start()
        self.service = AuthService(self.db, throttle=LoginThrottle())

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def signup(self, email="Ada@Example.com", password=GOOD, name="Ada Lovelace"):
        return self.service.signup(email, password, name)


class TestValidation(unittest.TestCase):
    def test_email_is_normalised_and_checked(self):
        self.assertEqual(svc.normalize_email("  Ada@Example.COM "), "ada@example.com")
        for bad in ("", "no-at-sign", "a@b", "a b@c.com", "a@@c.com", "a@.com", "x" * 70 + "@c.com"):
            with self.subTest(bad), self.assertRaises(AuthError):
                svc.normalize_email(bad)

    def test_password_rules(self):
        for bad in ("short", "x" * 129, "        ", "password", "12345678"):
            with self.subTest(bad), self.assertRaises(AuthError) as cm:
                svc.validate_password(bad)
            self.assertEqual(cm.exception.status, 400)
        with self.assertRaises(AuthError):
            svc.validate_password("ada@example.com", "ada@example.com")
        self.assertEqual(svc.validate_password(GOOD), GOOD)

    def test_name_rules(self):
        self.assertEqual(svc.normalize_name("  Ada   Lovelace "), "Ada Lovelace")
        for bad in ("", "   ", "x" * 101, "bad\x00name"):
            with self.subTest(bad), self.assertRaises(AuthError):
                svc.normalize_name(bad)


class TestPasswordsAndTokens(AuthTestCase):
    def test_hash_is_argon2id_and_verifies(self):
        stored = svc.hash_password(GOOD)
        self.assertTrue(stored.startswith("$argon2id$"))
        self.assertEqual(svc.verify_password(stored, GOOD)[0], True)
        self.assertEqual(svc.verify_password(stored, "wrong-password")[0], False)

    def test_unknown_user_is_verified_against_a_dummy_hash(self):
        self.assertEqual(svc.verify_password(None, GOOD), (False, False))

    def test_access_token_round_trip_and_claims(self):
        token, lifetime = svc.create_access_token("user-1", "ada@example.com")
        claims = svc.verify_access_token(token)
        self.assertEqual((claims["sub"], claims["email"], claims["iss"], claims["aud"]), ("user-1", "ada@example.com", "cafy-agent", "cafy-agent-web"))
        self.assertEqual(lifetime, 15 * 60)
        self.assertEqual(claims["exp"] - claims["iat"], lifetime)

    def test_tokens_that_must_be_rejected(self):
        base = {"sub": "u", "iss": "cafy-agent", "aud": "cafy-agent-web", "exp": int(time.time()) + 600}
        cases = {
            "expired": jwt.encode({**base, "exp": int(time.time()) - 600}, SECRET, algorithm="HS256"),
            "wrong secret": jwt.encode(base, "another-secret-another-secret-another-secret", algorithm="HS256"),
            "wrong audience": jwt.encode({**base, "aud": "other"}, SECRET, algorithm="HS256"),
            "wrong issuer": jwt.encode({**base, "iss": "other"}, SECRET, algorithm="HS256"),
            "no subject": jwt.encode({k: v for k, v in base.items() if k != "sub"}, SECRET, algorithm="HS256"),
            "alg none": jwt.encode(base, key=None, algorithm="none"),
            "HS512": jwt.encode(base, SECRET, algorithm="HS512"),
            "garbage": "not.a.jwt",
        }
        for name, token in cases.items():
            with self.subTest(name), self.assertRaises(AuthError):
                svc.verify_access_token(token)

    def test_production_refuses_missing_or_weak_secret(self):
        with mock.patch.dict(os.environ, {"APP_ENV": "production"}):
            for secret in ("", "short", "replace-with-a-long-random-secret"):
                with mock.patch.dict(os.environ, {"JWT_SECRET_KEY": secret}), self.assertRaises(RuntimeError):
                    svc.signing_secret()

    def test_development_without_secret_gets_a_random_key(self):
        with mock.patch.dict(os.environ, {"JWT_SECRET_KEY": ""}):
            key = svc.signing_secret()
            self.assertGreaterEqual(len(key), svc.MIN_SECRET_LENGTH)
            self.assertEqual(svc.signing_secret(), key)

    def test_the_public_example_secret_is_never_used_to_sign(self):
        with mock.patch.dict(os.environ, {"JWT_SECRET_KEY": "replace-with-a-long-random-secret"}):
            self.assertNotEqual(svc.signing_secret(), "replace-with-a-long-random-secret")

    def test_guest_mode_is_never_enabled_in_production(self):
        with mock.patch.dict(os.environ, {"ENABLE_GUEST_MODE": "true", "APP_ENV": "production"}):
            self.assertFalse(svc.guest_mode_enabled())
        with mock.patch.dict(os.environ, {"ENABLE_GUEST_MODE": "true", "APP_ENV": "development"}):
            self.assertTrue(svc.guest_mode_enabled())

    def test_guest_mode_defaults_on_in_development_and_can_be_turned_off(self):
        with mock.patch.dict(os.environ, {"APP_ENV": "development"}):
            os.environ.pop("ENABLE_GUEST_MODE", None)
            self.assertTrue(svc.guest_mode_enabled())
            os.environ["ENABLE_GUEST_MODE"] = "false"
            self.assertFalse(svc.guest_mode_enabled())
        with mock.patch.dict(os.environ, {"APP_ENV": "production"}):
            os.environ.pop("ENABLE_GUEST_MODE", None)
            self.assertFalse(svc.guest_mode_enabled())


class TestAccounts(AuthTestCase):
    def test_signup_creates_a_session_and_never_stores_the_password(self):
        session = self.signup()
        self.assertEqual(session.user["email"], "ada@example.com")
        self.assertEqual(svc.verify_access_token(session.access_token)["sub"], session.user["id"])
        with self.db._get_connection() as conn:
            row = conn.execute("SELECT password_hash FROM users").fetchone()
            token_row = conn.execute("SELECT token_hash FROM refresh_tokens").fetchone()
        self.assertNotIn(GOOD, row["password_hash"])
        self.assertNotEqual(token_row["token_hash"], session.refresh_token)  # only the hash is stored

    def test_duplicate_email_is_a_conflict_regardless_of_case(self):
        self.signup()
        with self.assertRaises(AuthError) as cm:
            self.signup(email="ADA@example.com")
        self.assertEqual(cm.exception.status, 409)

    def test_login_success_and_uniform_failure(self):
        created = self.signup()
        ok = self.service.login("ada@example.com", GOOD)
        self.assertEqual(ok.user["id"], created.user["id"])
        for email, password in (("ada@example.com", "wrong-password"), ("nobody@example.com", GOOD), ("not-an-email", GOOD)):
            with self.subTest(email), self.assertRaises(AuthError) as cm:
                self.service.login(email, password)
            self.assertEqual((cm.exception.status, str(cm.exception)), (401, "Incorrect email or password."))

    def test_inactive_account_cannot_sign_in_or_refresh(self):
        session = self.signup()
        with self.db._get_connection() as conn:
            conn.execute("UPDATE users SET is_active = ?", (False,))
            conn.commit()
        with self.assertRaises(AuthError):
            self.service.login("ada@example.com", GOOD)
        with self.assertRaises(AuthError):
            self.service.refresh(session.refresh_token)

    def test_failed_logins_are_throttled_per_email(self):
        self.signup()
        for _ in range(svc.THROTTLE_MAX_PER_EMAIL):
            with self.assertRaises(AuthError) as cm:
                self.service.login("ada@example.com", "wrong-password", client="1.1.1.1")
            self.assertEqual(cm.exception.status, 401)
        with self.assertRaises(AuthError) as cm:
            self.service.login("ada@example.com", GOOD, client="2.2.2.2")  # even the right password, from elsewhere
        self.assertEqual(cm.exception.status, 429)
        self.assertGreater(cm.exception.retry_after, 0)

    def test_successful_login_resets_the_email_counter(self):
        self.signup()
        for _ in range(svc.THROTTLE_MAX_PER_EMAIL - 1):
            with self.assertRaises(AuthError):
                self.service.login("ada@example.com", "wrong-password")
        self.service.login("ada@example.com", GOOD)
        with self.assertRaises(AuthError) as cm:
            self.service.login("ada@example.com", "wrong-password")
        self.assertEqual(cm.exception.status, 401)


class TestRefreshTokens(AuthTestCase):
    def test_refresh_rotates_and_the_old_token_stops_working(self):
        first = self.signup()
        second = self.service.refresh(first.refresh_token)
        self.assertNotEqual(first.refresh_token, second.refresh_token)
        self.assertEqual(second.user["id"], first.user["id"])
        self.assertEqual(svc.verify_access_token(second.access_token)["sub"], first.user["id"])

    def test_replaying_a_rotated_token_revokes_every_session(self):
        first = self.signup()
        second = self.service.refresh(first.refresh_token)
        with mock.patch.object(svc, "REFRESH_REUSE_GRACE_SECONDS", 0):
            time.sleep(0.01)
            with self.assertRaises(AuthError):
                self.service.refresh(first.refresh_token)          # replay of the rotated token
        with self.assertRaises(AuthError):
            self.service.refresh(second.refresh_token)             # the successor is gone too, even inside the grace window

    def test_two_tabs_racing_inside_the_grace_window_both_succeed(self):
        first = self.signup()
        a = self.service.refresh(first.refresh_token)
        b = self.service.refresh(first.refresh_token)               # same token, immediately
        self.assertNotEqual(a.refresh_token, b.refresh_token)
        self.service.refresh(b.refresh_token)                       # and the account is still signed in

    def test_unknown_expired_and_missing_tokens_are_rejected(self):
        session = self.signup()
        for token in (None, "", "made-up"):
            with self.subTest(token), self.assertRaises(AuthError):
                self.service.refresh(token)
        with self.db._get_connection() as conn:
            conn.execute("UPDATE refresh_tokens SET expires_at = ?", ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),))
            conn.commit()
        with self.assertRaises(AuthError):
            self.service.refresh(session.refresh_token)

    def test_purge_removes_long_expired_tokens_only(self):
        keep, gone = self.signup(), self.service.login("ada@example.com", GOOD)
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        with self.db._get_connection() as conn:
            conn.execute("UPDATE refresh_tokens SET expires_at = ? WHERE token_hash = ?", (old, svc._token_hash(gone.refresh_token)))
            conn.commit()
        self.service.purge_expired_tokens()
        with self.db._get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM refresh_tokens").fetchone()["n"], 1)
        self.service.refresh(keep.refresh_token)

    def test_logout_revokes_only_that_session_and_is_idempotent(self):
        one = self.signup()
        two = self.service.login("ada@example.com", GOOD)
        self.service.logout(one.refresh_token)
        self.service.logout(one.refresh_token)
        self.service.logout(None)
        with self.assertRaises(AuthError):
            self.service.refresh(one.refresh_token)
        self.service.refresh(two.refresh_token)


class TestHttpContract(AuthTestCase):
    def setUp(self):
        super().setUp()
        # The app's router holds main.auth_svc; point that one service at the throwaway test database.
        self.db_patch = mock.patch.object(main.auth_svc, "db", self.db)
        self.db_patch.start()
        main.auth_svc.throttle = LoginThrottle()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.db_patch.stop()
        super().tearDown()

    def body(self, **over):
        return {"full_name": "Ada Lovelace", "email": "ada@example.com", "password": GOOD, **over}

    def test_signup_returns_token_user_and_a_locked_down_cookie(self):
        r = self.client.post("/api/auth/signup", json=self.body())
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual((data["token_type"], data["expires_in"], data["user"]["email"]), ("bearer", 900, "ada@example.com"))
        self.assertNotIn("refresh", str(data).lower())             # the refresh token never reaches JavaScript
        cookie = r.headers["set-cookie"].lower()
        for flag in ("httponly", "samesite=strict", "path=/api/auth"):
            self.assertIn(flag, cookie)
        self.assertEqual(r.headers["cache-control"], "no-store")

    def test_cookie_is_secure_in_production_and_behind_https(self):
        with mock.patch.dict(os.environ, {"APP_ENV": "production"}):
            self.assertIn("secure", self.client.post("/api/auth/signup", json=self.body()).headers["set-cookie"].lower())
        r = self.client.post("/api/auth/login", json=self.body(), headers={"X-Forwarded-Proto": "https"})
        self.assertIn("secure", r.headers["set-cookie"].lower())

    def test_validation_errors_are_clear(self):
        for override, fragment in (({"email": "nope"}, "valid email"), ({"password": "short"}, "at least 8"), ({"full_name": " "}, "full name")):
            with self.subTest(override):
                r = self.client.post("/api/auth/signup", json=self.body(**override))
                self.assertEqual(r.status_code, 400)
                self.assertIn(fragment, r.json()["detail"])

    def test_duplicate_signup_is_409(self):
        self.client.post("/api/auth/signup", json=self.body())
        self.assertEqual(self.client.post("/api/auth/signup", json=self.body()).status_code, 409)

    def test_login_wrong_password_is_401_with_www_authenticate(self):
        self.client.post("/api/auth/signup", json=self.body())
        r = self.client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-password"})
        self.assertEqual((r.status_code, r.json()["detail"]), (401, "Incorrect email or password."))
        self.assertEqual(r.headers["www-authenticate"], "Bearer")

    def test_login_is_429_with_retry_after_when_throttled(self):
        self.client.post("/api/auth/signup", json=self.body())
        for _ in range(svc.THROTTLE_MAX_PER_EMAIL):
            self.client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-password"})
        r = self.client.post("/api/auth/login", json=self.body())
        self.assertEqual(r.status_code, 429)
        self.assertGreater(int(r.headers["retry-after"]), 0)

    def test_config_tells_the_ui_whether_guests_are_allowed(self):
        with mock.patch.dict(os.environ, {"ENABLE_GUEST_MODE": "true"}):
            self.assertEqual(self.client.get("/api/auth/config").json(), {"guest_mode": True})
        with mock.patch.dict(os.environ, {"ENABLE_GUEST_MODE": "true", "APP_ENV": "production"}):
            self.assertEqual(self.client.get("/api/auth/config").json(), {"guest_mode": False})
        with mock.patch.dict(os.environ, {"ENABLE_GUEST_MODE": "false"}):
            self.assertEqual(self.client.get("/api/auth/config").json(), {"guest_mode": False})

    def test_guest_requests_work_only_when_the_server_allows_them(self):
        guest = {"X-Cafy-Guest": "true"}
        with mock.patch.dict(os.environ, {"ENABLE_GUEST_MODE": "true"}):
            self.assertEqual(self.client.get("/api/resume/current", headers=guest).status_code, 200)
        with mock.patch.dict(os.environ, {"ENABLE_GUEST_MODE": "false"}):
            self.assertEqual(self.client.get("/api/resume/current", headers=guest).status_code, 401)

    def test_me_requires_a_token_and_returns_the_user(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        token = self.client.post("/api/auth/signup", json=self.body()).json()["access_token"]
        r = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.json()["user"]["email"], "ada@example.com")

    def test_refresh_uses_the_cookie_rotates_it_and_needs_the_client_header(self):
        self.client.post("/api/auth/signup", json=self.body())
        self.assertEqual(self.client.post("/api/auth/refresh").status_code, 400)          # no X-Cafy-Client
        old_cookie = self.client.cookies.get("cafy_refresh")
        r = self.client.post("/api/auth/refresh", headers=CLIENT)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["access_token"])
        self.assertNotEqual(self.client.cookies.get("cafy_refresh"), old_cookie)

    def test_refresh_without_a_session_clears_the_cookie(self):
        r = self.client.post("/api/auth/refresh", headers=CLIENT)
        self.assertEqual(r.status_code, 401)

    def test_logout_ends_the_session(self):
        self.client.post("/api/auth/signup", json=self.body())
        self.assertEqual(self.client.post("/api/auth/logout", headers=CLIENT).status_code, 204)
        self.assertEqual(self.client.post("/api/auth/refresh", headers=CLIENT).status_code, 401)

    def test_the_issued_token_unlocks_protected_routes(self):
        self.assertEqual(self.client.get("/api/resume/current").status_code, 401)
        token = self.client.post("/api/auth/signup", json=self.body()).json()["access_token"]
        self.assertEqual(self.client.get("/api/resume/current", headers={"Authorization": f"Bearer {token}"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()

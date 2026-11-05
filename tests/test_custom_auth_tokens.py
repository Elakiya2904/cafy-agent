"""Verify signed application tokens used by PostgreSQL-backed accounts.

Covers valid tokens and rejection of altered signatures, expiry, issuer,
audience, and unsigned-token inputs.
"""
import os
import sys
import time
import unittest
from unittest import mock

import jwt

sys.path.insert(0, ".")
from backend import auth

SECRET = "test-jwt-secret-that-is-long-enough-for-hs256-ok"
TOKEN_ENV = {
    "JWT_SECRET_KEY": SECRET,
    "JWT_ISSUER": "cafy-agent",
    "JWT_AUDIENCE": "cafy-agent-web",
}


class CustomTokenTests(unittest.TestCase):
    def sign(self, secret=SECRET, **claims):
        now = int(time.time())
        payload = {
            "sub": "user-1",
            "aud": "cafy-agent-web",
            "iss": "cafy-agent",
            "iat": now,
            "exp": now + 600,
            **claims,
        }
        return jwt.encode(payload, secret, algorithm="HS256")

    def verify_with_config(self, token):
        with mock.patch.dict(os.environ, TOKEN_ENV, clear=True):
            return auth.verify_token(token)

    def test_valid_application_token_is_accepted(self):
        self.assertEqual(self.verify_with_config(self.sign())["sub"], "user-1")

    def test_token_signed_with_another_secret_is_rejected(self):
        with self.assertRaises(auth.AuthError):
            self.verify_with_config(self.sign(secret="another-secret-that-is-long-enough"))

    def test_expired_token_is_rejected(self):
        with self.assertRaises(auth.AuthError):
            self.verify_with_config(self.sign(exp=int(time.time()) - 1))

    def test_token_with_wrong_issuer_is_rejected(self):
        with self.assertRaises(auth.AuthError):
            self.verify_with_config(self.sign(iss="another-issuer"))

    def test_token_with_wrong_audience_is_rejected(self):
        with self.assertRaises(auth.AuthError):
            self.verify_with_config(self.sign(aud="another-audience"))

    def test_unsigned_token_is_rejected(self):
        forged = jwt.encode(
            {"sub": "admin", "aud": "cafy-agent-web", "iss": "cafy-agent", "exp": int(time.time()) + 600},
            key=None,
            algorithm="none",
        )
        with self.assertRaises(auth.AuthError):
            self.verify_with_config(forged)


if __name__ == "__main__":
    unittest.main()

"""Asymmetric (ES256) Supabase tokens verified through a real JWKS endpoint served over HTTP."""
import json
import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, ".")
from backend import auth


class JwksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = ec.generate_private_key(ec.SECP256R1())
        cls.other = ec.generate_private_key(ec.SECP256R1())
        jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(cls.key.public_key()))
        jwk.update(kid="test-key", use="sig", alg="ES256")
        body = json.dumps({"keys": [jwk]}).encode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/auth/v1/.well-known/jwks.json":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *a):
                pass

        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def sign(self, key=None, **claims):
        payload = {"sub": "user-1", "aud": "authenticated", "exp": int(time.time()) + 600, **claims}
        return jwt.encode(payload, key or self.key, algorithm="ES256", headers={"kid": "test-key"})

    def test_valid_es256_token_is_accepted(self):
        with mock.patch.dict(os.environ, {"SUPABASE_URL": self.url}, clear=False):
            self.assertEqual(auth.verify_token(self.sign())["sub"], "user-1")

    def test_token_signed_by_another_key_is_rejected(self):
        with mock.patch.dict(os.environ, {"SUPABASE_URL": self.url}, clear=False):
            with self.assertRaises(auth.AuthError):
                auth.verify_token(self.sign(key=self.other))

    def test_expired_es256_token_is_rejected(self):
        with mock.patch.dict(os.environ, {"SUPABASE_URL": self.url}, clear=False):
            with self.assertRaises(auth.AuthError):
                auth.verify_token(self.sign(exp=int(time.time()) - 5))

    def test_hs256_token_cannot_be_forged_with_the_public_key(self):
        """Classic alg-confusion attack: HS256 token whose 'secret' is the public key must not pass when no HS secret is configured."""
        forged = jwt.encode({"sub": "admin", "aud": "authenticated", "exp": int(time.time()) + 600}, "anything", algorithm="HS256")
        env = {"SUPABASE_URL": self.url}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("SUPABASE_JWT_SECRET", None)
            with self.assertRaises(auth.AuthError):
                auth.verify_token(forged)


if __name__ == "__main__":
    unittest.main()

"""Tests for the Nango integration service and API endpoints.

Covers:
- Connect session creation
- Connection listing with ownership enforcement
- Connection deletion with ownership verification
- Unauthorized access rejection
- Cross-user connection access prevention
- Nango API failure handling
- Secret key never exposed
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.nango_service import NangoError, NangoService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self._body = body or {}
        self.text = text if text is not None else json.dumps(self._body)
        self.content = b"x" if (body is not None or text) else b""

    def json(self):
        return self._body


USER_A = "user-aaa-111"
USER_B = "user-bbb-222"
CONN_A = "conn-gmail-aaa"
CONN_B = "conn-gmail-bbb"
INTEGRATION = "gmail"


# ---------------------------------------------------------------------------
# NangoService unit tests
# ---------------------------------------------------------------------------

class TestNangoServiceNotConfigured(unittest.TestCase):
    def test_unconfigured_raises_503(self):
        svc = NangoService(secret_key="")
        self.assertFalse(svc.configured)
        with self.assertRaises(NangoError) as cm:
            svc.create_connect_session(USER_A)
        self.assertEqual(cm.exception.status, 503)

    def test_configured_flag(self):
        svc = NangoService(secret_key="test-key")
        self.assertTrue(svc.configured)


class TestNangoServiceConnectSession(unittest.TestCase):
    def setUp(self):
        self.svc = NangoService(secret_key="test-secret")

    def _mock_post(self, body, status=200):
        return mock.patch(
            "backend.nango_service.requests.request",
            return_value=FakeResponse(status, body),
        )

    def test_returns_session_token(self):
        with self._mock_post({"data": {"token": "sess-tok-xyz"}}):
            result = self.svc.create_connect_session(USER_A)
        self.assertEqual(result["session_token"], "sess-tok-xyz")

    def test_secret_key_in_auth_header_not_response(self):
        with self._mock_post({"data": {"token": "t"}}) as m:
            result = self.svc.create_connect_session(USER_A)
        call_kwargs = m.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        self.assertIn("Bearer test-secret", headers.get("Authorization", ""))
        # Secret must not appear in the returned data
        self.assertNotIn("test-secret", json.dumps(result))

    def test_allowed_integrations_passed_to_nango(self):
        with self._mock_post({"data": {"token": "t"}}) as m:
            self.svc.create_connect_session(USER_A, ["gmail", "google-calendar"])
        body = m.call_args.kwargs.get("json") or {}
        self.assertEqual(body.get("allowed_integrations"), ["gmail", "google-calendar"])

    def test_end_user_id_passed_to_nango(self):
        with self._mock_post({"data": {"token": "t"}}) as m:
            self.svc.create_connect_session(USER_A)
        body = m.call_args.kwargs.get("json") or {}
        self.assertEqual(body["end_user"]["id"], USER_A)

    def test_nango_401_raises_503(self):
        with self._mock_post({}, status=401):
            with self.assertRaises(NangoError) as cm:
                self.svc.create_connect_session(USER_A)
        self.assertEqual(cm.exception.status, 503)

    def test_nango_500_raises_502(self):
        with self._mock_post({"error": {"message": "internal"}}, status=500):
            with self.assertRaises(NangoError) as cm:
                self.svc.create_connect_session(USER_A)
        self.assertEqual(cm.exception.status, 502)

    def test_missing_token_in_response_raises(self):
        with self._mock_post({"data": {}}):
            with self.assertRaises(NangoError):
                self.svc.create_connect_session(USER_A)

    def test_network_error_raises_503(self):
        import requests as req_lib
        with mock.patch("backend.nango_service.requests.request", side_effect=req_lib.RequestException("timeout")):
            with self.assertRaises(NangoError) as cm:
                self.svc.create_connect_session(USER_A)
        self.assertEqual(cm.exception.status, 503)


class TestNangoServiceConnections(unittest.TestCase):
    def setUp(self):
        self.svc = NangoService(secret_key="test-secret")

    def _conn(self, user_id, conn_id, integration="gmail"):
        return {
            "connection_id": conn_id,
            "provider_config_key": integration,
            "provider": "google",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "end_user": {"id": user_id},
        }

    def test_list_connections_returns_safe_data(self):
        body = {"connections": [self._conn(USER_A, CONN_A)]}
        with mock.patch("backend.nango_service.requests.request", return_value=FakeResponse(200, body)):
            result = self.svc.list_connections(USER_A)
        self.assertEqual(len(result), 1)
        conn = result[0]
        self.assertEqual(conn["connection_id"], CONN_A)
        self.assertEqual(conn["end_user_id"], USER_A)
        # No credentials in output
        self.assertNotIn("credentials", conn)
        self.assertNotIn("access_token", conn)
        self.assertNotIn("refresh_token", conn)

    def test_get_connection_strips_credentials(self):
        raw = {**self._conn(USER_A, CONN_A), "credentials": {"access_token": "secret-tok"}}
        with mock.patch("backend.nango_service.requests.request", return_value=FakeResponse(200, raw)):
            result = self.svc.get_connection(CONN_A, INTEGRATION)
        self.assertNotIn("credentials", result)
        self.assertNotIn("access_token", result)

    def test_get_access_token_returns_token_not_exposed_in_list(self):
        raw = {**self._conn(USER_A, CONN_A), "credentials": {"access_token": "real-access-tok"}}
        with mock.patch("backend.nango_service.requests.request", return_value=FakeResponse(200, raw)):
            token = self.svc.get_access_token(CONN_A, INTEGRATION)
        self.assertEqual(token, "real-access-tok")

    def test_delete_connection_calls_delete(self):
        with mock.patch("backend.nango_service.requests.request", return_value=FakeResponse(200, {})) as m:
            self.svc.delete_connection(CONN_A, INTEGRATION)
        self.assertEqual(m.call_args.args[0], "DELETE")

    def test_404_raises_nango_error(self):
        with mock.patch("backend.nango_service.requests.request", return_value=FakeResponse(404, {})):
            with self.assertRaises(NangoError) as cm:
                self.svc.get_connection("nonexistent", INTEGRATION)
        self.assertEqual(cm.exception.status, 404)


# ---------------------------------------------------------------------------
# API endpoint ownership tests (using FastAPI TestClient)
# ---------------------------------------------------------------------------

class TestNangoApiOwnership(unittest.TestCase):
    """Verify that the API layer enforces connection ownership."""

    def _make_app(self, user_id: str, connections):
        """Build a minimal FastAPI test app with the Nango router."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.nango_api import build_router
        from backend import context

        app = FastAPI()

        # Inject the user ID without going through JWT verification
        @app.middleware("http")
        async def inject_user(request, call_next):
            token = context.set_candidate(user_id)
            try:
                return await call_next(request)
            finally:
                context.reset_candidate(token)

        svc = NangoService(secret_key="test-secret")
        app.include_router(build_router(svc))
        return TestClient(app), svc

    def test_list_connections_only_returns_own(self):
        from fastapi.testclient import TestClient

        client, svc = self._make_app(USER_A, [])
        conn_a = {"connection_id": CONN_A, "provider_config_key": INTEGRATION, "provider": "google",
                  "created_at": "", "updated_at": "", "end_user": {"id": USER_A}}
        conn_b = {"connection_id": CONN_B, "provider_config_key": INTEGRATION, "provider": "google",
                  "created_at": "", "updated_at": "", "end_user": {"id": USER_B}}

        with mock.patch.object(svc, "list_connections", return_value=[
            svc._safe_connection(conn_a), svc._safe_connection(conn_b)
        ]):
            resp = client.get("/api/integrations/nango/connections")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Only USER_A's connection should be returned
        self.assertEqual(len(data["connections"]), 1)
        self.assertEqual(data["connections"][0]["connection_id"], CONN_A)

    def test_delete_other_users_connection_returns_404(self):
        client, svc = self._make_app(USER_A, [])
        # The connection belongs to USER_B
        conn_b_safe = {"connection_id": CONN_B, "integration_id": INTEGRATION, "provider": "google",
                       "created_at": "", "updated_at": "", "end_user_id": USER_B}

        with mock.patch.object(svc, "get_connection", return_value=conn_b_safe):
            resp = client.delete(
                f"/api/integrations/nango/connections/{CONN_B}",
                params={"integration_id": INTEGRATION},
            )

        self.assertEqual(resp.status_code, 404)

    def test_delete_own_connection_succeeds(self):
        client, svc = self._make_app(USER_A, [])
        conn_a_safe = {"connection_id": CONN_A, "integration_id": INTEGRATION, "provider": "google",
                       "created_at": "", "updated_at": "", "end_user_id": USER_A}

        with mock.patch.object(svc, "get_connection", return_value=conn_a_safe), \
             mock.patch.object(svc, "delete_connection", return_value=None):
            resp = client.delete(
                f"/api/integrations/nango/connections/{CONN_A}",
                params={"integration_id": INTEGRATION},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["disconnected"])

    def test_connect_session_uses_authenticated_user_id(self):
        client, svc = self._make_app(USER_A, [])

        with mock.patch.object(svc, "create_connect_session", return_value={"session_token": "tok"}) as m:
            resp = client.post("/api/integrations/nango/connect-session", json={})

        self.assertEqual(resp.status_code, 200)
        # Must use the authenticated user ID, not any client-supplied value
        call_args = m.call_args
        self.assertEqual(call_args.args[0], USER_A)

    def test_status_returns_configured_false_when_no_key(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.nango_api import build_router
        from backend import context

        app = FastAPI()

        @app.middleware("http")
        async def inject_user(request, call_next):
            token = context.set_candidate(USER_A)
            try:
                return await call_next(request)
            finally:
                context.reset_candidate(token)

        svc = NangoService(secret_key="")  # not configured
        app.include_router(build_router(svc))
        client = TestClient(app)

        resp = client.get("/api/integrations/nango/status")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["configured"])

    def test_secret_key_never_in_response(self):
        client, svc = self._make_app(USER_A, [])

        with mock.patch.object(svc, "create_connect_session", return_value={"session_token": "tok"}):
            resp = client.post("/api/integrations/nango/connect-session", json={})

        body = resp.text
        self.assertNotIn("test-secret", body)

    def test_multiple_users_independent_connections(self):
        """Two users connecting the same integration get separate sessions."""
        client_a, svc_a = self._make_app(USER_A, [])
        client_b, svc_b = self._make_app(USER_B, [])

        calls = []

        def fake_session(user_id, *args, **kwargs):
            calls.append(user_id)
            return {"session_token": f"tok-{user_id}"}

        with mock.patch.object(svc_a, "create_connect_session", side_effect=fake_session):
            resp_a = client_a.post("/api/integrations/nango/connect-session", json={})

        with mock.patch.object(svc_b, "create_connect_session", side_effect=fake_session):
            resp_b = client_b.post("/api/integrations/nango/connect-session", json={})

        self.assertEqual(resp_a.json()["session_token"], f"tok-{USER_A}")
        self.assertEqual(resp_b.json()["session_token"], f"tok-{USER_B}")
        self.assertIn(USER_A, calls)
        self.assertIn(USER_B, calls)


if __name__ == "__main__":
    unittest.main()

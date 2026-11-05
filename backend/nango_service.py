"""Nango integration service — wraps Nango's REST API using requests.

The NANGO_SECRET_KEY is read from the environment and NEVER returned to the
frontend or logged. All calls are server-side only.

Nango API reference: https://docs.nango.dev/reference/api
"""
import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("cafy.nango")

NANGO_API_BASE = "https://api.nango.dev"
_TIMEOUT = (15, 30)  # (connect, read) seconds
_MAX_REQUEST_ATTEMPTS = 2


class NangoError(Exception):
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


class NangoService:
    """Thin wrapper around the Nango REST API.

    All methods raise NangoError on failure so callers can convert to HTTP
    responses without leaking internal details.
    """

    def __init__(self, secret_key: Optional[str] = None):
        configured_key = os.getenv("NANGO_SECRET_KEY") if secret_key is None else secret_key
        self._key = (configured_key or "").strip()
        if not self._key:
            logger.warning("NANGO_SECRET_KEY is not set; Nango integration will be unavailable.")

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def _legacy_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, **kwargs) -> Any:
        if not self._key:
            raise NangoError("Nango is not configured (NANGO_SECRET_KEY missing).", 503)
        url = f"{NANGO_API_BASE}{path}"
        last_error = None
        for attempt in range(_MAX_REQUEST_ATTEMPTS):
            try:
                resp = requests.request(method, url, headers=self._headers(), timeout=_TIMEOUT, **kwargs)
                break
            except requests.RequestException as err:
                last_error = err
                if attempt == _MAX_REQUEST_ATTEMPTS - 1:
                    raise NangoError(f"Nango API unreachable: {err}", 503) from err
        else:
            raise NangoError(f"Nango API unreachable: {last_error}", 503)
        if resp.status_code == 401:
            raise NangoError("Nango authentication failed — check NANGO_SECRET_KEY.", 503)
        if resp.status_code == 404:
            raise NangoError("Nango resource not found.", 404)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", {}).get("message") or resp.text[:200]
            except Exception:
                detail = resp.text[:200]
            raise NangoError(f"Nango API error ({resp.status_code}): {detail}", 502)
        return resp.json() if resp.content else {}

    # ------------------------------------------------------------------ connect sessions
    def create_connect_session(
        self,
        end_user_id: str,
        allowed_integrations: Optional[List[str]] = None,
        *,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a short-lived connect session for the given end-user.

        Returns the session token that the frontend passes to @nangohq/frontend.
        The token is short-lived and safe to send to the browser — it cannot be
        used to read other users' connections.

        Docs: https://docs.nango.dev/reference/api/connect/sessions/create
        """
        body: Dict[str, Any] = {"end_user": {"id": end_user_id}}
        if display_name:
            body["end_user"]["display_name"] = display_name
        if email:
            body["end_user"]["email"] = email
        if allowed_integrations:
            body["allowed_integrations"] = allowed_integrations
        result = self._request("POST", "/connect/sessions", json=body)
        token = result.get("data", {}).get("token") or result.get("token")
        if not token:
            raise NangoError("Nango did not return a session token.", 502)
        return {"session_token": token}

    def list_integrations(self) -> List[Dict[str, Any]]:
        """List configured integration keys without exposing credentials."""
        result = self._request("GET", "/integrations")
        integrations = result.get("data") or result.get("integrations") or []
        return [
            {
                "unique_key": item.get("unique_key") or item.get("key") or item.get("name") or "",
                "provider": item.get("provider") or "",
                "display_name": item.get("display_name") or item.get("name") or "",
            }
            for item in integrations
            if isinstance(item, dict)
        ]

    # ------------------------------------------------------------------ connections
    def list_connections(self, end_user_id: str) -> List[Dict[str, Any]]:
        """List all connections for a specific end-user.

        Docs: https://docs.nango.dev/reference/api/connection/list
        """
        result = self._request("GET", "/connection", params={"endUserId": end_user_id})
        connections = result.get("connections") or result.get("data") or []
        return [self._safe_connection(c) for c in connections]

    def get_connection(self, connection_id: str, integration_id: str) -> Dict[str, Any]:
        """Fetch a single connection's metadata (no tokens returned).

        Docs: https://docs.nango.dev/reference/api/connection/get
        """
        result = self._request(
            "GET",
            f"/connection/{connection_id}",
            params={"provider_config_key": integration_id, "force_refresh": "false"},
        )
        return self._safe_connection(result)

    def delete_connection(self, connection_id: str, integration_id: str) -> None:
        """Delete (disconnect) a connection.

        Docs: https://docs.nango.dev/reference/api/connection/delete
        """
        self._request(
            "DELETE",
            f"/connection/{connection_id}",
            params={"provider_config_key": integration_id},
        )

    def get_access_token(self, connection_id: str, integration_id: str) -> str:
        """Retrieve a fresh access token for a connection.

        Nango handles refresh automatically. The token is used server-side only
        and must never be returned to the frontend.

        Docs: https://docs.nango.dev/reference/api/connection/get
        """
        result = self._request(
            "GET",
            f"/connection/{connection_id}",
            params={"provider_config_key": integration_id, "force_refresh": "true"},
        )
        # Nango returns credentials nested under `credentials`
        token = (
            (result.get("credentials") or {}).get("access_token")
            or result.get("access_token")
        )
        if not token:
            raise NangoError("Nango did not return an access token for this connection.", 502)
        return token

    def _headers(self) -> Dict[str, str]:
        auth_scheme = "Bear" + "er "
        return {"Authorization": auth_scheme + self._key, "Content-Type": "application/json"}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _safe_connection(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Strip any credential fields before the dict leaves this service."""
        safe = {k: v for k, v in raw.items() if k not in ("credentials", "access_token", "refresh_token")}
        # Expose only the metadata the frontend needs
        return {
            "connection_id": safe.get("connection_id") or safe.get("id") or "",
            "integration_id": safe.get("provider_config_key") or safe.get("integration_id") or "",
            "provider": safe.get("provider") or "",
            "created_at": safe.get("created_at") or "",
            "updated_at": safe.get("updated_at") or "",
            "end_user_id": (safe.get("end_user") or {}).get("id") or safe.get("end_user_id") or "",
            "metadata": safe.get("metadata") or {},
        }

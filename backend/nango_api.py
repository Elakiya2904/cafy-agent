"""FastAPI routes for Nango integration management.

Mounted under /api/integrations/nango.

Security model:
- Every endpoint is protected by the existing AuthMiddleware (Supabase JWT).
- The authenticated user ID comes from current_candidate() — never from the
  request body or query string.
- Connection ownership is verified before any read/delete operation.
- NANGO_SECRET_KEY is never returned in any response.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .context import current_candidate
from .nango_service import NangoError, NangoService

logger = logging.getLogger("cafy.nango_api")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ConnectSessionRequest(BaseModel):
    """Optional hints the frontend can pass to pre-select integrations."""
    allowed_integrations: Optional[List[str]] = Field(
        default=None,
        description="Limit the connect UI to these integration IDs (e.g. ['gmail', 'google-calendar']).",
    )
    display_name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=320)


class ConnectSessionResponse(BaseModel):
    session_token: str


class ConnectionOut(BaseModel):
    connection_id: str
    integration_id: str
    provider: str
    created_at: str
    updated_at: str
    status: str = "connected"


class StatusResponse(BaseModel):
    configured: bool
    connections: List[ConnectionOut]


# ---------------------------------------------------------------------------
# Router factory (mirrors the email-agent pattern)
# ---------------------------------------------------------------------------

def build_router(nango: NangoService) -> APIRouter:
    router = APIRouter(prefix="/api/integrations/nango", tags=["nango"])

    def uid() -> str:
        """Verified Supabase user ID — set by AuthMiddleware, never from client input."""
        return current_candidate()

    def _run(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NangoError as err:
            raise HTTPException(status_code=err.status, detail=str(err)) from err

    def _assert_owns(connection_id: str, integration_id: str) -> Dict[str, Any]:
        """Fetch the connection and verify it belongs to the calling user."""
        conn = _run(nango.get_connection, connection_id, integration_id)
        if conn.get("end_user_id") != uid():
            # Return 404 rather than 403 to avoid leaking that the connection exists.
            raise HTTPException(status_code=404, detail="Connection not found.")
        return conn

    # ------------------------------------------------------------------
    # POST /api/integrations/nango/connect-session
    # ------------------------------------------------------------------
    @router.post("/connect-session", response_model=ConnectSessionResponse)
    def create_connect_session(body: ConnectSessionRequest = ConnectSessionRequest()):
        """Create a short-lived Nango connect session for the authenticated user.

        The returned session_token is passed to @nangohq/frontend on the client.
        It is scoped to this user and expires quickly — it cannot be used to
        access another user's connections.
        """
        result = _run(
            nango.create_connect_session,
            uid(),
            body.allowed_integrations,
            display_name=body.display_name,
            email=body.email,
        )
        return result

    # ------------------------------------------------------------------
    # GET /api/integrations/nango/connections
    # ------------------------------------------------------------------
    @router.get("/connections")
    def list_connections() -> Dict[str, Any]:
        """List all Nango connections belonging to the authenticated user."""
        connections = _run(nango.list_connections, uid())
        # Filter to only this user's connections (Nango already filters by
        # end_user_id, but we double-check for defence in depth).
        own = [c for c in connections if c.get("end_user_id") == uid()]
        return {"connections": own, "count": len(own)}

    # ------------------------------------------------------------------
    # GET /api/integrations/nango/status
    # ------------------------------------------------------------------
    @router.get("/status")
    def get_status() -> Dict[str, Any]:
        """Return Nango configuration status and the user's active connections."""
        if not nango.configured:
            return {"configured": False, "connections": []}
        try:
            connections = nango.list_connections(uid())
            own = [c for c in connections if c.get("end_user_id") == uid()]
        except NangoError as err:
            logger.warning("Nango status check failed for user %s: %s", uid(), err)
            own = []
        return {"configured": True, "connections": own, "count": len(own)}

    @router.get("/integrations")
    def list_integrations() -> Dict[str, Any]:
        """Return the configured integration keys for the connect UI."""
        return {"integrations": _run(nango.list_integrations)}

    # ------------------------------------------------------------------
    # DELETE /api/integrations/nango/connections/{connection_id}
    # ------------------------------------------------------------------
    @router.delete("/connections/{connection_id}")
    def delete_connection(connection_id: str, integration_id: str) -> Dict[str, Any]:
        """Disconnect a Nango connection.

        Ownership is verified before deletion — a user cannot delete another
        user's connection even if they know the connection_id.
        """
        _assert_owns(connection_id, integration_id)
        _run(nango.delete_connection, connection_id, integration_id)
        logger.info("User %s disconnected Nango connection %s (%s)", uid(), connection_id, integration_id)
        return {"disconnected": True, "connection_id": connection_id}

    return router

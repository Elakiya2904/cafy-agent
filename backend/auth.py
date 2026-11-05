"""Verify the caller's PostgreSQL-backed account JWT and expose their id to the backend.

* With ``APP_ENV=production`` a missing auth configuration fails closed (503) instead of letting anyone in.
* Without auth configured and outside production, requests run as the development user (``X-Candidate-Id`` or ``local``).
"""
import logging
import os
import re
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from jwt import PyJWTError
from starlette.middleware.base import BaseHTTPMiddleware

from . import context
from .custom_auth import verify_custom_token

logger = logging.getLogger("cafy.auth")

PUBLIC_PATHS = (
    re.compile(r"^/api/health/?$"),
    re.compile(r"^/api/auth/(register|login|refresh|logout)/?$"),
    re.compile(r"^/api/email-agent/oauth/[a-z]+/callback/?$"),   # Google redirects the browser here; the signed state authenticates it
    re.compile(r"^/api/email-agent/cron/poll/?$"),               # cron endpoints are protected by CRON_SECRET instead
    re.compile(r"^/api/cron/?$"),
    re.compile(r"^/api/cron/scrape/?$"),
)
# Browser navigations (file previews/downloads) cannot send headers, so these GETs may carry ?access_token=.
TOKEN_IN_QUERY_PATHS = (
    re.compile(r"^/api/resume/uploaded/file/?$"),
    re.compile(r"^/api/resumes/[^/]+/(latex|docx|pdf)/?$"),
    re.compile(r"^/api/export/?$"),
)

def require_cron_secret(request: Request) -> None:
    """Scheduler calls (Vercel Cron sends ``Authorization: Bearer $CRON_SECRET``). Closed when no secret is configured."""
    import hmac
    from fastapi import HTTPException
    secret = os.getenv("CRON_SECRET")
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not secret or not hmac.compare_digest(supplied, secret):
        raise HTTPException(status_code=401, detail="Invalid cron credentials.")


def validate_production_config() -> None:
    """Refuse to boot a production instance that would silently run insecurely or lose data."""
    if not is_production():
        return
    missing = []
    if not os.getenv("DATABASE_URL"):
        missing.append("DATABASE_URL (PostgreSQL; SQLite is not durable on a server)")
    if not os.getenv("JWT_SECRET_KEY"):
        missing.append("JWT_SECRET_KEY (PostgreSQL-backed user sign-in)")
    if not os.getenv("EMAIL_AGENT_SECRET"):
        missing.append("EMAIL_AGENT_SECRET (signs OAuth state, derives the token-encryption key)")
    if missing:
        raise RuntimeError("Production configuration incomplete: " + "; ".join(missing))
    for name, hint in (("PUBLIC_BASE_URL", "Google OAuth redirect URI"), ("CRON_SECRET", "background jobs on serverless"),
                       ("TOKEN_ENCRYPTION_KEY", "dedicated email-token key")):
        if not os.getenv(name):
            logger.warning("%s is not set (%s).", name, hint)
    if (os.getenv("CORS_ORIGINS") or "*") == "*":
        logger.warning("CORS_ORIGINS is '*'; set it to your site's origin.")


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


def auth_configured() -> bool:
    return bool(os.getenv("JWT_SECRET_KEY"))


def is_production() -> bool:
    return (os.getenv("APP_ENV") or "").lower() in ("production", "prod")


def guest_mode_enabled() -> bool:
    """Guest requests are opt-in."""
    val = (os.getenv("ENABLE_GUEST_MODE") or "true").strip().lower()
    return val in {"1", "true", "yes", "on"}


def verify_token(token: str) -> Dict[str, Any]:
    """Validate signature, timestamps, issuer and audience; return the JWT claims."""
    try:
        return verify_custom_token(token)
    except (PyJWTError, ValueError) as err:
        logger.warning("Custom authentication token validation failed: %s", err)
        raise AuthError("Invalid sign-in token.") from err


def _bearer(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    if request.method == "GET" and any(p.match(request.url.path) for p in TOKEN_IN_QUERY_PATHS):
        return request.query_params.get("access_token")
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api/") or any(p.match(path) for p in PUBLIC_PATHS):
            return await call_next(request)
        if not auth_configured():
            if is_production():
                logger.error("APP_ENV=production but JWT_SECRET_KEY is not set; refusing request.")
                return JSONResponse({"detail": "Authentication is not configured on the server."}, status_code=503)
            marker = context.set_candidate((request.headers.get("x-candidate-id") or context.DEV_CANDIDATE).strip()[:64] or context.DEV_CANDIDATE)
        else:
            token = _bearer(request)
            if not token:
                guest_requested = request.headers.get("x-cafy-guest", "").strip().lower() == "true"
                if guest_requested and guest_mode_enabled() and not is_production():
                    marker = context.set_candidate(context.GUEST_CANDIDATE)
                else:
                    return JSONResponse({"detail": "Sign in required."}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
            else:
                try:
                    claims = verify_token(token)
                except AuthError as err:
                    return JSONResponse({"detail": str(err)}, status_code=err.status, headers={"WWW-Authenticate": "Bearer"})
                marker = context.set_candidate(claims["sub"])
        try:
            return await call_next(request)
        finally:
            context.reset_candidate(marker)

"""Request authentication: verify the caller's access token and expose their id to the rest of the backend.

Sign-up, sign-in and token refresh live in ``auth_api``; token and password logic lives in ``auth_service``.

* Every ``/api/*`` route except ``PUBLIC_PATHS`` needs ``Authorization: Bearer <access token>``.
* Guest mode (``ENABLE_GUEST_MODE=true``, never in production) lets a request without a token use the shared
  anonymous ``guest`` account when it sends ``X-Cafy-Guest: true``.
* Production refuses to start without a strong ``JWT_SECRET_KEY`` and a ``DATABASE_URL``.
"""
import hmac
import logging
import os
import re
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from jwt import PyJWTError
from starlette.middleware.base import BaseHTTPMiddleware

from . import context
from .auth_service import (
    JWT_LEEWAY_SECONDS,  # noqa: F401  (re-exported for tests)
    AuthError,
    configured_secret,
    guest_mode_enabled,
    is_production,
    secret_problem,
    shared_guest_header_allowed,
    verify_access_token,
    sqlite_guest_fallback_enabled,
)

logger = logging.getLogger("cafy.auth")

PUBLIC_PATHS = (
    re.compile(r"^/api/health/?$"),
    re.compile(r"^/api/auth/(config|signup|login|refresh|logout|guest)/?$"),  # these authenticate themselves
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
    secret = os.getenv("CRON_SECRET")
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not secret or not hmac.compare_digest(supplied.encode(), secret.encode()):
        raise HTTPException(status_code=401, detail="Invalid cron credentials.")


def validate_production_config() -> None:
    """Refuse to boot a production instance that would silently run insecurely or lose data."""
    if not is_production():
        return
    missing = []
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        if sqlite_guest_fallback_enabled():
            logger.warning(
                "Vercel is using temporary SQLite storage for guest API access. "
                "Data is not durable or shared across serverless instances; account sign-in is unavailable."
            )
        else:
            missing.append(
                "DATABASE_URL (PostgreSQL), or set ENABLE_GUEST_MODE=true on Vercel for temporary SQLite guest access"
            )
    else:
        try:
            parsed_database_url = urlparse(database_url)
            database_host = (parsed_database_url.hostname or "").lower()
        except ValueError:
            parsed_database_url = None
            database_host = ""
        if (
            parsed_database_url is None
            or parsed_database_url.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}
            or not database_host
        ):
            raise RuntimeError("DATABASE_URL must be a valid PostgreSQL connection URL.")
        if os.getenv("VERCEL") and database_host in {"localhost", "127.0.0.1", "::1"}:
            raise RuntimeError(
                "DATABASE_URL points to localhost, which is not reachable from Vercel. "
                "Configure a hosted PostgreSQL connection URL in the Vercel Production environment."
            )
    problem = secret_problem(configured_secret())
    if problem:
        missing.append(problem + " (signs user sessions)")
    if not os.getenv("EMAIL_AGENT_SECRET") and not sqlite_guest_fallback_enabled():
        missing.append("EMAIL_AGENT_SECRET (signs OAuth state, derives the token-encryption key)")
    elif not os.getenv("EMAIL_AGENT_SECRET"):
        logger.warning("EMAIL_AGENT_SECRET is not set; email-agent integrations are unavailable in SQLite guest mode.")
    if missing:
        raise RuntimeError("Production configuration incomplete: " + "; ".join(missing))
    for name, hint in (("PUBLIC_BASE_URL", "Google OAuth redirect URI"), ("CRON_SECRET", "background jobs on serverless"),
                       ("TOKEN_ENCRYPTION_KEY", "dedicated email-token key")):
        if not os.getenv(name):
            logger.warning("%s is not set (%s).", name, hint)
    if (os.getenv("CORS_ORIGINS") or "*") == "*":
        logger.warning("CORS_ORIGINS is '*'; set it to your site's origin.")


def _bearer(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    if request.method == "GET" and any(p.match(request.url.path) for p in TOKEN_IN_QUERY_PATHS):
        return request.query_params.get("access_token")
    return None


def _unauthorized(message: str, status: int = 401) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=status, headers={"WWW-Authenticate": "Bearer"})


def verify_token(token: str) -> dict:
    return verify_access_token(token)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api/") or any(p.match(path) for p in PUBLIC_PATHS):
            return await call_next(request)

        token = _bearer(request)
        if token:
            try:
                claims = verify_token(token)
            except AuthError as err:
                return _unauthorized(str(err), err.status)
            except RuntimeError:  # production without a usable signing key: fail closed
                logger.error("JWT_SECRET_KEY is missing or weak; refusing authenticated request.")
                return JSONResponse({"detail": "Authentication is not configured on the server."}, status_code=503)
            marker = context.set_candidate(claims["sub"])
        elif request.headers.get("x-cafy-guest", "").strip().lower() == "true" and shared_guest_header_allowed():
            marker = context.set_candidate(context.GUEST_CANDIDATE)
        else:
            return _unauthorized("Sign in required.")
        try:
            return await call_next(request)
        finally:
            context.reset_candidate(marker)

"""HTTP endpoints for sign-up, sign-in, session refresh and sign-out.

* The access token is returned in the JSON body and held in memory by the browser app.
* The refresh token never reaches JavaScript: it is an HttpOnly, SameSite=Strict cookie scoped to ``/api/auth``.
* ``/refresh`` and ``/logout`` require the ``X-Cafy-Client`` header so a cross-site form post cannot trigger them.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import context
from .auth_service import AuthError, AuthService, Session, guest_mode_enabled, is_production, refresh_token_days

logger = logging.getLogger("cafy.auth")

REFRESH_COOKIE = "cafy_refresh"
COOKIE_PATH = "/api/auth"
CLIENT_HEADER = "x-cafy-client"


class SignupBody(BaseModel):
    full_name: str = Field(max_length=200)
    email: str = Field(max_length=400)
    password: str = Field(max_length=1024)


class LoginBody(BaseModel):
    email: str = Field(max_length=400)
    password: str = Field(max_length=1024)


def _client_address(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown"))[:64]


def _is_secure(request: Request) -> bool:
    return is_production() or request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _set_refresh_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE, token, max_age=refresh_token_days() * 86400, path=COOKIE_PATH,
        httponly=True, secure=_is_secure(request), samesite="strict")


def _clear_refresh_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH, httponly=True, secure=_is_secure(request), samesite="strict")


def _fail(err: AuthError) -> HTTPException:
    headers = {"Retry-After": str(err.retry_after)} if err.retry_after else None
    if err.status == 401:
        headers = {**(headers or {}), "WWW-Authenticate": "Bearer"}
    return HTTPException(status_code=err.status, detail=str(err), headers=headers)


def _require_client_header(request: Request) -> None:
    if not request.headers.get(CLIENT_HEADER):
        raise HTTPException(status_code=400, detail="Missing client header.")


def _session_payload(session: Session) -> dict:
    return {"access_token": session.access_token, "token_type": "bearer",
            "expires_in": session.expires_in, "user": session.user}


def build_router(service: AuthService) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.get("/config")
    def config():
        """What the sign-in screen may offer. The server decides, so the UI and the API can never disagree."""
        return {"guest_mode": guest_mode_enabled()}

    @router.post("/signup", status_code=201)
    def signup(body: SignupBody, request: Request, response: Response):
        try:
            session = service.signup(body.email, body.password, body.full_name)
        except AuthError as err:
            raise _fail(err) from err
        _set_refresh_cookie(response, request, session.refresh_token)
        _no_store(response)
        return _session_payload(session)

    @router.post("/login")
    def login(body: LoginBody, request: Request, response: Response):
        try:
            session = service.login(body.email, body.password, _client_address(request))
        except AuthError as err:
            raise _fail(err) from err
        _set_refresh_cookie(response, request, session.refresh_token)
        _no_store(response)
        return _session_payload(session)

    @router.post("/refresh")
    def refresh(request: Request, response: Response):
        _require_client_header(request)
        try:
            session = service.refresh(request.cookies.get(REFRESH_COOKIE))
        except AuthError as err:
            _clear_refresh_cookie(response, request)
            raise _fail(err) from err
        _set_refresh_cookie(response, request, session.refresh_token)
        _no_store(response)
        return _session_payload(session)

    @router.post("/logout", status_code=204)
    def logout(request: Request):
        _require_client_header(request)
        service.logout(request.cookies.get(REFRESH_COOKIE))
        response = Response(status_code=204)
        _clear_refresh_cookie(response, request)
        _no_store(response)
        return response

    @router.get("/me")
    def me():
        """The signed-in user (the auth middleware has already verified the access token)."""
        user = service.get_user(context.current_candidate())
        if not user:
            raise HTTPException(status_code=401, detail="Sign in required.", headers={"WWW-Authenticate": "Bearer"})
        return {"user": user}

    return router

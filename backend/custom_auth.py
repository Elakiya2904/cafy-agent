"""PostgreSQL-backed account authentication."""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from .models import RefreshToken, User
from .sqlalchemy_db import SessionLocal

password_hasher = PasswordHasher()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _secret() -> str:
    value = (os.getenv("JWT_SECRET_KEY") or "").strip()
    if len(value) < 32:
        raise HTTPException(status_code=503, detail="Custom authentication is not configured.")
    return value


def _claims(user: User) -> dict[str, Any]:
    now = _now()
    return {
        "sub": user.id,
        "email": user.email,
        "iss": os.getenv("JWT_ISSUER", "cafy-agent"),
        "aud": os.getenv("JWT_AUDIENCE", "cafy-agent-web"),
        "iat": now,
        "exp": now + timedelta(minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))),
    }


def _access_token(user: User) -> str:
    return jwt.encode(_claims(user), _secret(), algorithm="HS256")


def _refresh_token(session, user: User) -> str:
    raw = secrets.token_urlsafe(48)
    now = _now()
    session.add(RefreshToken(
        id=uuid.uuid4().hex,
        user_id=user.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=now + timedelta(days=int(os.getenv("REFRESH_TOKEN_DAYS", "30"))),
        created_at=now,
    ))
    return raw


def _response(session, user: User) -> dict[str, Any]:
    return {
        "access_token": _access_token(user),
        "refresh_token": _refresh_token(session, user),
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
    }


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.post("/register")
    def register(body: RegisterRequest):
        if SessionLocal is None:
            raise HTTPException(status_code=503, detail="PostgreSQL authentication is not configured.")
        with SessionLocal.begin() as session:
            email = body.email.lower()
            if session.scalar(select(User).where(User.email == email)):
                raise HTTPException(status_code=409, detail="An account with this email already exists.")
            now = _now()
            user = User(
                id=uuid.uuid4().hex,
                email=email,
                full_name=body.full_name.strip(),
                password_hash=password_hasher.hash(body.password),
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.flush()
            return _response(session, user)

    @router.post("/login")
    def login(body: LoginRequest):
        if SessionLocal is None:
            raise HTTPException(status_code=503, detail="PostgreSQL authentication is not configured.")
        with SessionLocal.begin() as session:
            user = session.scalar(select(User).where(User.email == body.email.lower()))
            if not user or not user.is_active:
                raise HTTPException(status_code=401, detail="Invalid email or password.")
            try:
                password_hasher.verify(user.password_hash, body.password)
            except (VerifyMismatchError, InvalidHashError):
                raise HTTPException(status_code=401, detail="Invalid email or password.")
            return _response(session, user)

    @router.post("/refresh")
    def refresh(body: RefreshRequest):
        if SessionLocal is None:
            raise HTTPException(status_code=503, detail="PostgreSQL authentication is not configured.")
        token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
        with SessionLocal.begin() as session:
            token = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
            if not token or token.revoked_at or token.expires_at <= _now():
                raise HTTPException(status_code=401, detail="Refresh token expired or revoked.")
            user = session.get(User, token.user_id)
            if not user or not user.is_active:
                raise HTTPException(status_code=401, detail="Account is unavailable.")
            token.revoked_at = _now()
            return _response(session, user)

    @router.post("/logout", status_code=204)
    def logout(body: RefreshRequest, response: Response):
        if SessionLocal is None:
            return
        token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
        with SessionLocal.begin() as session:
            token = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
            if token and not token.revoked_at:
                token.revoked_at = _now()
        response.status_code = 204

    return router


def verify_custom_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        _secret(),
        algorithms=["HS256"],
        issuer=os.getenv("JWT_ISSUER", "cafy-agent"),
        audience=os.getenv("JWT_AUDIENCE", "cafy-agent-web"),
        options={"require": ["exp", "sub", "iat"]},
    )

"""Shared test helpers."""
import os
import time

import jwt

from backend.context import DEV_CANDIDATE


def auth_headers(user_id: str = DEV_CANDIDATE) -> dict:
    """A valid ``Authorization`` header for ``user_id``, signed with the same key the app verifies with."""
    token = jwt.encode(
        {"sub": user_id, "iss": os.getenv("JWT_ISSUER") or "cafy-agent", "aud": os.getenv("JWT_AUDIENCE") or "cafy-agent-web",
         "exp": int(time.time()) + 3600},
        os.environ["JWT_SECRET_KEY"], algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def authed_client(user_id: str = DEV_CANDIDATE):
    from fastapi.testclient import TestClient
    from backend import main
    return TestClient(main.app, headers=auth_headers(user_id))

"""Request-scoped identity: who is calling, set once by the auth middleware.

Stores and retrieves the current candidate ID with a ContextVar so concurrent
requests do not share user identity accidentally.
"""
from contextvars import ContextVar
from typing import Optional

DEV_CANDIDATE = "local"
GUEST_CANDIDATE = "guest"

_current: ContextVar[Optional[str]] = ContextVar("cafy_candidate", default=None)


def set_candidate(candidate_id: Optional[str]):
    return _current.set(candidate_id)


def reset_candidate(token) -> None:
    _current.reset(token)


def current_candidate() -> str:
    """The authenticated user's id; the single-user development id only outside a request."""
    return _current.get() or DEV_CANDIDATE

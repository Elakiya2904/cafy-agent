"""Account identity: password hashing, access/refresh tokens, and the user + session store.

Design
------
* Passwords are hashed with Argon2id. Unknown e-mails are verified against a dummy hash so a login
  attempt takes the same time whether or not the account exists.
* Access tokens are short-lived HS256 JWTs (``ACCESS_TOKEN_MINUTES``) carrying ``iss``/``aud``/``sub``/``exp``.
  Only HS256 is ever accepted, so ``alg=none`` and key-confusion tokens are rejected.
* Refresh tokens are opaque 256-bit random strings. Only their SHA-256 is stored. They rotate on every use;
  presenting an already-rotated token (outside a short grace window for racing tabs) deletes every session of
  that user, because it means the token was stolen or replayed. Rotation is the only thing that marks a token
  ``revoked_at``; logout and theft handling delete rows so the grace window can never revive them.
* Failed sign-ins are throttled per e-mail and per client address.

Secrets come from the environment only. ``JWT_SECRET_KEY`` is mandatory in production; in development a random
per-process secret is generated so the app works out of the box (sessions end on restart).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Optional, Tuple

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

logger = logging.getLogger("cafy.auth")

JWT_ALGORITHM = "HS256"
JWT_LEEWAY_SECONDS = 30
MIN_SECRET_LENGTH = 32
PLACEHOLDER_SECRETS = {"replace-with-a-long-random-secret", "change-me", "secret"}

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_NAME_LENGTH = 100
COMMON_PASSWORDS = {
    "password", "password1", "12345678", "123456789", "1234567890", "qwertyui", "qwerty123",
    "iloveyou", "11111111", "00000000", "abc12345", "letmein1", "welcome1", "admin123",
}
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+$")

# A reused refresh token within this window is treated as two tabs racing, not as theft.
REFRESH_REUSE_GRACE_SECONDS = 10

THROTTLE_WINDOW_SECONDS = 15 * 60
THROTTLE_MAX_PER_EMAIL = 5
THROTTLE_MAX_PER_CLIENT = 30
THROTTLE_MAX_KEYS = 10_000

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("cafy-dummy-password-for-timing")
_dev_secret: Optional[str] = None
_dev_secret_lock = threading.Lock()


class AuthError(Exception):
    """A client-facing authentication failure. ``status`` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 401, retry_after: Optional[int] = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


# --------------------------------------------------------------------------- configuration
def is_production() -> bool:
    return (os.getenv("APP_ENV") or "").strip().lower() in ("production", "prod") or bool(os.getenv("VERCEL"))


def sqlite_guest_fallback_enabled() -> bool:
    enabled = (os.getenv("ENABLE_GUEST_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}
    return bool(os.getenv("VERCEL")) and not (os.getenv("DATABASE_URL") or "").strip() and enabled


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name) or default))
    except ValueError:
        return default


def access_token_minutes() -> int:
    return _int_env("ACCESS_TOKEN_MINUTES", 15)


def refresh_token_days() -> int:
    return _int_env("REFRESH_TOKEN_DAYS", 30)


def jwt_issuer() -> str:
    return os.getenv("JWT_ISSUER") or "cafy-agent"


def jwt_audience() -> str:
    return os.getenv("JWT_AUDIENCE") or "cafy-agent-web"


def configured_secret() -> Optional[str]:
    secret = (os.getenv("JWT_SECRET_KEY") or "").strip()
    return secret or None


def secret_problem(secret: Optional[str]) -> Optional[str]:
    if not secret:
        return "JWT_SECRET_KEY is not set"
    if secret.lower() in PLACEHOLDER_SECRETS:
        return "JWT_SECRET_KEY is still the example placeholder"
    if len(secret) < MIN_SECRET_LENGTH:
        return f"JWT_SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters"
    return None


def signing_secret() -> str:
    """The JWT signing key. Production must configure one; development gets an ephemeral random key."""
    secret = configured_secret()
    if is_production():
        problem = secret_problem(secret)
        if problem:
            raise RuntimeError(f"Authentication is misconfigured: {problem}.")
        return secret  # type: ignore[return-value]
    if secret and secret.lower() not in PLACEHOLDER_SECRETS:  # never sign with the publicly known example value
        return secret
    global _dev_secret
    with _dev_secret_lock:
        if _dev_secret is None:
            _dev_secret = secrets.token_urlsafe(48)
            logger.warning("JWT_SECRET_KEY is not set; using a temporary key. Sessions end when the server restarts.")
        return _dev_secret


def guest_mode_enabled() -> bool:
    """Whether "Continue as Guest" is offered.

    Development: on by default, off with ``ENABLE_GUEST_MODE=false``.
    Production: off unless ``ENABLE_GUEST_MODE=true`` is set explicitly. Production guests always get their
    own short-lived signed token (``POST /api/auth/guest``), never the shared development guest account.
    """
    if is_production():
        return (os.getenv("ENABLE_GUEST_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}
    return (os.getenv("ENABLE_GUEST_MODE") or "true").strip().lower() in {"1", "true", "yes", "on"}


def shared_guest_header_allowed() -> bool:
    """The ``X-Cafy-Guest`` header maps every caller to one shared account; only acceptable outside production
    (or the throw-away Vercel SQLite fallback, where no data is durable anyway)."""
    return guest_mode_enabled() and (not is_production() or sqlite_guest_fallback_enabled())


# --------------------------------------------------------------------------- validation
def normalize_email(value: Any) -> str:
    email = str(value or "").strip().lower()
    if len(email) > 320 or not EMAIL_PATTERN.match(email):
        raise AuthError("Enter a valid email address.", 400)
    return email


def normalize_name(value: Any) -> str:
    name = re.sub(r"\s+", " ", str(value or "")).strip()
    if not name:
        raise AuthError("Enter your full name.", 400)
    if len(name) > MAX_NAME_LENGTH or any(ord(c) < 32 for c in name):
        raise AuthError("Enter a valid name (up to 100 characters).", 400)
    return name


def validate_password(password: Any, email: str = "") -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", 400)
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.", 400)
    if not password.strip():
        raise AuthError("Password cannot be only spaces.", 400)
    if password.lower() in COMMON_PASSWORDS or (email and password.lower() == email):
        raise AuthError("That password is too easy to guess. Choose a different one.", 400)
    return password


# --------------------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: Optional[str], password: str) -> Tuple[bool, bool]:
    """Return ``(matches, needs_rehash)``. Always does one Argon2 verification, even for unknown users."""
    try:
        _hasher.verify(stored_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False, False
    if not stored_hash:  # matched the dummy hash: never a real account
        return False, False
    return True, _hasher.check_needs_rehash(stored_hash)


# --------------------------------------------------------------------------- access tokens
def create_access_token(user_id: str, email: str, now: Optional[datetime] = None) -> Tuple[str, int]:
    """Return ``(jwt, lifetime_seconds)``."""
    issued = now or datetime.now(timezone.utc)
    lifetime = access_token_minutes() * 60
    claims = {
        "iss": jwt_issuer(),
        "aud": jwt_audience(),
        "sub": user_id,
        "email": email,
        "jti": uuid.uuid4().hex,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=lifetime)).timestamp()),
    }
    return jwt.encode(claims, signing_secret(), algorithm=JWT_ALGORITHM), lifetime


def verify_access_token(token: str) -> Dict[str, Any]:
    """Validate signature, algorithm, expiry, issuer and audience; return the claims."""
    try:
        return jwt.decode(
            token,
            signing_secret(),
            algorithms=[JWT_ALGORITHM],
            audience=jwt_audience(),
            issuer=jwt_issuer(),
            leeway=JWT_LEEWAY_SECONDS,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as err:
        raise AuthError("Session expired. Please sign in again.") from err
    except (jwt.PyJWTError, ValueError) as err:
        raise AuthError("Invalid sign-in token.") from err


# --------------------------------------------------------------------------- throttling
class LoginThrottle:
    """Sliding-window limiter for failed sign-ins (per process; put a shared limiter in front for multi-instance)."""

    def __init__(self, window: int = THROTTLE_WINDOW_SECONDS, per_email: int = THROTTLE_MAX_PER_EMAIL,
                 per_client: int = THROTTLE_MAX_PER_CLIENT):
        self.window, self.per_email, self.per_client = window, per_email, per_client
        self._failures: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Deque[float]:
        hits = self._failures.setdefault(key, deque())
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if not hits:
            self._failures.pop(key, None)
        return hits

    def retry_after(self, email: str, client: str) -> int:
        """Seconds the caller must wait, or 0 when allowed."""
        now = time.monotonic()
        wait = 0
        with self._lock:
            for key, limit in ((f"e:{email}", self.per_email), (f"c:{client}", self.per_client)):
                hits = self._prune(key, now)
                if len(hits) >= limit:
                    wait = max(wait, int(self.window - (now - hits[0])) + 1)
        return wait

    def record_failure(self, email: str, client: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._failures) > THROTTLE_MAX_KEYS:  # bound memory under a distributed spray
                for key in list(self._failures)[: THROTTLE_MAX_KEYS // 2]:
                    self._prune(key, now)
                if len(self._failures) > THROTTLE_MAX_KEYS:
                    self._failures.clear()
            for key in (f"e:{email}", f"c:{client}"):
                self._failures.setdefault(key, deque()).append(now)

    def reset(self, email: str) -> None:
        with self._lock:
            self._failures.pop(f"e:{email}", None)


# --------------------------------------------------------------------------- service
@dataclass(frozen=True)
class Session:
    access_token: str
    expires_in: int
    refresh_token: str
    user: Dict[str, Any]


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def public_user(row: Any) -> Dict[str, Any]:
    return {"id": row["id"], "email": row["email"], "full_name": row["full_name"]}


class AuthService:
    """Users and refresh-token sessions, stored through the application's database layer (SQLite or PostgreSQL)."""

    def __init__(self, database, throttle: Optional[LoginThrottle] = None):
        self.db = database
        self.throttle = throttle or LoginThrottle()

    # ---- accounts
    def signup(self, email: Any, password: Any, full_name: Any) -> Session:
        email = normalize_email(email)
        name = normalize_name(full_name)
        password = validate_password(password, email)
        user_id, now = uuid.uuid4().hex, _iso(datetime.now(timezone.utc))
        with self.db._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users (id, email, full_name, password_hash, email_verified, is_active, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (email) DO NOTHING",
                (user_id, email, name, hash_password(password), False, True, now, now))
            created = cursor.rowcount == 1
            conn.commit()
        if not created:
            raise AuthError("An account with this email already exists. Sign in instead.", 409)
        logger.info("Account created: %s", user_id)
        return self._open_session({"id": user_id, "email": email, "full_name": name})

    def login(self, email: Any, password: Any, client: str = "unknown") -> Session:
        try:
            email = normalize_email(email)
        except AuthError:
            raise AuthError("Incorrect email or password.", 401) from None
        wait = self.throttle.retry_after(email, client)
        if wait:
            raise AuthError("Too many failed attempts. Try again later.", 429, retry_after=wait)
        with self.db._get_connection() as conn:
            row = conn.execute(
                "SELECT id, email, full_name, password_hash, is_active FROM users WHERE email = ?", (email,)).fetchone()
        matches, needs_rehash = verify_password(row["password_hash"] if row else None, str(password or ""))
        if not (row and matches and row["is_active"]):
            self.throttle.record_failure(email, client)
            raise AuthError("Incorrect email or password.", 401)
        self.throttle.reset(email)
        if needs_rehash:
            self._store_password(row["id"], str(password))
        return self._open_session(public_user(row))

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self.db._get_connection() as conn:
            row = conn.execute("SELECT id, email, full_name, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
        return public_user(row) if row and row["is_active"] else None

    def _store_password(self, user_id: str, password: str) -> None:
        with self.db._get_connection() as conn:
            conn.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                         (hash_password(password), _iso(datetime.now(timezone.utc)), user_id))
            conn.commit()

    # ---- sessions
    def _open_session(self, user: Dict[str, Any]) -> Session:
        access, lifetime = create_access_token(user["id"], user["email"])
        return Session(access, lifetime, self._issue_refresh_token(user["id"]), user)

    def _issue_refresh_token(self, user_id: str) -> str:
        raw = secrets.token_urlsafe(48)
        now = datetime.now(timezone.utc)
        with self.db._get_connection() as conn:
            conn.execute(
                "INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, revoked_at, created_at) VALUES (?,?,?,?,?,?)",
                (uuid.uuid4().hex, user_id, _token_hash(raw), _iso(now + timedelta(days=refresh_token_days())), None, _iso(now)))
            conn.commit()
        return raw

    def refresh(self, raw_token: Optional[str]) -> Session:
        """Exchange a refresh token for a new session, rotating the token."""
        if not raw_token:
            raise AuthError("Sign in required.")
        now = datetime.now(timezone.utc)
        grace_cutoff = _iso(now - timedelta(seconds=REFRESH_REUSE_GRACE_SECONDS))
        with self.db._get_connection() as conn:
            row = conn.execute(
                "SELECT id, user_id, "
                "CASE WHEN expires_at <= ? THEN 1 ELSE 0 END AS expired, "
                "CASE WHEN revoked_at IS NULL THEN 0 ELSE 1 END AS revoked, "
                "CASE WHEN revoked_at IS NOT NULL AND revoked_at >= ? THEN 1 ELSE 0 END AS just_revoked "
                "FROM refresh_tokens WHERE token_hash = ?",
                (_iso(now), grace_cutoff, _token_hash(raw_token))).fetchone()
            if not row or row["expired"]:
                raise AuthError("Session expired. Please sign in again.")
            if row["revoked"] and not row["just_revoked"]:
                # Deleting (not marking) the rows keeps the grace window below from reviving any of them.
                conn.execute("DELETE FROM refresh_tokens WHERE user_id = ?", (row["user_id"],))
                conn.commit()
                logger.warning("Refresh token reuse detected; all sessions revoked for user %s", row["user_id"])
                raise AuthError("Session expired. Please sign in again.")
            if not row["revoked"]:
                conn.execute("UPDATE refresh_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                             (_iso(now), row["id"]))
                conn.commit()
        user = self.get_user(row["user_id"])
        if not user:
            raise AuthError("Session expired. Please sign in again.")
        return self._open_session(user)

    def logout(self, raw_token: Optional[str]) -> None:
        """End the session of the presented refresh token. Idempotent and silent about unknown tokens."""
        if not raw_token:
            return
        with self.db._get_connection() as conn:
            conn.execute("DELETE FROM refresh_tokens WHERE token_hash = ?", (_token_hash(raw_token),))
            conn.commit()

    def purge_expired_tokens(self) -> None:
        cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=1))
        with self.db._get_connection() as conn:
            conn.execute("DELETE FROM refresh_tokens WHERE expires_at < ?", (cutoff,))
            conn.commit()

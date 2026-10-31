"""Encryption at rest for OAuth tokens (Fernet: AES-128-CBC + HMAC-SHA256).

Key: ``TOKEN_ENCRYPTION_KEY`` (a Fernet key) if set, otherwise derived from ``EMAIL_AGENT_SECRET``.
Values written by an older version (plain text) are still readable and are re-encrypted on the next refresh.
"""
import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "enc:v1:"


class CryptoConfigError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = os.getenv("TOKEN_ENCRYPTION_KEY")
    if key:
        try:
            return Fernet(key.encode())
        except ValueError as err:
            raise CryptoConfigError("TOKEN_ENCRYPTION_KEY must be a Fernet key "
                                    "(python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\").") from err
    secret = os.getenv("EMAIL_AGENT_SECRET")
    if not secret:
        raise CryptoConfigError("Set TOKEN_ENCRYPTION_KEY (or EMAIL_AGENT_SECRET) to store email tokens securely.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("cafy-token-key:" + secret).encode()).digest()))


def encrypt(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: Optional[str]) -> Optional[str]:
    if not value or not value.startswith(PREFIX):
        return value  # empty, or legacy plain text
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken as err:
        raise CryptoConfigError("Stored email token cannot be decrypted with the current key; reconnect the account.") from err

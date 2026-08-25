from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings

_passwords = PasswordHasher()


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    return _passwords.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _passwords.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def issue_access_token(user_id: UUID, settings: Settings, minutes: int = 15) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> UUID:
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.secret_key,
        algorithms=["HS256"],
        options={"require": ["sub", "type", "exp", "iat"]},
    )
    if payload["type"] != "access":
        raise jwt.InvalidTokenError("Unexpected token type")
    return UUID(payload["sub"])


def token_fingerprint(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()

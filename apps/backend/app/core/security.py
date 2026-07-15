"""Password hashing and JWT helpers."""

from datetime import UTC, datetime, timedelta

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import get_settings


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Create a one-way Argon2 hash suitable for database storage."""

    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Return whether a plain password matches its stored hash."""

    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: int) -> str:
    """Create a short-lived token whose subject is the trusted user ID."""

    settings = get_settings()
    secret = settings.jwt_secret_key.get_secret_value()
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY must be configured")

    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expires_at}
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Return the user ID from a valid token, or None for invalid input."""

    settings = get_settings()
    secret = settings.jwt_secret_key.get_secret_value()
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY must be configured")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.jwt_algorithm],
        )
        subject = payload.get("sub")
        return int(subject) if subject is not None else None
    except (InvalidTokenError, TypeError, ValueError):
        return None

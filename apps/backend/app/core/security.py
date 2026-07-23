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


def create_upload_analysis_token(user_id: int, item_id: int) -> str:
    """Sign a short-lived receipt used only while polling a new upload."""

    settings = get_settings()
    secret = settings.jwt_secret_key.get_secret_value()
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY must be configured")

    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "item_id": item_id,
        "purpose": "wardrobe_upload_analysis",
        "exp": expires_at,
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def validate_upload_analysis_token(
    token: str,
    user_id: int,
    item_id: int,
) -> bool:
    """Validate a polling receipt without trusting IDs supplied by the client."""

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
        return (
            payload.get("purpose") == "wardrobe_upload_analysis"
            and int(payload.get("sub")) == user_id
            and int(payload.get("item_id")) == item_id
        )
    except (InvalidTokenError, TypeError, ValueError):
        return False


def create_recommendation_save_token(
    *,
    user_id: int,
    user_request: str,
    item_ids: list[int],
    explanation: str,
    evaluation_score: float,
) -> str:
    """Sign the evaluated recommendation so the client cannot alter it before saving."""

    settings = get_settings()
    secret = settings.jwt_secret_key.get_secret_value()
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY must be configured")

    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "purpose": "recommendation_save",
        "user_request": user_request,
        "item_ids": item_ids,
        "explanation": explanation,
        "evaluation_score": evaluation_score,
        "exp": expires_at,
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def decode_recommendation_save_token(token: str, user_id: int) -> dict | None:
    """Return trusted recommendation claims for this user, or None if invalid."""

    settings = get_settings()
    secret = settings.jwt_secret_key.get_secret_value()
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY must be configured")

    try:
        payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
        if (
            payload.get("purpose") != "recommendation_save"
            or int(payload.get("sub")) != user_id
        ):
            return None
        return payload
    except (InvalidTokenError, TypeError, ValueError):
        return None

"""Shared FastAPI dependencies."""

from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.database import get_session
from app.models.user import User
from app.services.vector_store import WardrobeVectorStore, create_wardrobe_vector_store


bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_wardrobe_vector_store() -> WardrobeVectorStore | None:
    """Return the configured persistent index, or disable it if unconfigured."""

    settings = get_settings()
    if (
        not settings.openrouter_api_key.get_secret_value()
        or not settings.openrouter_embedding_model
    ):
        return None
    return create_wardrobe_vector_store(settings)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Resolve the authenticated user from a valid Bearer token."""

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized

    user = session.get(User, user_id)
    if user is None:
        raise unauthorized

    return user

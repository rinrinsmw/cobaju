"""Shared FastAPI dependencies."""

from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mcp import ClientSession
from sqlmodel import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.database import get_session
from app.models.user import User
from app.observability import bind_authenticated_user, get_observability
from app.services.mcp_client import open_user_scoped_mcp_session
from app.services.chat_guardrails import OpenRouterChatScopeClassifier
from app.services.style_critic import OpenAIAgentsStyleCritic
from app.services.stylist_agent import OpenAIAgentsStylistRunner
from app.services.vector_store import WardrobeVectorStore, create_wardrobe_vector_store


bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_chat_scope_classifier() -> OpenRouterChatScopeClassifier:
    """Return the configured classifier; tests may override this dependency."""

    return OpenRouterChatScopeClassifier(get_settings(), get_observability())


@lru_cache
def get_stylist_runner() -> OpenAIAgentsStylistRunner:
    """Return the configured Agents SDK runner; tests may override it."""

    return OpenAIAgentsStylistRunner(get_settings(), get_observability())


@lru_cache
def get_outfit_evaluator() -> OpenAIAgentsStyleCritic:
    """Return the separate Style Critic; the old dependency name is stable."""

    return OpenAIAgentsStyleCritic(get_settings(), get_observability())


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
    observability = get_observability()
    with observability.observe("auth.validate", as_type="span"):
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise unauthorized
        user_id = decode_access_token(credentials.credentials)
        if user_id is None:
            raise unauthorized

        user = session.get(User, user_id)
        if user is None:
            raise unauthorized
        bind_authenticated_user(user_id)
        observability.update_current(output={"authenticated": True})
        return user


async def get_current_user_mcp_session(
    current_user: User = Depends(get_current_user),
) -> AsyncIterator[ClientSession]:
    """Open MCP only for endpoints that explicitly request this dependency."""

    async with open_user_scoped_mcp_session(current_user) as client_session:
        yield client_session

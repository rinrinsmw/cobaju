"""Launch one wardrobe MCP stdio process for one authenticated FastAPI user."""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core.config import BACKEND_DIR, Settings, get_settings
from app.core.mcp_identity import MCP_RUNTIME_USER_ID_ENV
from app.models.user import User


class MissingAuthenticatedUserError(RuntimeError):
    """Raised when FastAPI did not supply a persisted authenticated user."""


def _single_known_domain_exception(
    error_group: BaseExceptionGroup,
) -> BaseException | None:
    """Return the sole domain-error leaf, leaving every mixed group intact."""

    # Import here to avoid the module cycle through stylist_agent -> mcp_client.
    from app.services.outfit_evaluator import RecommendationValidationError

    leaves: list[BaseException] = []

    def collect_leaves(error: BaseException) -> None:
        if isinstance(error, BaseExceptionGroup):
            for nested_error in error.exceptions:
                collect_leaves(nested_error)
            return
        leaves.append(error)

    collect_leaves(error_group)
    if len(leaves) == 1 and isinstance(leaves[0], RecommendationValidationError):
        return leaves[0]
    return None


def build_user_scoped_mcp_parameters(
    current_user: User,
    settings: Settings,
) -> StdioServerParameters:
    """Build child-process parameters from a verified FastAPI current user."""

    if current_user.id is None or current_user.id < 1:
        raise MissingAuthenticatedUserError(
            "A persisted authenticated user is required for MCP"
        )

    # The private identity exists only in this child's environment. It is not a
    # setting and must never come from an HTTP body, tool input, or shared .env.
    child_environment = {
        MCP_RUNTIME_USER_ID_ENV: str(current_user.id),
        "DATABASE_URL": settings.resolved_database_url,
        "OPENROUTER_API_KEY": settings.openrouter_api_key.get_secret_value(),
        "OPENROUTER_BASE_URL": settings.openrouter_base_url,
        "OPENROUTER_EMBEDDING_MODEL": settings.openrouter_embedding_model,
        "OPENROUTER_TIMEOUT_SECONDS": str(settings.openrouter_timeout_seconds),
        "CHROMA_DIRECTORY": str(settings.resolved_chroma_directory),
        "CHROMA_COLLECTION_NAME": settings.chroma_collection_name,
        "WARDROBE_SEARCH_LIMIT": str(settings.wardrobe_search_limit),
        "STYLING_CANDIDATES_PER_CATEGORY": str(
            settings.styling_candidates_per_category
        ),
        "LANGFUSE_ENABLED": str(settings.langfuse_enabled).lower(),
        "LANGFUSE_PUBLIC_KEY": settings.langfuse_public_key,
        "LANGFUSE_SECRET_KEY": settings.langfuse_secret_key.get_secret_value(),
        "LANGFUSE_HOST": settings.langfuse_base_url,
    }
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        env=child_environment,
        cwd=BACKEND_DIR,
    )


@asynccontextmanager
async def open_user_scoped_mcp_session(
    current_user: User,
    settings: Settings | None = None,
) -> AsyncIterator[ClientSession]:
    """Open and always clean up one user-bound MCP process and client session."""

    parameters = build_user_scoped_mcp_parameters(
        current_user,
        settings or get_settings(),
    )
    try:
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as client_session:
                await client_session.initialize()
                yield client_session
    except BaseExceptionGroup as error_group:
        domain_error = _single_known_domain_exception(error_group)
        if domain_error is None:
            raise
        # Keep the shutdown group as the explicit cause. Development traceback
        # logging therefore retains both MCP cleanup and original error frames.
        raise domain_error from error_group

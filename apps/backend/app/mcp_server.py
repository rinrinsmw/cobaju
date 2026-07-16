"""Standalone wardrobe MCP server with a trusted host-supplied user context."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.session import ServerSession
from sqlmodel import Session

from app.core.config import get_settings
from app.database import engine
from app.models.clothing_item import ClothingCategory
from app.schemas.mcp import (
    ListWardrobeCategoriesOutput,
    SaveRecommendationInput,
    SaveRecommendationOutput,
    SearchWardrobeOutput,
    ToolClothingItem,
)
from app.services.vector_store import (
    WardrobeVectorError,
    create_wardrobe_vector_store,
)
from app.services.wardrobe import ClothingItemNotFoundError
from app.services.wardrobe_tools import (
    RecommendationItemNotFoundError,
    WardrobeRetrievalUnavailableError,
    WardrobeToolService,
)


@dataclass
class WardrobeMcpContext:
    """Per-process resources initialized outside all model-controlled inputs."""

    service: WardrobeToolService


@asynccontextmanager
async def wardrobe_mcp_lifespan(
    server: FastMCP[WardrobeMcpContext],
) -> AsyncIterator[WardrobeMcpContext]:
    """Create one database session and bind it to the trusted configured user."""

    del server
    settings = get_settings()
    if settings.mcp_user_id is None:
        raise RuntimeError("MCP_USER_ID must identify the authenticated user")

    vector_store = None
    if (
        settings.openrouter_api_key.get_secret_value()
        and settings.openrouter_embedding_model
    ):
        vector_store = create_wardrobe_vector_store(settings)

    with Session(engine) as session:
        yield WardrobeMcpContext(
            service=WardrobeToolService(
                session=session,
                user_id=settings.mcp_user_id,
                vector_store=vector_store,
            )
        )


mcp = FastMCP(
    "Cobaju Wardrobe",
    instructions=(
        "Use these tools only for the authenticated user's wardrobe. "
        "Item ownership is enforced by trusted server context."
    ),
    lifespan=wardrobe_mcp_lifespan,
)


def _service(ctx: Context[ServerSession, WardrobeMcpContext]) -> WardrobeToolService:
    return ctx.request_context.lifespan_context.service


@mcp.tool(structured_output=True)
def search_wardrobe(
    query: str,
    ctx: Context[ServerSession, WardrobeMcpContext],
    category: ClothingCategory | None = None,
    limit: int | None = None,
) -> SearchWardrobeOutput:
    """Search the authenticated user's confirmed wardrobe by meaning and optional category."""

    try:
        return _service(ctx).search_wardrobe(query, category, limit)
    except ValueError as error:
        raise ToolError(str(error)) from error
    except (WardrobeRetrievalUnavailableError, WardrobeVectorError) as error:
        raise ToolError("Wardrobe search is unavailable") from error


@mcp.tool(structured_output=True)
def get_clothing_item(
    item_id: int,
    ctx: Context[ServerSession, WardrobeMcpContext],
) -> ToolClothingItem:
    """Get one confirmed clothing item only if the authenticated user owns it."""

    try:
        return _service(ctx).get_clothing_item(item_id)
    except ClothingItemNotFoundError as error:
        raise ToolError("Clothing item not found") from error


@mcp.tool(structured_output=True)
def list_wardrobe_categories(
    ctx: Context[ServerSession, WardrobeMcpContext],
) -> ListWardrobeCategoriesOutput:
    """List populated clothing categories for the authenticated user's confirmed items."""

    return _service(ctx).list_wardrobe_categories()


@mcp.tool(structured_output=True)
def save_recommendation(
    user_request: str,
    item_ids: list[int],
    explanation: str,
    ctx: Context[ServerSession, WardrobeMcpContext],
) -> SaveRecommendationOutput:
    """Accept a recommendation only when every item is confirmed and owned by the user."""

    try:
        recommendation = SaveRecommendationInput(
            user_request=user_request,
            item_ids=item_ids,
            explanation=explanation,
        )
        return _service(ctx).save_recommendation(recommendation)
    except ValueError as error:
        raise ToolError("Recommendation input is invalid") from error
    except RecommendationItemNotFoundError as error:
        raise ToolError("Recommendation contains an unavailable item") from error


def main() -> None:
    """Run the local server over stdio for one trusted authenticated user."""

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

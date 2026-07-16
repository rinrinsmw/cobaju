"""Normal Python services used independently and through thin MCP wrappers."""

from collections import Counter

from sqlmodel import Session

from app.models.clothing_item import ClothingCategory, ClothingItem, ProcessingStatus
from app.schemas.mcp import (
    ListWardrobeCategoriesOutput,
    SaveRecommendationInput,
    SaveRecommendationOutput,
    SearchWardrobeOutput,
    ToolClothingItem,
    ToolSearchMatch,
    WardrobeCategorySummary,
)
from app.services.vector_store import WardrobeVectorStore
from app.services.wardrobe import (
    ClothingItemNotFoundError,
    get_owned_clothing_item,
    list_confirmed_clothing_items,
)


class WardrobeRetrievalUnavailableError(Exception):
    """Raised when semantic search has not been configured for the server."""


class RecommendationItemNotFoundError(Exception):
    """Raised when a recommendation includes an unavailable or foreign item."""


def _tool_item(item: ClothingItem) -> ToolClothingItem:
    if item.id is None:
        raise RecommendationItemNotFoundError
    return ToolClothingItem(
        item_id=item.id,
        name=item.name,
        category=item.category,
        color=item.color,
        description=item.description,
    )


class WardrobeToolService:
    """Ownership-safe wardrobe operations for one trusted user context."""

    def __init__(
        self,
        session: Session,
        user_id: int,
        vector_store: WardrobeVectorStore | None,
    ) -> None:
        if user_id < 1:
            raise ValueError("Trusted user ID must be positive")
        self.session = session
        self.user_id = user_id
        self.vector_store = vector_store

    def search_wardrobe(
        self,
        query: str,
        category: ClothingCategory | None = None,
        limit: int | None = None,
    ) -> SearchWardrobeOutput:
        """Semantically search confirmed items owned by the trusted user."""

        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("Search query must not be blank")
        if limit is not None and not 1 <= limit <= 15:
            raise ValueError("Search limit must be between 1 and 15")
        if self.vector_store is None:
            raise WardrobeRetrievalUnavailableError

        confirmed_items = list_confirmed_clothing_items(self.session, self.user_id)
        confirmed_by_id = {
            item.id: item for item in confirmed_items if item.id is not None
        }
        self.vector_store.index_missing_items(confirmed_items)
        vector_matches = self.vector_store.search(
            query=normalized_query,
            user_id=self.user_id,
            category=category,
            limit=limit,
        )

        # Recheck each vector match against the database. This prevents a stale
        # index record from becoming evidence that an item is owned or confirmed.
        matches = []
        for match in vector_matches:
            item = confirmed_by_id.get(match.item_id)
            if item is None:
                continue
            matches.append(
                ToolSearchMatch(
                    **_tool_item(item).model_dump(),
                    distance=match.distance,
                )
            )
        return SearchWardrobeOutput(matches=matches)

    def get_clothing_item(self, item_id: int) -> ToolClothingItem:
        """Return one confirmed item owned by the trusted user."""

        if item_id < 1:
            raise ClothingItemNotFoundError
        item = get_owned_clothing_item(self.session, self.user_id, item_id)
        if item.processing_status != ProcessingStatus.COMPLETED:
            raise ClothingItemNotFoundError
        return _tool_item(item)

    def list_wardrobe_categories(self) -> ListWardrobeCategoriesOutput:
        """Count the trusted user's confirmed items by populated category."""

        items = list_confirmed_clothing_items(self.session, self.user_id)
        counts = Counter(item.category for item in items)
        categories = [
            WardrobeCategorySummary(category=category, item_count=counts[category])
            for category in ClothingCategory
            if counts[category]
        ]
        return ListWardrobeCategoriesOutput(categories=categories)

    def save_recommendation(
        self,
        recommendation: SaveRecommendationInput,
    ) -> SaveRecommendationOutput:
        """Validate a candidate; the chat service saves it only after evaluation."""

        items: list[ToolClothingItem] = []
        try:
            for item_id in recommendation.item_ids:
                items.append(self.get_clothing_item(item_id))
        except ClothingItemNotFoundError as error:
            # One indistinguishable error hides whether an ID is absent, pending,
            # failed, or belongs to another user.
            raise RecommendationItemNotFoundError from error

        return SaveRecommendationOutput(
            user_request=recommendation.user_request,
            items=items,
            explanation=recommendation.explanation,
        )

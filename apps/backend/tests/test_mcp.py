"""Phase 8 normal wardrobe service and thin MCP tool tests."""

from collections.abc import Generator
from types import SimpleNamespace

import anyio
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from sqlmodel import Session, SQLModel, create_engine

from app.mcp_server import (
    WardrobeMcpContext,
    get_clothing_item,
    list_wardrobe_categories,
    mcp,
    save_recommendation,
    search_wardrobe,
)
from app.models.clothing_item import (
    ClothingCategory,
    ClothingItem,
    ProcessingStatus,
)
from app.schemas.mcp import SaveRecommendationInput
from app.services.vector_store import WardrobeSearchResult
from app.services.wardrobe import ClothingItemNotFoundError
from app.services.wardrobe_tools import (
    RecommendationItemNotFoundError,
    WardrobeToolService,
)


class FakeVectorStore:
    """Small retrieval double that can also return deliberately stale records."""

    def __init__(self, matches: list[WardrobeSearchResult]) -> None:
        self.matches = matches
        self.indexed_item_ids: list[int] = []
        self.search_user_id: int | None = None

    def index_missing_items(self, items: list[ClothingItem]) -> None:
        self.indexed_item_ids = [item.id for item in items if item.id is not None]

    def search(
        self,
        *,
        query: str,
        user_id: int,
        category: ClothingCategory | None = None,
        limit: int | None = None,
    ) -> list[WardrobeSearchResult]:
        del query, category
        self.search_user_id = user_id
        return self.matches[:limit]


@pytest.fixture
def wardrobe_session(tmp_path: object) -> Generator[Session, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path}/mcp.db")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def add_item(
    session: Session,
    *,
    user_id: int,
    name: str,
    category: ClothingCategory,
    status: ProcessingStatus = ProcessingStatus.COMPLETED,
) -> ClothingItem:
    item = ClothingItem(
        user_id=user_id,
        name=name,
        category=category,
        color="blue",
        description=f"Description for {name}.",
        processing_status=status,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def vector_match(item: ClothingItem, distance: float) -> WardrobeSearchResult:
    assert item.id is not None
    return WardrobeSearchResult(
        item_id=item.id,
        name=item.name,
        category=item.category,
        color=item.color,
        description=item.description,
        distance=distance,
    )


def fake_context(service: WardrobeToolService) -> object:
    return SimpleNamespace(
        request_context=SimpleNamespace(
            lifespan_context=WardrobeMcpContext(service=service)
        )
    )


def test_normal_search_service_rechecks_confirmed_ownership(
    wardrobe_session: Session,
) -> None:
    own_item = add_item(
        wardrobe_session,
        user_id=1,
        name="Office Shirt",
        category=ClothingCategory.TOP,
    )
    own_pending = add_item(
        wardrobe_session,
        user_id=1,
        name="Unconfirmed Shirt",
        category=ClothingCategory.TOP,
        status=ProcessingStatus.PENDING,
    )
    foreign_item = add_item(
        wardrobe_session,
        user_id=2,
        name="Private Shirt",
        category=ClothingCategory.TOP,
    )
    store = FakeVectorStore(
        [
            vector_match(foreign_item, 0.01),
            vector_match(own_pending, 0.02),
            vector_match(own_item, 0.03),
        ]
    )
    service = WardrobeToolService(wardrobe_session, user_id=1, vector_store=store)  # type: ignore[arg-type]

    result = service.search_wardrobe("blue office shirt", limit=5)

    assert [match.item_id for match in result.matches] == [own_item.id]
    assert store.indexed_item_ids == [own_item.id]
    assert store.search_user_id == 1


def test_normal_item_and_category_services_hide_other_users_and_drafts(
    wardrobe_session: Session,
) -> None:
    own_top = add_item(
        wardrobe_session,
        user_id=1,
        name="Top",
        category=ClothingCategory.TOP,
    )
    add_item(
        wardrobe_session,
        user_id=1,
        name="Shoes",
        category=ClothingCategory.SHOES,
    )
    own_pending = add_item(
        wardrobe_session,
        user_id=1,
        name="Draft Bag",
        category=ClothingCategory.BAG,
        status=ProcessingStatus.PENDING,
    )
    foreign = add_item(
        wardrobe_session,
        user_id=2,
        name="Private Dress",
        category=ClothingCategory.DRESS,
    )
    service = WardrobeToolService(wardrobe_session, user_id=1, vector_store=None)

    assert service.get_clothing_item(own_top.id or 0).name == "Top"
    assert [summary.model_dump(mode="json") for summary in service.list_wardrobe_categories().categories] == [
        {"category": "top", "item_count": 1},
        {"category": "shoes", "item_count": 1},
    ]
    with pytest.raises(ClothingItemNotFoundError):
        service.get_clothing_item(own_pending.id or 0)
    with pytest.raises(ClothingItemNotFoundError):
        service.get_clothing_item(foreign.id or 0)


def test_save_recommendation_validates_every_owned_item_without_persisting_history(
    wardrobe_session: Session,
) -> None:
    own_item = add_item(
        wardrobe_session,
        user_id=1,
        name="Blue Shirt",
        category=ClothingCategory.TOP,
    )
    foreign_item = add_item(
        wardrobe_session,
        user_id=2,
        name="Private Shoes",
        category=ClothingCategory.SHOES,
    )
    service = WardrobeToolService(wardrobe_session, user_id=1, vector_store=None)
    accepted = service.save_recommendation(
        SaveRecommendationInput(
            user_request="  office outfit  ",
            item_ids=[own_item.id or 0],
            explanation="  A simple office option.  ",
        )
    )

    assert accepted.status == "accepted"
    assert accepted.user_request == "office outfit"
    assert [item.item_id for item in accepted.items] == [own_item.id]
    assert accepted.persisted is False
    with pytest.raises(RecommendationItemNotFoundError):
        service.save_recommendation(
            SaveRecommendationInput(
                user_request="office outfit",
                item_ids=[foreign_item.id or 0],
                explanation="Must be rejected.",
            )
        )
    with pytest.raises(ValueError, match="unique"):
        SaveRecommendationInput(
            user_request="office outfit",
            item_ids=[own_item.id or 0, own_item.id or 0],
            explanation="Duplicate item IDs are invalid.",
        )


def test_mcp_exposes_four_structured_tools_without_user_id_input() -> None:
    tools = anyio.run(mcp.list_tools)

    assert [tool.name for tool in tools] == [
        "search_wardrobe",
        "get_clothing_item",
        "list_wardrobe_categories",
        "save_recommendation",
    ]
    assert all(tool.description for tool in tools)
    assert all(tool.outputSchema for tool in tools)
    assert all("user_id" not in tool.inputSchema.get("properties", {}) for tool in tools)


def test_mcp_wrappers_delegate_and_keep_cross_user_errors_safe(
    wardrobe_session: Session,
) -> None:
    own_item = add_item(
        wardrobe_session,
        user_id=1,
        name="Office Shirt",
        category=ClothingCategory.TOP,
    )
    foreign_item = add_item(
        wardrobe_session,
        user_id=2,
        name="Private Shirt",
        category=ClothingCategory.TOP,
    )
    store = FakeVectorStore([vector_match(own_item, 0.1)])
    service = WardrobeToolService(wardrobe_session, user_id=1, vector_store=store)  # type: ignore[arg-type]
    context = fake_context(service)

    assert search_wardrobe("office", context).matches[0].item_id == own_item.id  # type: ignore[arg-type]
    assert get_clothing_item(own_item.id or 0, context).name == "Office Shirt"  # type: ignore[arg-type]
    assert list_wardrobe_categories(context).categories[0].category == ClothingCategory.TOP  # type: ignore[arg-type]
    assert save_recommendation(
        "office outfit",
        [own_item.id or 0],
        "Wear the owned shirt.",
        context,  # type: ignore[arg-type]
    ).status == "accepted"

    with pytest.raises(ToolError, match="Clothing item not found"):
        get_clothing_item(foreign_item.id or 0, context)  # type: ignore[arg-type]
    with pytest.raises(ToolError, match="unavailable item"):
        save_recommendation(
            "office outfit",
            [foreign_item.id or 0],
            "Must be rejected.",
            context,  # type: ignore[arg-type]
        )

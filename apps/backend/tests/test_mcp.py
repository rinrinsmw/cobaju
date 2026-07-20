"""Phase 8 normal wardrobe service and thin MCP tool tests."""

import asyncio
import traceback as traceback_module
from collections.abc import Generator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import anyio
import pytest
from fastapi.dependencies.utils import get_dependant
from fastapi.routing import APIRoute
from mcp.server.fastmcp.exceptions import ToolError
from sqlmodel import Session, SQLModel, create_engine

from app import mcp_server as mcp_server_module
from app.services import mcp_client as mcp_client_module
from app.core.config import Settings
from app.core.mcp_identity import (
    MCP_RUNTIME_USER_ID_ENV,
    McpRuntimeIdentityError,
)
from app.dependencies import get_current_user, get_current_user_mcp_session
from app.main import app
from app.mcp_server import (
    WardrobeMcpContext,
    get_clothing_item,
    get_styling_candidates,
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
from app.models.user import User
from app.models.recommendation import Recommendation
from app.schemas.mcp import GetStylingCandidatesInput, SaveRecommendationInput
from app.services.mcp_client import (
    build_user_scoped_mcp_parameters,
    open_user_scoped_mcp_session,
)
from app.services.outfit_evaluator import RecommendationValidationError
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


def add_user(session: Session, email: str) -> User:
    user = User(email=email, hashed_password="test-only-hash")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


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


def test_save_recommendation_validates_candidate_without_persisting_early(
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
            evaluation_score=9,
        )
    )

    assert accepted.status == "accepted"
    assert accepted.user_request == "office outfit"
    assert [item.item_id for item in accepted.items] == [own_item.id]
    assert accepted.persisted is True
    assert accepted.recommendation_id > 0
    saved = wardrobe_session.get(Recommendation, accepted.recommendation_id)
    assert saved is not None
    assert saved.selected_item_ids == [own_item.id]
    with pytest.raises(RecommendationItemNotFoundError):
        service.save_recommendation(
            SaveRecommendationInput(
                user_request="office outfit",
                item_ids=[own_item.id or 0, foreign_item.id or 0],
                explanation="Must be rejected.",
                evaluation_score=1,
            )
        )
    with pytest.raises(ValueError, match="unique"):
        SaveRecommendationInput(
            user_request="office outfit",
            item_ids=[own_item.id or 0, own_item.id or 0],
            explanation="Duplicate item IDs are invalid.",
            evaluation_score=1,
        )


@pytest.mark.parametrize("raw_user_id", [None, "not-a-number", "0", "-1"])
def test_mcp_startup_rejects_missing_or_invalid_runtime_identity(
    wardrobe_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    raw_user_id: str | None,
) -> None:
    monkeypatch.setattr(mcp_server_module, "engine", wardrobe_session.get_bind())
    if raw_user_id is None:
        monkeypatch.delenv(MCP_RUNTIME_USER_ID_ENV, raising=False)
    else:
        monkeypatch.setenv(MCP_RUNTIME_USER_ID_ENV, raw_user_id)

    async def start_server_lifespan() -> None:
        async with mcp_server_module.wardrobe_mcp_lifespan(mcp):
            pass

    with pytest.raises(McpRuntimeIdentityError):
        anyio.run(start_server_lifespan)


def test_mcp_startup_rejects_nonexistent_sqlite_user(
    wardrobe_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server_module, "engine", wardrobe_session.get_bind())
    monkeypatch.setenv(MCP_RUNTIME_USER_ID_ENV, "999")

    async def start_server_lifespan() -> None:
        async with mcp_server_module.wardrobe_mcp_lifespan(mcp):
            pass

    with pytest.raises(RuntimeError, match="does not exist"):
        anyio.run(start_server_lifespan)


def test_mcp_dependency_is_opt_in_and_uses_verified_current_user(
    wardrobe_session: Session,
) -> None:
    current_user = add_user(wardrobe_session, "dependency@example.com")
    settings = Settings(
        database_url=str(wardrobe_session.get_bind().url),
        openrouter_api_key="",
        openrouter_embedding_model="",
    )
    parameters = build_user_scoped_mcp_parameters(current_user, settings)
    dependency = get_dependant(path="/mcp-only", call=get_current_user_mcp_session)

    assert dependency.dependencies[0].call is get_current_user
    assert parameters.env is not None
    assert parameters.env[MCP_RUNTIME_USER_ID_ENV] == str(current_user.id)
    assert all(
        dependency.call is not get_current_user_mcp_session
        for route in app.routes
        if isinstance(route, APIRoute)
        for dependency in route.dependant.dependencies
    )


def test_two_user_scoped_stdio_sessions_are_isolated(
    wardrobe_session: Session,
    tmp_path: object,
) -> None:
    first_user = add_user(wardrobe_session, "first@example.com")
    second_user = add_user(wardrobe_session, "second@example.com")
    assert first_user.id is not None
    assert second_user.id is not None
    first_item = add_item(
        wardrobe_session,
        user_id=first_user.id,
        name="First User Shirt",
        category=ClothingCategory.TOP,
    )
    second_item = add_item(
        wardrobe_session,
        user_id=second_user.id,
        name="Second User Shoes",
        category=ClothingCategory.SHOES,
    )
    settings = Settings(
        database_url=str(wardrobe_session.get_bind().url),
        openrouter_api_key="",
        openrouter_embedding_model="",
        langfuse_enabled=False,
        chroma_directory=f"{tmp_path}/mcp-chroma",
    )

    async def exercise_sessions() -> None:
        async with open_user_scoped_mcp_session(first_user, settings) as first_session:
            async with open_user_scoped_mcp_session(
                second_user, settings
            ) as second_session:
                first_categories = await first_session.call_tool(
                    "list_wardrobe_categories", {}
                )
                second_categories = await second_session.call_tool(
                    "list_wardrobe_categories", {}
                )
                first_foreign_item = await first_session.call_tool(
                    "get_clothing_item", {"item_id": second_item.id}
                )
                second_foreign_item = await second_session.call_tool(
                    "get_clothing_item", {"item_id": first_item.id}
                )

                assert first_categories.structuredContent == {
                    "categories": [{"category": "top", "item_count": 1}]
                }
                assert second_categories.structuredContent == {
                    "categories": [{"category": "shoes", "item_count": 1}]
                }
                assert first_foreign_item.isError is True
                assert second_foreign_item.isError is True

        class ExpectedCallerError(Exception):
            pass

        try:
            async with open_user_scoped_mcp_session(first_user, settings):
                raise ExpectedCallerError
        except* ExpectedCallerError:
            pass

        # Opening another process after the exception proves the previous
        # ClientSession, stdio streams, and child process finished cleanup.
        async with open_user_scoped_mcp_session(first_user, settings) as session:
            categories = await session.call_tool("list_wardrobe_categories", {})
            assert categories.isError is False

    anyio.run(exercise_sessions)


def test_mcp_boundary_unwraps_one_domain_error_after_session_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_events: list[str] = []

    @asynccontextmanager
    async def fake_stdio_client(parameters: object):
        del parameters
        try:
            yield object(), object()
        finally:
            cleanup_events.append("stdio")

    class GroupingClientSession:
        async def __aenter__(self) -> "GroupingClientSession":
            return self

        async def __aexit__(
            self,
            error_type: type[BaseException] | None,
            error: BaseException | None,
            traceback: object,
        ) -> None:
            del error_type, traceback
            cleanup_events.append("session")
            if error is not None:
                raise ExceptionGroup("MCP session shutdown", [error])

        async def initialize(self) -> None:
            pass

    monkeypatch.setattr(mcp_client_module, "stdio_client", fake_stdio_client)
    monkeypatch.setattr(
        mcp_client_module,
        "ClientSession",
        lambda read_stream, write_stream: GroupingClientSession(),
    )

    async def exercise_boundary() -> None:
        error = RecommendationValidationError("invalid after repair")
        with pytest.raises(RecommendationValidationError) as caught:
            async with open_user_scoped_mcp_session(
                User(id=1, email="owner@example.com", hashed_password="hash"),
                Settings(openrouter_api_key=""),
            ):
                raise error
        assert caught.value is error
        assert isinstance(caught.value.__cause__, ExceptionGroup)
        formatted = "".join(
            traceback_module.format_exception(
                type(caught.value), caught.value, caught.value.__traceback__
            )
        )
        assert "MCP session shutdown" in formatted
        assert "RecommendationValidationError: invalid after repair" in formatted

    anyio.run(exercise_boundary)

    assert cleanup_events == ["session", "stdio"]


@pytest.mark.parametrize(
    "original_group",
    [
        BaseExceptionGroup("cancelled", [asyncio.CancelledError()]),
        ExceptionGroup(
            "multiple",
            [
                ExceptionGroup(
                    "domain",
                    [RecommendationValidationError("invalid after repair")],
                ),
                ValueError("cleanup also failed"),
            ],
        ),
    ],
    ids=["cancellation", "multiple-nested-exceptions"],
)
def test_mcp_boundary_preserves_non_unwrappable_exception_groups(
    monkeypatch: pytest.MonkeyPatch,
    original_group: BaseExceptionGroup,
) -> None:
    @asynccontextmanager
    async def fake_stdio_client(parameters: object):
        del parameters
        yield object(), object()

    class PassthroughClientSession:
        async def __aenter__(self) -> "PassthroughClientSession":
            return self

        async def __aexit__(
            self,
            error_type: type[BaseException] | None,
            error: BaseException | None,
            traceback: object,
        ) -> bool:
            del error_type, error, traceback
            return False

        async def initialize(self) -> None:
            pass

    monkeypatch.setattr(mcp_client_module, "stdio_client", fake_stdio_client)
    monkeypatch.setattr(
        mcp_client_module,
        "ClientSession",
        lambda read_stream, write_stream: PassthroughClientSession(),
    )

    async def exercise_boundary() -> None:
        try:
            async with open_user_scoped_mcp_session(
                User(id=1, email="owner@example.com", hashed_password="hash"),
                Settings(openrouter_api_key=""),
            ):
                raise original_group
        except BaseExceptionGroup as caught:
            assert caught is original_group
        else:
            pytest.fail("The original exception group was swallowed")

    anyio.run(exercise_boundary)


def test_mcp_exposes_high_level_candidate_tool_without_user_id_input() -> None:
    tools = anyio.run(mcp.list_tools)

    assert [tool.name for tool in tools] == [
        "get_styling_candidates",
        "search_wardrobe",
        "get_clothing_item",
        "list_wardrobe_categories",
        "save_recommendation",
    ]
    assert all(tool.description for tool in tools)
    assert all(tool.outputSchema for tool in tools)
    assert all("user_id" not in tool.inputSchema.get("properties", {}) for tool in tools)


def test_styling_candidates_are_grouped_capped_and_report_missing_categories(
    wardrobe_session: Session,
) -> None:
    first_top = add_item(
        wardrobe_session,
        user_id=1,
        name="First top",
        category=ClothingCategory.TOP,
    )
    add_item(
        wardrobe_session,
        user_id=1,
        name="Second top",
        category=ClothingCategory.TOP,
    )
    add_item(
        wardrobe_session,
        user_id=1,
        name="Third top",
        category=ClothingCategory.TOP,
    )
    service = WardrobeToolService(wardrobe_session, user_id=1, vector_store=None)

    result = service.get_styling_candidates(
        GetStylingCandidatesInput(
            user_request="Style item 1 for work",
            required_categories=[ClothingCategory.TOP, ClothingCategory.SHOES],
            anchor_item_id=first_top.id,
            limit_per_category=2,
        )
    )

    assert result.anchor_item is not None
    assert result.anchor_item.item_id == first_top.id
    assert len(result.candidates_by_category[0].items) == 2
    assert result.missing_required_categories == [ClothingCategory.SHOES]
    assert result.owned_item_ids == sorted(result.owned_item_ids)


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
    candidates = get_styling_candidates(
        "office",
        [ClothingCategory.TOP, ClothingCategory.SHOES],
        context,  # type: ignore[arg-type]
        limit_per_category=1,
    )
    assert candidates.candidates_by_category[0].items[0].item_id == own_item.id
    assert candidates.missing_required_categories == [ClothingCategory.SHOES]
    assert save_recommendation(
        "office outfit",
        [own_item.id or 0],
        "Wear the owned shirt.",
        9,
        context,  # type: ignore[arg-type]
    ).status == "accepted"

    with pytest.raises(ToolError, match="Clothing item not found"):
        get_clothing_item(foreign_item.id or 0, context)  # type: ignore[arg-type]
    with pytest.raises(ToolError, match="unavailable item"):
        save_recommendation(
            "office outfit",
            [foreign_item.id or 0],
            "Must be rejected.",
            1,
            context,  # type: ignore[arg-type]
        )

"""Phase 11 recommendation persistence, history, and ownership tests."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.dependencies import get_current_user
from app.main import app
from app.models.clothing_item import ClothingCategory, ClothingItem
from app.models.recommendation import Recommendation
from app.models.user import User
from app.schemas.chat import RecommendedOwnedItem, StylistResponse
from app.services.recommendations import (
    InvalidRecommendationItemsError,
    list_recommendation_history,
    save_completed_recommendation,
)


@pytest.fixture
def history_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id=1, email="owner@example.com", hashed_password="hash"))
        session.add(User(id=2, email="other@example.com", hashed_password="hash"))
        session.add(
            ClothingItem(
                id=10,
                user_id=1,
                name="Blue Oxford",
                category=ClothingCategory.TOP,
                color="blue",
                original_image_path="uploads/blue-oxford.jpg",
            )
        )
        session.add(
            ClothingItem(
                id=20,
                user_id=2,
                name="Private trousers",
                category=ClothingCategory.BOTTOM,
                color="black",
            )
        )
        session.commit()
        yield session


def completed_response(item_id: int) -> StylistResponse:
    return StylistResponse(
        status="recommendation",
        message="A polished blue layer for your presentation.",
        required_categories=[],
        owned_items=[
            RecommendedOwnedItem(
                item_id=item_id,
                category=ClothingCategory.TOP,
                reason="It suits the occasion.",
            )
        ],
        missing_categories=[],
    )


def test_completed_recommendation_is_saved_with_score_and_timestamp(
    history_session: Session,
) -> None:
    saved = save_completed_recommendation(
        history_session,
        user_id=1,
        original_request="Office presentation",
        response=completed_response(10),
        evaluation_score=9.4,
    )

    history = list_recommendation_history(history_session, 1)

    assert saved.id is not None
    assert len(history) == 1
    assert history[0].original_request == "Office presentation"
    assert history[0].selected_item_ids == [10]
    assert history[0].evaluation_score == 9.4
    assert history[0].created_at is not None
    assert history[0].items[0].name == "Blue Oxford"
    assert history[0].items[0].available is True


def test_save_rechecks_item_ownership(history_session: Session) -> None:
    with pytest.raises(InvalidRecommendationItemsError):
        save_completed_recommendation(
            history_session,
            user_id=1,
            original_request="Use another user's item",
            response=completed_response(20),
            evaluation_score=8,
        )


def test_history_is_user_scoped_and_deleted_items_remain_safe(
    history_session: Session,
) -> None:
    save_completed_recommendation(
        history_session,
        user_id=1,
        original_request="Coffee meeting",
        response=completed_response(10),
        evaluation_score=8.7,
    )
    item = history_session.get(ClothingItem, 10)
    assert item is not None
    history_session.delete(item)
    history_session.commit()

    owner_history = list_recommendation_history(history_session, 1)

    assert list_recommendation_history(history_session, 2) == []
    assert owner_history[0].selected_item_ids == [10]
    assert owner_history[0].items[0].available is False
    assert owner_history[0].items[0].name is None


def test_history_api_returns_only_authenticated_users_records(
    history_session: Session,
) -> None:
    save_completed_recommendation(
        history_session,
        user_id=1,
        original_request="Owner's look",
        response=completed_response(10),
        evaluation_score=9,
    )

    def session_override() -> Generator[Session, None, None]:
        yield history_session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: User(
        id=2, email="other@example.com", hashed_password="hash"
    )
    try:
        with TestClient(app) as client:
            response = client.get("/recommendations")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []


def test_history_api_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/recommendations")

    assert response.status_code == 401


def test_owner_can_delete_lookbook_entry_without_deleting_wardrobe_item(
    history_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = save_completed_recommendation(
        history_session,
        user_id=1,
        original_request="Owner's removable look",
        response=completed_response(10),
        evaluation_score=9,
    )
    assert saved.id is not None

    def session_override() -> Generator[Session, None, None]:
        yield history_session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, email="owner@example.com", hashed_password="hash"
    )
    delete_events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "app.routers.recommendations.structured_log",
        lambda event, **fields: delete_events.append((event, fields)),
    )
    try:
        with TestClient(app) as client:
            response = client.delete(f"/recommendations/{saved.id}")
            history_response = client.get("/recommendations")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert history_response.json() == []
    assert history_session.get(Recommendation, saved.id) is None
    wardrobe_item = history_session.get(ClothingItem, 10)
    assert wardrobe_item is not None
    assert wardrobe_item.original_image_path == "uploads/blue-oxford.jpg"
    event, fields = delete_events[0]
    assert event == "recommendation_deleted"
    assert fields["recommendation_id"] == saved.id
    assert fields["user_id"]
    assert fields["delete_success"] is True
    assert isinstance(fields["delete_latency_ms"], float)


def test_another_user_cannot_delete_recommendation(
    history_session: Session,
) -> None:
    saved = save_completed_recommendation(
        history_session,
        user_id=1,
        original_request="Owner's private look",
        response=completed_response(10),
        evaluation_score=9,
    )
    assert saved.id is not None

    def session_override() -> Generator[Session, None, None]:
        yield history_session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: User(
        id=2, email="other@example.com", hashed_password="hash"
    )
    try:
        with TestClient(app) as client:
            response = client.delete(f"/recommendations/{saved.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert history_session.get(Recommendation, saved.id) is not None
    assert history_session.get(ClothingItem, 10) is not None

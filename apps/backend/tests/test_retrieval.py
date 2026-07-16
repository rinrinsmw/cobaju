"""Phase 7 Chroma indexing, retrieval, lifecycle, and API tests."""

from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import Settings, get_settings
from app.database import get_session
from app.dependencies import get_wardrobe_vector_store
from app.main import app
from app.models.clothing_item import (
    ClothingCategory,
    ClothingItem,
    ProcessingStatus,
)
from app.services.embeddings import (
    EmbeddingError,
    OpenRouterEmbeddingProvider,
)
from app.services.vector_store import (
    RetrievalTracer,
    WardrobeVectorError,
    WardrobeVectorStore,
    build_clothing_description,
)
from app.services.wardrobe import confirm_analyzed_item


class KeywordEmbeddingProvider:
    """Small deterministic semantic model used instead of a paid API."""

    KEYWORD_GROUPS = (
        ("blue", "navy"),
        ("office", "formal", "smart", "work"),
        ("shoe", "shoes", "sneaker", "sneakers"),
        ("red", "crimson"),
        ("top", "shirt", "blouse"),
    )

    def embed_text(self, text: str) -> list[float]:
        normalized = text.lower()
        vector = [
            float(sum(normalized.count(keyword) for keyword in group))
            for group in self.KEYWORD_GROUPS
        ]
        return vector if any(vector) else [0.01] * len(self.KEYWORD_GROUPS)


def make_store(tmp_path: Path) -> WardrobeVectorStore:
    settings = Settings(
        chroma_directory=str(tmp_path / "chroma"),
        chroma_collection_name="test_wardrobe",
        wardrobe_search_limit=5,
        langfuse_enabled=False,
    )
    return WardrobeVectorStore(settings, KeywordEmbeddingProvider())


def make_item(
    *,
    item_id: int,
    user_id: int,
    name: str,
    category: ClothingCategory,
    color: str,
    description: str | None,
) -> ClothingItem:
    return ClothingItem(
        id=item_id,
        user_id=user_id,
        name=name,
        category=category,
        color=color,
        description=description,
        processing_status=ProcessingStatus.COMPLETED,
    )


def test_description_builder_uses_only_validated_item_metadata() -> None:
    item = make_item(
        item_id=1,
        user_id=7,
        name="Oxford Shirt",
        category=ClothingCategory.TOP,
        color="light blue",
        description="Suitable for office and smart-casual outfits.",
    )

    assert build_clothing_description(item) == (
        "light blue top named Oxford Shirt. "
        "Suitable for office and smart-casual outfits."
    )


def test_search_ranks_relevant_items_and_filters_user_and_category(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    own_shirt = make_item(
        item_id=1,
        user_id=10,
        name="Oxford Shirt",
        category=ClothingCategory.TOP,
        color="light blue",
        description="Formal office and smart-casual shirt.",
    )
    own_shoes = make_item(
        item_id=2,
        user_id=10,
        name="Running Sneakers",
        category=ClothingCategory.SHOES,
        color="red",
        description="Casual athletic shoes.",
    )
    other_user_shirt = make_item(
        item_id=3,
        user_id=20,
        name="Work Blouse",
        category=ClothingCategory.TOP,
        color="blue",
        description="Formal office top.",
    )
    for item in (own_shoes, other_user_shirt, own_shirt):
        store.upsert_item(item)

    results = store.search(query="blue office shirt", user_id=10)
    shoe_results = store.search(
        query="what can I wear on my feet? sneakers",
        user_id=10,
        category=ClothingCategory.SHOES,
    )

    assert [result.item_id for result in results] == [1, 2]
    assert all(result.item_id != 3 for result in results)
    assert [result.item_id for result in shoe_results] == [2]


def test_upsert_replaces_metadata_and_delete_removes_record(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    item = make_item(
        item_id=1,
        user_id=10,
        name="Plain Top",
        category=ClothingCategory.TOP,
        color="white",
        description="Casual shirt.",
    )
    store.upsert_item(item)
    item.name = "Office Top"
    item.color = "blue"
    item.description = "Formal work shirt."
    store.upsert_item(item)

    results = store.search(query="blue formal office", user_id=10)
    assert len(results) == 1
    assert results[0].name == "Office Top"
    assert results[0].color == "blue"

    store.delete_item(1)
    assert store.search(query="blue formal office", user_id=10) == []


@pytest.fixture
def retrieval_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, Session, WardrobeVectorStore], None, None]:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-secret-with-enough-entropy")
    get_settings.cache_clear()
    engine = create_engine(
        f"sqlite:///{tmp_path / 'retrieval.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    store = make_store(tmp_path)

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_wardrobe_vector_store] = lambda: store
    with Session(engine) as inspection_session:
        with TestClient(app) as test_client:
            yield test_client, inspection_session, store

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    password = "correct-horse-battery-staple"
    assert client.post(
        "/auth/register", json={"email": email, "password": password}
    ).status_code == 201
    login = client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def item_payload(
    name: str,
    *,
    category: str = "top",
    color: str = "blue",
    description: str = "Formal office shirt.",
) -> dict[str, str]:
    return {
        "name": name,
        "category": category,
        "color": color,
        "description": description,
    }


def test_api_indexes_updates_deletes_and_hides_other_users_items(
    retrieval_client: tuple[TestClient, Session, WardrobeVectorStore],
) -> None:
    client, _, _ = retrieval_client
    owner = auth_headers(client, "owner@example.com")
    other = auth_headers(client, "other@example.com")
    own_item = client.post(
        "/wardrobe/items",
        headers=owner,
        json=item_payload("Oxford Shirt"),
    )
    other_item = client.post(
        "/wardrobe/items",
        headers=other,
        json=item_payload("Private Work Blouse"),
    )
    assert own_item.status_code == 201
    assert other_item.status_code == 201

    search = client.get(
        "/wardrobe/items/search",
        headers=owner,
        params={"q": "formal office", "category": "top"},
    )
    assert search.status_code == 200
    assert [result["item_id"] for result in search.json()] == [own_item.json()["id"]]

    updated = client.patch(
        f"/wardrobe/items/{own_item.json()['id']}",
        headers=owner,
        json={"name": "Red Sneakers", "category": "shoes", "color": "red", "description": "Casual athletic shoes."},
    )
    category_search = client.get(
        "/wardrobe/items/search",
        headers=owner,
        params={"q": "red sneakers", "category": "shoes"},
    )
    assert updated.status_code == 200
    assert category_search.json()[0]["name"] == "Red Sneakers"

    assert client.delete(
        f"/wardrobe/items/{own_item.json()['id']}", headers=owner
    ).status_code == 204
    assert client.get(
        "/wardrobe/items/search",
        headers=owner,
        params={"q": "red sneakers"},
    ).json() == []


def test_failed_embedding_does_not_commit_confirmed_item(
    retrieval_client: tuple[TestClient, Session, WardrobeVectorStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, store = retrieval_client
    headers = auth_headers(client, "embedding-failure@example.com")

    def fail_upsert(item: ClothingItem) -> None:
        raise WardrobeVectorError("provider unavailable")

    monkeypatch.setattr(store, "upsert_item", fail_upsert)
    create_response = client.post(
        "/wardrobe/items",
        headers=headers,
        json=item_payload("Unindexed Shirt"),
    )

    assert create_response.status_code == 503
    assert client.get("/wardrobe/items", headers=headers).json() == []


def test_confirmed_analysis_is_indexed_but_pending_draft_is_not(
    retrieval_client: tuple[TestClient, Session, WardrobeVectorStore],
) -> None:
    client, session, store = retrieval_client
    headers = auth_headers(client, "confirm@example.com")
    draft = ClothingItem(
        user_id=1,
        name="Blue Work Shirt",
        category=ClothingCategory.TOP,
        color="blue",
        description="Formal office top.",
        original_image_path="1/item.jpg",
        analysis_completed=True,
        processing_status=ProcessingStatus.PENDING,
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    assert store.search(query="office shirt", user_id=1) == []

    confirmed = confirm_analyzed_item(session, draft, store)
    response = client.get(
        "/wardrobe/items/search",
        headers=headers,
        params={"q": "office shirt"},
    )

    assert confirmed.processing_status == ProcessingStatus.COMPLETED
    assert response.status_code == 200
    assert response.json()[0]["item_id"] == draft.id


def test_first_search_backfills_confirmed_items_created_before_phase_seven(
    retrieval_client: tuple[TestClient, Session, WardrobeVectorStore],
) -> None:
    client, session, store = retrieval_client
    headers = auth_headers(client, "backfill@example.com")
    old_item = ClothingItem(
        user_id=1,
        name="Legacy Oxford Shirt",
        category=ClothingCategory.TOP,
        color="blue",
        description="Formal office shirt.",
        processing_status=ProcessingStatus.COMPLETED,
    )
    session.add(old_item)
    session.commit()
    session.refresh(old_item)
    assert store.search(query="office shirt", user_id=1) == []

    response = client.get(
        "/wardrobe/items/search",
        headers=headers,
        params={"q": "office shirt"},
    )

    assert response.status_code == 200
    assert response.json()[0]["item_id"] == old_item.id


def test_search_requires_auth_and_valid_query_parameters(
    retrieval_client: tuple[TestClient, Session, WardrobeVectorStore],
) -> None:
    client, _, _ = retrieval_client
    headers = auth_headers(client, "validation@example.com")

    assert client.get("/wardrobe/items/search", params={"q": "shirt"}).status_code == 401
    assert client.get(
        "/wardrobe/items/search", headers=headers, params={"q": "   "}
    ).status_code == 422
    assert client.get(
        "/wardrobe/items/search",
        headers=headers,
        params={"q": "shirt", "limit": 16},
    ).status_code == 422
    assert client.get(
        "/wardrobe/items/search",
        headers=headers,
        params={"q": "shirt", "category": "invalid"},
    ).status_code == 422


def test_openrouter_embedding_provider_uses_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        openrouter_api_key="test-key",
        openrouter_embedding_model="provider/embedding-model",
    )
    provider = OpenRouterEmbeddingProvider(settings)
    captured: dict[str, Any] = {}

    def fake_post(*args: Any, **kwargs: Any) -> httpx.Response:
        captured.update(kwargs)
        request = httpx.Request("POST", str(args[0]))
        return httpx.Response(
            200,
            request=request,
            json={"data": [{"embedding": [0.1, 0.2, 0.3]}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    assert provider.embed_text("blue office shirt") == [0.1, 0.2, 0.3]
    assert captured["json"] == {
        "model": "provider/embedding-model",
        "input": "blue office shirt",
        "encoding_format": "float",
    }


def test_openrouter_embedding_provider_rejects_invalid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenRouterEmbeddingProvider(
        Settings(openrouter_api_key="test-key", openrouter_embedding_model="model")
    )

    def fake_post(*args: Any, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", str(args[0]))
        return httpx.Response(200, request=request, json={"data": []})

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(EmbeddingError):
        provider.embed_text("shirt")


def test_retrieval_tracer_uses_configured_langfuse_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeLangfuse:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs

        def start_as_current_observation(self, **kwargs: Any) -> Any:
            captured["observation"] = kwargs
            from contextlib import nullcontext

            return nullcontext()

    monkeypatch.setattr("langfuse.Langfuse", FakeLangfuse)
    tracer = RetrievalTracer(
        Settings(
            langfuse_enabled=True,
            langfuse_public_key="public-key",
            langfuse_secret_key="secret-key",
            langfuse_base_url="https://langfuse.example.com",
        )
    )
    with tracer.observation(user_id=5, category=ClothingCategory.TOP):
        pass

    assert captured["client"]["base_url"] == "https://langfuse.example.com"
    assert captured["observation"]["name"] == "wardrobe_retrieval"
    assert captured["observation"]["input"] == {"user_id": 5, "category": "top"}

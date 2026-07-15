"""API, ownership, and limit tests for Phase 3 wardrobe CRUD."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings
from app.database import get_session
from app.main import app
from app.models.clothing_item import (
    ClothingCategory,
    ClothingItem,
    ProcessingStatus,
)


@pytest.fixture
def client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, Session], None, None]:
    """Give each wardrobe test an isolated database and signing secret."""

    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-secret-with-enough-entropy")
    get_settings.cache_clear()

    engine = create_engine(
        f"sqlite:///{tmp_path / 'wardrobe.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session

    with Session(engine) as inspection_session:
        with TestClient(app) as test_client:
            yield test_client, inspection_session

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def create_account_and_headers(
    client: TestClient,
    email: str,
) -> dict[str, str]:
    """Register and log in one test user."""

    password = "correct-horse-battery-staple"
    register_response = client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def clothing_payload(name: str = "Blue Oxford Shirt") -> dict[str, str]:
    return {
        "name": name,
        "category": "top",
        "color": "light blue",
        "description": "A smart-casual cotton shirt.",
    }


def test_user_can_create_list_read_update_and_delete_item(
    client: tuple[TestClient, Session],
) -> None:
    test_client, _ = client
    headers = create_account_and_headers(test_client, "owner@example.com")

    create_response = test_client.post(
        "/wardrobe/items",
        json=clothing_payload(),
        headers=headers,
    )

    assert create_response.status_code == 201
    assert create_response.json() == {
        "id": 1,
        "name": "Blue Oxford Shirt",
        "category": "top",
        "color": "light blue",
        "description": "A smart-casual cotton shirt.",
        "processing_status": "completed",
    }
    assert "user_id" not in create_response.json()

    list_response = test_client.get("/wardrobe/items", headers=headers)
    detail_response = test_client.get("/wardrobe/items/1", headers=headers)

    assert list_response.status_code == 200
    assert list_response.json() == [create_response.json()]
    assert detail_response.status_code == 200
    assert detail_response.json() == create_response.json()

    update_response = test_client.patch(
        "/wardrobe/items/1",
        json={"name": "  Blue Work Shirt  ", "description": None},
        headers=headers,
    )

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Blue Work Shirt"
    assert update_response.json()["description"] is None
    assert update_response.json()["category"] == "top"

    delete_response = test_client.delete("/wardrobe/items/1", headers=headers)
    missing_response = test_client.get("/wardrobe/items/1", headers=headers)

    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert missing_response.status_code == 404
    assert missing_response.json() == {"detail": "Clothing item not found"}


def test_every_wardrobe_route_requires_authentication(
    client: tuple[TestClient, Session],
) -> None:
    test_client, _ = client

    responses = [
        test_client.post("/wardrobe/items", json=clothing_payload()),
        test_client.get("/wardrobe/items"),
        test_client.get("/wardrobe/items/1"),
        test_client.patch("/wardrobe/items/1", json={"color": "navy"}),
        test_client.delete("/wardrobe/items/1"),
    ]

    assert all(response.status_code == 401 for response in responses)


def test_cross_user_items_are_hidden_from_all_operations(
    client: tuple[TestClient, Session],
) -> None:
    test_client, _ = client
    owner_headers = create_account_and_headers(test_client, "owner@example.com")
    other_headers = create_account_and_headers(test_client, "other@example.com")
    created = test_client.post(
        "/wardrobe/items",
        json=clothing_payload(),
        headers=owner_headers,
    )
    item_id = created.json()["id"]

    other_list = test_client.get("/wardrobe/items", headers=other_headers)
    other_detail = test_client.get(
        f"/wardrobe/items/{item_id}", headers=other_headers
    )
    other_update = test_client.patch(
        f"/wardrobe/items/{item_id}",
        json={"color": "red"},
        headers=other_headers,
    )
    other_delete = test_client.delete(
        f"/wardrobe/items/{item_id}", headers=other_headers
    )

    assert other_list.json() == []
    assert other_detail.status_code == 404
    assert other_update.status_code == 404
    assert other_delete.status_code == 404

    owner_detail = test_client.get(
        f"/wardrobe/items/{item_id}", headers=owner_headers
    )
    assert owner_detail.status_code == 200
    assert owner_detail.json()["color"] == "light blue"


@pytest.mark.parametrize(
    "changes",
    [
        {"category": "hat"},
        {"name": "   "},
        {"color": ""},
        {"processing_status": "failed"},
        {"user_id": 999},
    ],
)
def test_create_rejects_invalid_or_server_controlled_metadata(
    client: tuple[TestClient, Session],
    changes: dict[str, object],
) -> None:
    test_client, _ = client
    headers = create_account_and_headers(test_client, "validation@example.com")
    payload: dict[str, object] = clothing_payload()
    payload.update(changes)

    response = test_client.post("/wardrobe/items", json=payload, headers=headers)

    assert response.status_code == 422


def test_update_rejects_null_required_metadata(
    client: tuple[TestClient, Session],
) -> None:
    test_client, _ = client
    headers = create_account_and_headers(test_client, "update@example.com")
    test_client.post("/wardrobe/items", json=clothing_payload(), headers=headers)

    response = test_client.patch(
        "/wardrobe/items/1",
        json={"category": None},
        headers=headers,
    )

    assert response.status_code == 422


def test_limit_counts_only_confirmed_items(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    headers = create_account_and_headers(test_client, "limit@example.com")

    pending_item = ClothingItem(
        user_id=1,
        name="Pending Upload",
        category=ClothingCategory.TOP,
        color="unknown",
        processing_status=ProcessingStatus.PENDING,
    )
    session.add(pending_item)
    session.commit()

    for number in range(15):
        response = test_client.post(
            "/wardrobe/items",
            json=clothing_payload(f"Confirmed item {number + 1}"),
            headers=headers,
        )
        assert response.status_code == 201

    limit_response = test_client.post(
        "/wardrobe/items",
        json=clothing_payload("One item too many"),
        headers=headers,
    )

    assert limit_response.status_code == 409
    assert limit_response.json() == {
        "detail": "Wardrobe limit of 15 confirmed items reached"
    }
    assert len(test_client.get("/wardrobe/items", headers=headers).json()) == 16


def test_deleting_confirmed_item_frees_one_limit_slot(
    client: tuple[TestClient, Session],
) -> None:
    test_client, _ = client
    headers = create_account_and_headers(test_client, "slot@example.com")

    for number in range(15):
        response = test_client.post(
            "/wardrobe/items",
            json=clothing_payload(f"Item {number + 1}"),
            headers=headers,
        )
        assert response.status_code == 201

    assert test_client.delete("/wardrobe/items/1", headers=headers).status_code == 204
    replacement = test_client.post(
        "/wardrobe/items",
        json=clothing_payload("Replacement item"),
        headers=headers,
    )

    assert replacement.status_code == 201

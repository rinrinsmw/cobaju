"""Upload validation, storage, ownership, and cleanup tests for Phase 4."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings
from app.database import get_session
from app.main import app
from app.routers import wardrobe as wardrobe_router


JPEG_BYTES = b"\xff\xd8\xff\xe0small-jpeg\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\nsmall-png"
WEBP_BYTES = b"RIFF\x0c\x00\x00\x00WEBPsmall-webp"


@pytest.fixture
def client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, Path], None, None]:
    """Give every upload test isolated database and storage directories."""

    upload_directory = tmp_path / "uploads"
    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-secret-with-enough-entropy")
    monkeypatch.setenv("UPLOAD_DIRECTORY", str(upload_directory))
    get_settings.cache_clear()

    engine = create_engine(
        f"sqlite:///{tmp_path / 'uploads.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    with TestClient(app) as test_client:
        yield test_client, upload_directory

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def create_account_and_headers(client: TestClient, email: str) -> dict[str, str]:
    """Register and log in a test account."""

    password = "correct-horse-battery-staple"
    assert client.post(
        "/auth/register",
        json={"email": email, "password": password},
    ).status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def create_item(client: TestClient, headers: dict[str, str], name: str = "Shirt") -> int:
    """Create a metadata item that can receive an image."""

    response = client.post(
        "/wardrobe/items",
        headers=headers,
        json={"name": name, "category": "top", "color": "blue"},
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "extension"),
    [
        ("item.jpg", "image/jpeg", JPEG_BYTES, ".jpg"),
        ("item.png", "image/png", PNG_BYTES, ".png"),
        ("item.webp", "image/webp", WEBP_BYTES, ".webp"),
    ],
)
def test_combined_upload_creates_pending_item_and_stores_image(
    client: tuple[TestClient, Path],
    filename: str,
    content_type: str,
    content: bytes,
    extension: str,
) -> None:
    test_client, upload_directory = client
    headers = create_account_and_headers(test_client, "combined@example.com")

    response = test_client.post(
        "/wardrobe/items/upload",
        headers=headers,
        files={"image": (filename, content, content_type)},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Pending analysis"
    assert body["color"] == "Unknown"
    assert body["analysis_completed"] is False
    assert body["processing_status"] == "pending"
    assert body["original_image_path"].startswith("1/")
    assert body["original_image_path"].endswith(extension)
    assert (upload_directory / body["original_image_path"]).read_bytes() == content

    listed_items = test_client.get("/wardrobe/items", headers=headers).json()
    assert [item["id"] for item in listed_items] == [body["id"]]


def test_combined_upload_rejects_invalid_image_without_creating_item(
    client: tuple[TestClient, Path],
) -> None:
    test_client, upload_directory = client
    headers = create_account_and_headers(test_client, "combined-invalid@example.com")

    response = test_client.post(
        "/wardrobe/items/upload",
        headers=headers,
        files={"image": ("spoofed.png", JPEG_BYTES, "image/png")},
    )

    assert response.status_code == 415
    assert list(upload_directory.rglob("*.*")) == []
    assert test_client.get("/wardrobe/items", headers=headers).json() == []


def test_combined_upload_requires_authentication(
    client: tuple[TestClient, Path],
) -> None:
    test_client, upload_directory = client

    response = test_client.post(
        "/wardrobe/items/upload",
        files={"image": ("shirt.jpg", JPEG_BYTES, "image/jpeg")},
    )

    assert response.status_code == 401
    assert list(upload_directory.rglob("*.*")) == []


def test_combined_upload_is_not_counted_as_a_confirmed_item(
    client: tuple[TestClient, Path],
) -> None:
    test_client, _ = client
    headers = create_account_and_headers(test_client, "combined-limit@example.com")
    for item_number in range(15):
        create_item(test_client, headers, f"Confirmed item {item_number}")

    response = test_client.post(
        "/wardrobe/items/upload",
        headers=headers,
        files={"image": ("shirt.jpg", JPEG_BYTES, "image/jpeg")},
    )

    assert response.status_code == 201
    assert response.json()["processing_status"] == "pending"


def test_combined_upload_removes_file_when_item_creation_fails(
    client: tuple[TestClient, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, upload_directory = client
    headers = create_account_and_headers(test_client, "combined-failure@example.com")

    def fail_item_creation(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError("simulated database failure")

    monkeypatch.setattr(
        wardrobe_router,
        "create_uploaded_clothing_item",
        fail_item_creation,
    )
    response = test_client.post(
        "/wardrobe/items/upload",
        headers=headers,
        files={"image": ("shirt.jpg", JPEG_BYTES, "image/jpeg")},
    )

    assert response.status_code == 500
    assert list(upload_directory.rglob("*.*")) == []
    assert test_client.get("/wardrobe/items", headers=headers).json() == []


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "extension"),
    [
        ("item.jpg", "image/jpeg", JPEG_BYTES, ".jpg"),
        ("item.png", "image/png", PNG_BYTES, ".png"),
        ("item.webp", "image/webp", WEBP_BYTES, ".webp"),
    ],
)
def test_valid_supported_image_is_stored_and_recorded(
    client: tuple[TestClient, Path],
    filename: str,
    content_type: str,
    content: bytes,
    extension: str,
) -> None:
    test_client, upload_directory = client
    headers = create_account_and_headers(test_client, "owner@example.com")
    item_id = create_item(test_client, headers)

    response = test_client.post(
        f"/wardrobe/items/{item_id}/image",
        headers=headers,
        files={"image": (filename, content, content_type)},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["processing_status"] == "pending"
    assert body["original_image_path"].startswith("1/")
    assert body["original_image_path"].endswith(extension)
    stored_file = upload_directory / body["original_image_path"]
    assert stored_file.read_bytes() == content
    assert stored_file.name != filename


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        ("notes.txt", "text/plain", b"not an image"),
        ("spoofed.png", "image/png", JPEG_BYTES),
        ("empty.jpg", "image/jpeg", b""),
    ],
)
def test_invalid_or_spoofed_formats_are_rejected_without_files(
    client: tuple[TestClient, Path],
    filename: str,
    content_type: str,
    content: bytes,
) -> None:
    test_client, upload_directory = client
    headers = create_account_and_headers(test_client, "invalid@example.com")
    item_id = create_item(test_client, headers)

    response = test_client.post(
        f"/wardrobe/items/{item_id}/image",
        headers=headers,
        files={"image": (filename, content, content_type)},
    )

    assert response.status_code == 415
    assert list(upload_directory.rglob("*")) == []
    detail = test_client.get(f"/wardrobe/items/{item_id}", headers=headers).json()
    assert detail["original_image_path"] is None
    assert detail["processing_status"] == "completed"


def test_image_larger_than_five_megabytes_is_rejected_and_removed(
    client: tuple[TestClient, Path],
) -> None:
    test_client, upload_directory = client
    headers = create_account_and_headers(test_client, "large@example.com")
    item_id = create_item(test_client, headers)
    oversized_png = PNG_BYTES + b"0" * (5 * 1024 * 1024)

    response = test_client.post(
        f"/wardrobe/items/{item_id}/image",
        headers=headers,
        files={"image": ("large.png", oversized_png, "image/png")},
    )

    assert response.status_code == 413
    assert list(upload_directory.rglob("*.*")) == []


def test_same_client_filename_never_overwrites_another_upload(
    client: tuple[TestClient, Path],
) -> None:
    test_client, upload_directory = client
    headers = create_account_and_headers(test_client, "unique@example.com")
    first_id = create_item(test_client, headers, "First shirt")
    second_id = create_item(test_client, headers, "Second shirt")

    first = test_client.post(
        f"/wardrobe/items/{first_id}/image",
        headers=headers,
        files={"image": ("shirt.jpg", JPEG_BYTES, "image/jpeg")},
    )
    second = test_client.post(
        f"/wardrobe/items/{second_id}/image",
        headers=headers,
        files={"image": ("shirt.jpg", JPEG_BYTES + b"2", "image/jpeg")},
    )

    first_path = first.json()["original_image_path"]
    second_path = second.json()["original_image_path"]
    assert first_path != second_path
    assert (upload_directory / first_path).read_bytes() == JPEG_BYTES
    assert (upload_directory / second_path).read_bytes() == JPEG_BYTES + b"2"


def test_upload_requires_authentication_and_item_ownership(
    client: tuple[TestClient, Path],
) -> None:
    test_client, upload_directory = client
    owner_headers = create_account_and_headers(test_client, "owner@example.com")
    other_headers = create_account_and_headers(test_client, "other@example.com")
    item_id = create_item(test_client, owner_headers)
    files = {"image": ("shirt.jpg", JPEG_BYTES, "image/jpeg")}

    unauthenticated = test_client.post(
        f"/wardrobe/items/{item_id}/image",
        files=files,
    )
    cross_user = test_client.post(
        f"/wardrobe/items/{item_id}/image",
        headers=other_headers,
        files=files,
    )

    assert unauthenticated.status_code == 401
    assert cross_user.status_code == 404
    assert list(upload_directory.rglob("*")) == []


def test_second_image_for_same_item_is_rejected_without_replacement(
    client: tuple[TestClient, Path],
) -> None:
    test_client, upload_directory = client
    headers = create_account_and_headers(test_client, "single@example.com")
    item_id = create_item(test_client, headers)
    first = test_client.post(
        f"/wardrobe/items/{item_id}/image",
        headers=headers,
        files={"image": ("first.jpg", JPEG_BYTES, "image/jpeg")},
    )
    first_path = first.json()["original_image_path"]

    second = test_client.post(
        f"/wardrobe/items/{item_id}/image",
        headers=headers,
        files={"image": ("second.png", PNG_BYTES, "image/png")},
    )

    assert second.status_code == 409
    assert (upload_directory / first_path).read_bytes() == JPEG_BYTES
    assert len(list(upload_directory.rglob("*.*"))) == 1


def test_new_file_is_removed_when_database_update_fails(
    client: tuple[TestClient, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, upload_directory = client
    headers = create_account_and_headers(test_client, "failure@example.com")
    item_id = create_item(test_client, headers)

    def fail_database_update(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError("simulated database failure")

    monkeypatch.setattr(
        wardrobe_router,
        "attach_image_to_clothing_item",
        fail_database_update,
    )
    response = test_client.post(
        f"/wardrobe/items/{item_id}/image",
        headers=headers,
        files={"image": ("shirt.jpg", JPEG_BYTES, "image/jpeg")},
    )

    assert response.status_code == 500
    assert list(upload_directory.rglob("*.*")) == []


def test_deleting_item_removes_its_local_image(
    client: tuple[TestClient, Path],
) -> None:
    test_client, upload_directory = client
    headers = create_account_and_headers(test_client, "delete@example.com")
    item_id = create_item(test_client, headers)
    upload = test_client.post(
        f"/wardrobe/items/{item_id}/image",
        headers=headers,
        files={"image": ("shirt.jpg", JPEG_BYTES, "image/jpeg")},
    )
    stored_file = upload_directory / upload.json()["original_image_path"]
    assert stored_file.exists()

    response = test_client.delete(f"/wardrobe/items/{item_id}", headers=headers)

    assert response.status_code == 204
    assert not stored_file.exists()


def test_owner_can_read_image_but_another_user_cannot(
    client: tuple[TestClient, Path],
) -> None:
    test_client, _ = client
    owner_headers = create_account_and_headers(test_client, "image-owner@example.com")
    other_headers = create_account_and_headers(test_client, "image-other@example.com")
    item_id = create_item(test_client, owner_headers)
    test_client.post(
        f"/wardrobe/items/{item_id}/image",
        headers=owner_headers,
        files={"image": ("shirt.jpg", JPEG_BYTES, "image/jpeg")},
    )

    owned = test_client.get(f"/wardrobe/items/{item_id}/image", headers=owner_headers)
    cross_user = test_client.get(f"/wardrobe/items/{item_id}/image", headers=other_headers)

    assert owned.status_code == 200
    assert owned.content == JPEG_BYTES
    assert cross_user.status_code == 404

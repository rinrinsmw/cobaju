"""Mocked AI workflow and OpenRouter contract tests for Phase 5."""

from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import Settings, get_settings
from app.database import get_session
from app.main import app
from app.routers.wardrobe import get_clothing_vision_provider
from app.schemas.wardrobe import ClothingGuardrailResult, ClothingMetadata
from app.services.clothing_analysis import ClothingAnalysisTracer
from app.services.openrouter import OpenRouterResponseError, OpenRouterVisionProvider


JPEG_BYTES = b"\xff\xd8\xff\xe0mock-clothing\xff\xd9"


class FakeVisionProvider:
    """Deterministic replacement for both paid OpenRouter calls."""

    def __init__(self) -> None:
        self.is_clothing = True
        self.classify_calls = 0
        self.analyze_calls = 0

    def classify_image(self, image_path: Path) -> ClothingGuardrailResult:
        assert image_path.read_bytes() == JPEG_BYTES
        self.classify_calls += 1
        return ClothingGuardrailResult(
            is_clothing=self.is_clothing,
            reason="One visible garment" if self.is_clothing else "A plate of food",
        )

    def analyze_image(self, image_path: Path) -> ClothingMetadata:
        assert image_path.read_bytes() == JPEG_BYTES
        self.analyze_calls += 1
        return ClothingMetadata(
            name="Blue crew-neck T-shirt",
            category="top",
            color="blue",
            description="Short-sleeve crew-neck T-shirt.",
        )


@pytest.fixture
def client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, Path, FakeVisionProvider], None, None]:
    """Use isolated storage, database, and a fake vision provider."""

    upload_directory = tmp_path / "uploads"
    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-secret-with-enough-entropy")
    monkeypatch.setenv("UPLOAD_DIRECTORY", str(upload_directory))
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    get_settings.cache_clear()

    engine = create_engine(
        f"sqlite:///{tmp_path / 'analysis.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    fake_provider = FakeVisionProvider()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_clothing_vision_provider] = lambda: fake_provider
    with TestClient(app) as test_client:
        yield test_client, upload_directory, fake_provider

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


def create_and_upload(client: TestClient, headers: dict[str, str]) -> tuple[int, str]:
    created = client.post(
        "/wardrobe/items",
        headers=headers,
        json={"name": "Upload", "category": "top", "color": "unknown"},
    )
    item_id = created.json()["id"]
    uploaded = client.post(
        f"/wardrobe/items/{item_id}/image",
        headers=headers,
        files={"image": ("item.jpg", JPEG_BYTES, "image/jpeg")},
    )
    assert uploaded.status_code == 201
    return item_id, uploaded.json()["original_image_path"]


def test_clothing_image_generates_editable_draft_then_user_confirms(
    client: tuple[TestClient, Path, FakeVisionProvider],
) -> None:
    test_client, _, fake_provider = client
    headers = auth_headers(test_client, "owner@example.com")
    item_id, _ = create_and_upload(test_client, headers)

    analyzed = test_client.post(
        f"/wardrobe/items/{item_id}/analyze", headers=headers
    )

    assert analyzed.status_code == 200
    assert analyzed.json()["processing_status"] == "pending"
    assert analyzed.json()["name"] == "Blue crew-neck T-shirt"
    assert analyzed.json()["category"] == "top"
    assert analyzed.json()["analysis_completed"] is True
    assert fake_provider.classify_calls == 1
    assert fake_provider.analyze_calls == 1

    edited = test_client.patch(
        f"/wardrobe/items/{item_id}",
        headers=headers,
        json={"name": "My blue T-shirt", "color": "navy blue"},
    )
    confirmed = test_client.post(
        f"/wardrobe/items/{item_id}/confirm", headers=headers
    )

    assert edited.status_code == 200
    assert confirmed.status_code == 200
    assert confirmed.json()["name"] == "My blue T-shirt"
    assert confirmed.json()["color"] == "navy blue"
    assert confirmed.json()["processing_status"] == "completed"


def test_clear_non_clothing_image_is_rejected_and_deleted(
    client: tuple[TestClient, Path, FakeVisionProvider],
) -> None:
    test_client, upload_directory, fake_provider = client
    fake_provider.is_clothing = False
    headers = auth_headers(test_client, "reject@example.com")
    item_id, relative_path = create_and_upload(test_client, headers)
    stored_file = upload_directory / relative_path

    response = test_client.post(
        f"/wardrobe/items/{item_id}/analyze", headers=headers
    )
    detail = test_client.get(f"/wardrobe/items/{item_id}", headers=headers)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Image must contain one clearly visible clothing item"
    }
    assert fake_provider.analyze_calls == 0
    assert detail.json()["original_image_path"] is None
    assert detail.json()["processing_status"] == "failed"
    assert not stored_file.exists()


def test_analysis_and_confirmation_enforce_ownership_and_state(
    client: tuple[TestClient, Path, FakeVisionProvider],
) -> None:
    test_client, _, fake_provider = client
    owner = auth_headers(test_client, "owner@example.com")
    other = auth_headers(test_client, "other@example.com")
    item_id, _ = create_and_upload(test_client, owner)

    cross_user = test_client.post(
        f"/wardrobe/items/{item_id}/analyze", headers=other
    )
    premature_confirm = test_client.post(
        f"/wardrobe/items/{item_id}/confirm", headers=owner
    )

    assert cross_user.status_code == 404
    assert premature_confirm.status_code == 409
    assert fake_provider.classify_calls == 0


def test_invalid_generated_metadata_marks_item_failed_and_keeps_image(
    client: tuple[TestClient, Path, FakeVisionProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, upload_directory, fake_provider = client
    headers = auth_headers(test_client, "invalid-ai@example.com")
    item_id, relative_path = create_and_upload(test_client, headers)

    def invalid_metadata(image_path: Path) -> Any:
        return {"name": "Hat", "category": "hat", "color": "red"}

    monkeypatch.setattr(fake_provider, "analyze_image", invalid_metadata)
    response = test_client.post(
        f"/wardrobe/items/{item_id}/analyze", headers=headers
    )
    detail = test_client.get(f"/wardrobe/items/{item_id}", headers=headers)

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Clothing analysis could not be completed"
    }
    assert detail.json()["processing_status"] == "failed"
    assert detail.json()["analysis_completed"] is False
    assert detail.json()["original_image_path"] == relative_path
    assert (upload_directory / relative_path).exists()


def test_openrouter_uses_separate_temperatures_and_validates_responses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_path = tmp_path / "item.jpg"
    image_path.write_bytes(JPEG_BYTES)
    settings = Settings(
        openrouter_api_key="test-key",
        openrouter_guardrail_model="guardrail-model",
        openrouter_vision_model="vision-model",
        guardrail_temperature=0.0,
        vision_temperature=0.1,
    )
    provider = OpenRouterVisionProvider(settings)
    payloads: list[dict[str, Any]] = []
    responses = [
        {"is_clothing": True, "reason": "One shirt"},
        {
            "name": "White shirt",
            "category": "top",
            "color": "white",
            "description": "Long-sleeve collared shirt.",
        },
    ]

    def fake_post(*args: Any, **kwargs: Any) -> httpx.Response:
        payloads.append(kwargs["json"])
        content = responses[len(payloads) - 1]
        request = httpx.Request("POST", str(args[0]))
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": __import__("json").dumps(content)}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    assert provider.classify_image(image_path).is_clothing is True
    assert provider.analyze_image(image_path).name == "White shirt"
    assert payloads[0]["temperature"] == 0.0
    assert payloads[1]["temperature"] == 0.1
    assert payloads[0]["response_format"]["json_schema"]["strict"] is True
    metadata_schema = payloads[1]["response_format"]["json_schema"]["schema"]
    assert "description" in metadata_schema["required"]


def test_openrouter_rejects_metadata_outside_stable_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_path = tmp_path / "item.jpg"
    image_path.write_bytes(JPEG_BYTES)
    provider = OpenRouterVisionProvider(
        Settings(openrouter_api_key="test-key", openrouter_vision_model="vision")
    )

    def invalid_post(*args: Any, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", str(args[0]))
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"name":"Hat","category":"hat","color":"red"}'
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", invalid_post)

    with pytest.raises(OpenRouterResponseError):
        provider.analyze_image(image_path)


def test_langfuse_credentials_are_passed_from_application_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeObservation:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: Any) -> None:
            return None

    class FakeLangfuse:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        def start_as_current_observation(self, **kwargs: Any) -> FakeObservation:
            captured["observation"] = kwargs
            return FakeObservation()

    monkeypatch.setattr("langfuse.Langfuse", FakeLangfuse)
    tracer = ClothingAnalysisTracer(
        Settings(
            langfuse_enabled=True,
            langfuse_public_key="public-test-key",
            langfuse_secret_key="secret-test-key",
            langfuse_base_url="https://langfuse.example.com",
        )
    )

    with tracer.observation("clothing_analysis"):
        pass

    assert captured["public_key"] == "public-test-key"
    assert captured["secret_key"] == "secret-test-key"
    assert captured["base_url"] == "https://langfuse.example.com"
    assert captured["observation"]["name"] == "clothing_analysis"

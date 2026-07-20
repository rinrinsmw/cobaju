"""Tests for application settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_DIR, Settings


def test_relative_sqlite_path_is_resolved_from_backend_directory() -> None:
    settings = Settings(database_url="sqlite:///./custom.db")

    assert settings.resolved_database_url == f"sqlite:///{BACKEND_DIR / 'custom.db'}"


def test_absolute_sqlite_path_is_not_changed(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'absolute.db'}"
    settings = Settings(database_url=database_url)

    assert settings.resolved_database_url == database_url


def test_relative_upload_directory_is_resolved_from_backend_directory() -> None:
    settings = Settings(upload_directory="./custom-uploads")

    assert settings.resolved_upload_directory == BACKEND_DIR / "custom-uploads"


def test_absolute_upload_directory_is_not_changed(tmp_path: Path) -> None:
    upload_directory = tmp_path / "uploads"
    settings = Settings(upload_directory=str(upload_directory))

    assert settings.resolved_upload_directory == upload_directory


def test_relative_chroma_directory_is_resolved_from_backend_directory() -> None:
    settings = Settings(chroma_directory="./custom-chroma")

    assert settings.resolved_chroma_directory == BACKEND_DIR / "custom-chroma"


def test_absolute_chroma_directory_is_not_changed(tmp_path: Path) -> None:
    chroma_directory = tmp_path / "chroma"
    settings = Settings(chroma_directory=str(chroma_directory))

    assert settings.resolved_chroma_directory == chroma_directory


def test_celery_retry_settings_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        Settings(celery_task_max_retries=-1)

    with pytest.raises(ValidationError):
        Settings(celery_task_retry_delay_seconds=-1)


def test_wardrobe_search_limit_must_be_between_one_and_fifteen() -> None:
    with pytest.raises(ValidationError):
        Settings(wardrobe_search_limit=0)

    with pytest.raises(ValidationError):
        Settings(wardrobe_search_limit=16)


def test_agent_temperatures_and_limits_have_safe_defaults() -> None:
    settings = Settings()

    assert settings.chat_guardrail_temperature == 0.0
    assert settings.stylist_temperature == 0.5
    assert settings.stylist_repair_temperature == 0.1
    assert settings.evaluator_temperature == 0.0
    assert settings.stylist_max_turns == 8
    assert settings.stylist_max_tool_calls == 8
    assert settings.chat_guardrail_prompt_version == "chat-guardrail-v1"
    assert settings.stylist_prompt_version == "stylist-v2"
    assert settings.stylist_repair_prompt_version == "stylist-repair-v1"
    assert settings.evaluator_prompt_version == "outfit-evaluator-v1"


def test_langfuse_host_environment_name_is_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")

    assert Settings().langfuse_base_url == "https://langfuse.example.com"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stylist_max_turns", 0),
        ("stylist_max_turns", 21),
        ("stylist_max_tool_calls", 0),
        ("stylist_max_tool_calls", 31),
    ],
)
def test_phase_9_limits_are_bounded(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})

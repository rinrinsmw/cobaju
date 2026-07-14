"""Tests for application settings."""

from pathlib import Path

from app.core.config import BACKEND_DIR, Settings


def test_relative_sqlite_path_is_resolved_from_backend_directory() -> None:
    settings = Settings(database_url="sqlite:///./custom.db")

    assert settings.resolved_database_url == f"sqlite:///{BACKEND_DIR / 'custom.db'}"


def test_absolute_sqlite_path_is_not_changed(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'absolute.db'}"
    settings = Settings(database_url=database_url)

    assert settings.resolved_database_url == database_url

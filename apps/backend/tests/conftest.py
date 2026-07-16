"""Shared test isolation from developer credentials and cached providers."""

from collections.abc import Generator

import pytest

from app.core.config import get_settings
from app.dependencies import get_wardrobe_vector_store


@pytest.fixture(autouse=True)
def disable_unmocked_embedding_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Never let a local .env turn an isolated test into a paid API call."""

    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_EMBEDDING_MODEL", "")
    get_settings.cache_clear()
    get_wardrobe_vector_store.cache_clear()
    yield
    get_settings.cache_clear()
    get_wardrobe_vector_store.cache_clear()

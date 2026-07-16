"""Mockable text-embedding providers used by wardrobe retrieval."""

from typing import Any, Protocol

import httpx

from app.core.config import Settings


class EmbeddingError(Exception):
    """Raised when text cannot be converted into a valid embedding."""


class EmbeddingProvider(Protocol):
    """Small provider boundary so retrieval tests never make paid calls."""

    def embed_text(self, text: str) -> list[float]: ...


class OpenRouterEmbeddingProvider:
    """Generate one text embedding through OpenRouter's embeddings API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def embed_text(self, text: str) -> list[float]:
        api_key = self.settings.openrouter_api_key.get_secret_value()
        model = self.settings.openrouter_embedding_model
        if not api_key or not model:
            raise EmbeddingError(
                "OpenRouter API key and embedding model settings are required"
            )

        try:
            response = httpx.post(
                f"{self.settings.openrouter_base_url.rstrip('/')}/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "X-OpenRouter-Title": self.settings.app_name,
                },
                json={"model": model, "input": text, "encoding_format": "float"},
                timeout=self.settings.openrouter_timeout_seconds,
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            embedding = body["data"][0]["embedding"]
            if not isinstance(embedding, list) or not embedding:
                raise TypeError("embedding is empty or has the wrong type")
            vector = [float(value) for value in embedding]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise EmbeddingError("OpenRouter returned an invalid embedding") from error

        return vector

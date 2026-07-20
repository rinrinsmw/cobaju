"""Persistent, ownership-filtered Chroma index for confirmed wardrobe items."""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

import chromadb

from app.core.config import Settings
from app.models.clothing_item import ClothingCategory, ClothingItem
from app.observability import Observability
from app.services.embeddings import EmbeddingProvider, OpenRouterEmbeddingProvider


class WardrobeVectorError(Exception):
    """Raised when a vector record cannot be stored or retrieved safely."""


@dataclass(frozen=True)
class WardrobeSearchResult:
    """One structured wardrobe match returned by semantic retrieval."""

    item_id: int
    name: str
    category: ClothingCategory
    color: str
    description: str | None
    distance: float


def build_clothing_description(item: ClothingItem) -> str:
    """Build stable searchable text only from validated clothing metadata."""

    text = f"{item.color} {item.category.value} named {item.name}."
    if item.description:
        text = f"{text} {item.description}"
    return text


class RetrievalTracer:
    """Compatibility wrapper around the shared observability abstraction."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._observability = Observability(settings)

    def observation(
        self,
        *,
        user_id: int,
        category: ClothingCategory | None,
    ) -> AbstractContextManager[Any]:
        return self._observability.observe(
            "wardrobe_retrieval",
            as_type="retriever",
            input={
                "user_id": user_id,
                "category": category.value if category else None,
            },
        )


class WardrobeVectorStore:
    """Keep confirmed items in Chroma and query them with trusted filters."""

    def __init__(
        self,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        *,
        client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.embedding_provider = embedding_provider
        self.client = client or chromadb.PersistentClient(
            path=str(settings.resolved_chroma_directory)
        )
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_name,
            configuration={"hnsw": {"space": "cosine"}},
        )
        self.tracer = RetrievalTracer(settings)

    def upsert_item(self, item: ClothingItem) -> None:
        """Create or replace one record using its globally unique database ID."""

        if item.id is None:
            raise WardrobeVectorError("Cannot index an unsaved clothing item")
        document = build_clothing_description(item)
        try:
            embedding = self.embedding_provider.embed_text(document)
            self.collection.upsert(
                ids=[self._record_id(item.id)],
                embeddings=[embedding],
                documents=[document],
                metadatas=[
                    {
                        "item_id": item.id,
                        "user_id": item.user_id,
                        "name": item.name,
                        "category": item.category.value,
                        "color": item.color,
                        "description": item.description or "",
                    }
                ],
            )
        except Exception as error:
            if isinstance(error, WardrobeVectorError):
                raise
            raise WardrobeVectorError("Could not index clothing item") from error

    def delete_item(self, item_id: int) -> None:
        """Delete one vector record; deleting a missing ID is idempotent."""

        try:
            self.collection.delete(ids=[self._record_id(item_id)])
        except Exception as error:
            raise WardrobeVectorError("Could not delete clothing index record") from error

    def index_missing_items(self, items: list[ClothingItem]) -> None:
        """Backfill confirmed database items that predate the vector index."""

        persisted_items = [item for item in items if item.id is not None]
        if not persisted_items:
            return
        record_ids = [self._record_id(item.id) for item in persisted_items]
        try:
            existing = self.collection.get(ids=record_ids, include=[])
            existing_ids = set(existing.get("ids") or [])
            for item in persisted_items:
                if self._record_id(item.id) not in existing_ids:
                    self.upsert_item(item)
        except Exception as error:
            if isinstance(error, WardrobeVectorError):
                raise
            raise WardrobeVectorError("Could not backfill wardrobe index") from error

    def search(
        self,
        *,
        query: str,
        user_id: int,
        category: ClothingCategory | None = None,
        limit: int | None = None,
    ) -> list[WardrobeSearchResult]:
        """Return semantically ranked records belonging only to one user."""

        result_limit = min(limit or self.settings.wardrobe_search_limit, 15)
        where: dict[str, Any]
        if category is None:
            where = {"user_id": user_id}
        else:
            where = {
                "$and": [
                    {"user_id": user_id},
                    {"category": category.value},
                ]
            }

        try:
            with self.tracer.observation(user_id=user_id, category=category):
                query_embedding = self.embedding_provider.embed_text(query)
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=result_limit,
                    where=where,
                    include=["metadatas", "distances"],
                )
            metadatas = (results.get("metadatas") or [[]])[0]
            distances = (results.get("distances") or [[]])[0]
            matches: list[WardrobeSearchResult] = []
            for metadata, distance in zip(metadatas, distances, strict=True):
                if metadata is None:
                    continue
                matches.append(
                    WardrobeSearchResult(
                        item_id=int(metadata["item_id"]),
                        name=str(metadata["name"]),
                        category=ClothingCategory(str(metadata["category"])),
                        color=str(metadata["color"]),
                        description=str(metadata["description"]) or None,
                        distance=float(distance),
                    )
                )
            return matches
        except Exception as error:
            if isinstance(error, WardrobeVectorError):
                raise
            raise WardrobeVectorError("Could not search wardrobe index") from error

    @staticmethod
    def _record_id(item_id: int) -> str:
        return f"clothing-item:{item_id}"


def create_wardrobe_vector_store(settings: Settings) -> WardrobeVectorStore:
    """Build the production vector store with the configured provider."""

    return WardrobeVectorStore(settings, OpenRouterEmbeddingProvider(settings))

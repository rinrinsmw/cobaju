"""Public response schemas for recommendation history."""

from datetime import datetime

from pydantic import BaseModel

from app.models.clothing_item import ClothingCategory


class HistoricalClothingItem(BaseModel):
    """Current wardrobe details for a historically selected item."""

    item_id: int
    available: bool
    name: str | None = None
    category: ClothingCategory | None = None
    color: str | None = None


class RecommendationHistoryRead(BaseModel):
    """One completed recommendation safe to render after item deletion."""

    id: int
    original_request: str
    selected_item_ids: list[int]
    items: list[HistoricalClothingItem]
    explanation: str
    evaluation_score: float
    created_at: datetime

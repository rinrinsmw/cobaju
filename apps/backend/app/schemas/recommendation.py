"""Public response schemas for recommendation history."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class RecommendationSaveRequest(BaseModel):
    """An opaque server-signed receipt submitted by the Lookbook button."""

    save_token: str = Field(min_length=1)
    display_title: str | None = Field(default=None, min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("display_title")
    @classmethod
    def normalize_display_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = value.strip()
        if not title:
            raise ValueError("display title must not be blank")
        return title


class RecommendationSaveClaims(BaseModel):
    """Trusted recommendation data recovered from a valid save receipt."""

    user_request: str = Field(min_length=1, max_length=500)
    item_ids: list[int] = Field(max_length=15)
    explanation: str = Field(min_length=1, max_length=1200)
    evaluation_score: float = Field(ge=0, le=10)

    @field_validator("item_ids")
    @classmethod
    def item_ids_must_be_unique_and_positive(cls, value: list[int]) -> list[int]:
        if any(item_id < 1 for item_id in value) or len(value) != len(set(value)):
            raise ValueError("item IDs must be unique and positive")
        return value


class RecommendationSaved(BaseModel):
    """Confirmation returned after the user explicitly saves a look."""

    id: int

"""Structured inputs and outputs shared by wardrobe services and MCP tools."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.clothing_item import ClothingCategory


class ToolClothingItem(BaseModel):
    """Safe confirmed-item metadata exposed to the stylist tool layer."""

    item_id: int
    name: str
    category: ClothingCategory
    color: str
    description: str | None


class ToolSearchMatch(ToolClothingItem):
    """One ownership-checked semantic search match."""

    distance: float


class SearchWardrobeOutput(BaseModel):
    """Structured semantic search response."""

    matches: list[ToolSearchMatch]


class WardrobeCategorySummary(BaseModel):
    """Available confirmed items in one category."""

    category: ClothingCategory
    item_count: int = Field(ge=1)


class ListWardrobeCategoriesOutput(BaseModel):
    """Structured list of the current user's populated categories."""

    categories: list[WardrobeCategorySummary]


class SaveRecommendationInput(BaseModel):
    """Recommendation candidate to validate before a later history phase."""

    user_request: str = Field(min_length=1, max_length=500)
    item_ids: list[int] = Field(min_length=1, max_length=15)
    explanation: str = Field(min_length=1, max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("user_request", "explanation")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("item_ids")
    @classmethod
    def validate_item_ids(cls, value: list[int]) -> list[int]:
        if any(item_id < 1 for item_id in value):
            raise ValueError("item IDs must be positive")
        if len(value) != len(set(value)):
            raise ValueError("item IDs must be unique")
        return value


class SaveRecommendationOutput(BaseModel):
    """An ownership-validated recommendation accepted by the tool layer."""

    status: Literal["accepted"] = "accepted"
    user_request: str
    items: list[ToolClothingItem]
    explanation: str
    persisted: Literal[False] = False

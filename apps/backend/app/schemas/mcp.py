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


class StylingCandidateGroup(BaseModel):
    """A deliberately small group of owned items in one clothing category."""

    category: ClothingCategory
    items: list[ToolClothingItem]


class GetStylingCandidatesInput(BaseModel):
    """One high-level wardrobe retrieval request for a stylist run."""

    user_request: str = Field(min_length=1, max_length=500)
    required_categories: list[ClothingCategory] = Field(max_length=7)
    anchor_item_id: int | None = Field(default=None, ge=1)
    limit_per_category: int = Field(default=3, ge=1, le=5)

    model_config = ConfigDict(extra="forbid")

    @field_validator("user_request")
    @classmethod
    def normalize_user_request(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("required_categories")
    @classmethod
    def required_categories_must_be_unique(
        cls, value: list[ClothingCategory]
    ) -> list[ClothingCategory]:
        if len(value) != len(set(value)):
            raise ValueError("required categories must be unique")
        return value


class GetStylingCandidatesOutput(BaseModel):
    """Cached wardrobe evidence returned by one MCP retrieval call."""

    anchor_item: ToolClothingItem | None
    owned_item_ids: list[int]
    candidates_by_category: list[StylingCandidateGroup]
    missing_required_categories: list[ClothingCategory]

    @property
    def candidate_items(self) -> list[ToolClothingItem]:
        """Flatten the compact groups for validation and repair prompts."""

        return [
            item
            for group in self.candidates_by_category
            for item in group.items
        ]


class SaveRecommendationInput(BaseModel):
    """A fully validated recommendation ready for MCP persistence."""

    user_request: str = Field(min_length=1, max_length=500)
    item_ids: list[int] = Field(max_length=15)
    explanation: str = Field(min_length=1, max_length=1200)
    evaluation_score: float = Field(ge=0, le=10)

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
    """A final recommendation persisted through the MCP boundary."""

    status: Literal["accepted"] = "accepted"
    user_request: str
    items: list[ToolClothingItem]
    explanation: str
    recommendation_id: int = Field(ge=1)
    persisted: Literal[True] = True

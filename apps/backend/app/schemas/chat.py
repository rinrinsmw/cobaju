"""One stable response shape for every stylist chat outcome."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.clothing_item import ClothingCategory


class ChatRequest(BaseModel):
    """Authenticated stylist request supplied by the frontend."""

    message: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


class ChatScopeDecision(BaseModel):
    """Low-temperature classification result produced before the stylist runs."""

    allowed: bool
    reason: Literal["fashion_request", "out_of_scope", "unsafe", "prompt_injection"]

    model_config = ConfigDict(extra="forbid")


class RequiredCategory(BaseModel):
    """One clothing category needed to satisfy the user's request."""

    category: ClothingCategory
    reason: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid")


class RecommendedOwnedItem(BaseModel):
    """A selected owned item whose ID was accepted by the wardrobe MCP server."""

    item_id: int = Field(ge=1)
    category: ClothingCategory
    reason: str = Field(min_length=1, max_length=300)

    model_config = ConfigDict(extra="forbid")


class MissingCategoryGuidance(BaseModel):
    """Generic guidance that is explicitly not represented as an owned item."""

    category: ClothingCategory
    guidance: str = Field(min_length=1, max_length=300)

    model_config = ConfigDict(extra="forbid")


class StylistResponse(BaseModel):
    """The stable response schema returned by the stylist chat endpoint."""

    status: Literal["recommendation", "redirected", "rejected"]
    message: str = Field(min_length=1, max_length=1200)
    required_categories: list[RequiredCategory] = Field(max_length=7)
    owned_items: list[RecommendedOwnedItem] = Field(max_length=15)
    missing_categories: list[MissingCategoryGuidance] = Field(max_length=7)

    model_config = ConfigDict(extra="forbid")

    @field_validator("owned_items")
    @classmethod
    def owned_item_ids_must_be_unique(
        cls, value: list[RecommendedOwnedItem]
    ) -> list[RecommendedOwnedItem]:
        item_ids = [item.item_id for item in value]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("owned item IDs must be unique")
        return value


class StylistApiResponse(StylistResponse):
    """A validated stylist response with an opaque receipt for optional saving."""

    lookbook_save_token: str | None = None


class StyleCriticEvaluation(BaseModel):
    """Structured feedback returned only to the Stylist workflow."""

    approved: bool
    issues: list[str] = Field(max_length=10)
    repair_instruction: str = Field(max_length=600)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def verdict_fields_must_be_consistent(self) -> "StyleCriticEvaluation":
        self.issues = [issue.strip() for issue in self.issues if issue.strip()]
        self.repair_instruction = self.repair_instruction.strip()
        if self.approved and (self.issues or self.repair_instruction):
            raise ValueError(
                "approved critic output must have no issues or repair instruction"
            )
        if not self.approved and (not self.issues or not self.repair_instruction):
            raise ValueError(
                "rejected critic output needs issues and a repair instruction"
            )
        return self

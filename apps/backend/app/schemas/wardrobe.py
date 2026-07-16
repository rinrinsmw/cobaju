"""Typed request and response bodies for wardrobe endpoints."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.clothing_item import ClothingCategory, ProcessingStatus


class ClothingItemFields(BaseModel):
    """User-editable clothing metadata shared by create and read schemas."""

    name: str = Field(min_length=1, max_length=100)
    category: ClothingCategory
    color: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "color")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        """Trim required text and reject values containing only whitespace."""

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("category")
    @classmethod
    def reject_null_category(
        cls,
        value: ClothingCategory | None,
    ) -> ClothingCategory:
        if value is None:
            raise ValueError("must not be null")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        """Store an omitted or whitespace-only description as null."""

        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ClothingItemCreate(ClothingItemFields):
    """Metadata accepted when a user manually creates an item."""


class ClothingItemUpdate(BaseModel):
    """Editable fields accepted by the partial update endpoint."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    category: ClothingCategory | None = None
    color: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "color")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("must not be null")
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("category")
    @classmethod
    def reject_null_category(
        cls,
        value: ClothingCategory | None,
    ) -> ClothingCategory:
        if value is None:
            raise ValueError("must not be null")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ClothingItemRead(ClothingItemFields):
    """Safe wardrobe item data returned to its owner."""

    id: int
    original_image_path: str | None
    analysis_completed: bool
    processing_status: ProcessingStatus


class ClothingGuardrailResult(BaseModel):
    """Strict result returned by the inexpensive clothing guardrail."""

    is_clothing: bool
    reason: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid")


class ClothingMetadata(ClothingItemFields):
    """Stable, editable metadata generated only from visible image evidence."""

    # Strict structured-output providers require every property to be present.
    # The model may still return null when no supported description is visible.
    description: str | None = Field(max_length=500)

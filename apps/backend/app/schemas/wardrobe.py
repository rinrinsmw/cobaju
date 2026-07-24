"""Typed request and response bodies for wardrobe endpoints."""

from enum import StrEnum

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


class ClothingUploadRead(ClothingItemRead):
    """New-upload response with an authenticated asynchronous polling receipt."""

    analysis_token: str


class ClothingProcessingStatusRead(BaseModel):
    """Small polling response for one authenticated user's analysis job."""

    item_id: int
    status: ProcessingStatus
    analysis_completed: bool
    needs_confirmation: bool


class WardrobeSearchResultRead(ClothingItemFields):
    """Safe metadata and similarity distance for one wardrobe match."""

    item_id: int
    distance: float


class ClothingGuardrailDecision(StrEnum):
    """The only outcomes the upload guardrail may return."""

    VALID_GARMENT_PHOTO = "valid_garment_photo"
    INVALID_IMAGE = "invalid_image"
    UNCERTAIN = "uncertain"


class ImageMedium(StrEnum):
    """Whether the upload is a photograph rather than artwork or a screenshot."""

    REAL_PHOTOGRAPH = "real_photograph"
    NON_PHOTOGRAPHIC = "non_photographic"
    UNCERTAIN = "uncertain"


class ImagePrimarySubject(StrEnum):
    """The visually dominant subject, independent of visible clothing."""

    PHYSICAL_GARMENT = "physical_garment"
    PERSON_OR_FACE = "person_or_face"
    MULTIPLE_OR_UNRELATED = "multiple_or_unrelated"
    UNCERTAIN = "uncertain"


class GarmentVisibility(StrEnum):
    """Whether one physical garment can be identified from visible evidence."""

    CLEAR = "clear"
    UNCLEAR = "unclear"
    NOT_APPLICABLE = "not_applicable"


class ClothingGuardrailResult(BaseModel):
    """Strict photographic-garment decision returned by the guardrail."""

    decision: ClothingGuardrailDecision
    image_medium: ImageMedium
    primary_subject: ImagePrimarySubject
    garment_visibility: GarmentVisibility
    reason: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid")

    @property
    def allows_metadata_extraction(self) -> bool:
        """Require consistent evidence in addition to the model's decision."""

        return (
            self.decision == ClothingGuardrailDecision.VALID_GARMENT_PHOTO
            and self.image_medium == ImageMedium.REAL_PHOTOGRAPH
            and self.primary_subject == ImagePrimarySubject.PHYSICAL_GARMENT
            and self.garment_visibility == GarmentVisibility.CLEAR
        )


class ClothingMetadata(ClothingItemFields):
    """Stable, editable metadata generated only from visible image evidence."""

    # Strict structured-output providers require every property to be present.
    # The model may still return null when no supported description is visible.
    description: str | None = Field(max_length=500)

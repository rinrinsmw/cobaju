"""Synchronous clothing guardrail, vision analysis, and tracing workflow."""

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol

from sqlmodel import Session

from app.core.config import Settings
from app.models.clothing_item import ClothingItem, ProcessingStatus
from app.observability import Observability
from app.schemas.wardrobe import (
    ClothingGuardrailDecision,
    ClothingGuardrailResult,
    ClothingMetadata,
)
from app.services.wardrobe import (
    mark_item_processing,
    save_generated_metadata,
)


class ClothingAnalysisError(Exception):
    """Base error for safe clothing-analysis failures."""


class ClothingVisionProvider(Protocol):
    """Small boundary that lets tests replace paid AI calls with a fake."""

    def classify_image(self, image_path: Path) -> ClothingGuardrailResult: ...

    def analyze_image(self, image_path: Path) -> ClothingMetadata: ...


class ClothingAnalysisTracer:
    """Compatibility wrapper around the shared observability abstraction."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._observability = Observability(settings)

    def observation(
        self,
        name: str,
        *,
        as_type: str = "span",
        **attributes: Any,
    ) -> AbstractContextManager[Any]:
        return self._observability.observe(name, as_type=as_type, **attributes)


def analyze_clothing_item(
    session: Session,
    item: ClothingItem,
    image_path: Path,
    provider: ClothingVisionProvider,
    settings: Settings,
) -> tuple[ClothingItem, ClothingGuardrailDecision | None]:
    """Run guardrail then metadata analysis and persist a reviewable draft.

    The returned optional decision identifies a terminal content rejection. The
    worker owns storage and database cleanup so it can keep those operations
    ordered and retryable.
    """

    tracer = ClothingAnalysisTracer(settings)
    # The API normally claims the item before it sends the Celery message.
    # Keeping this fallback makes the Phase 5 service independently usable in
    # unit tests and other trusted Python callers.
    if item.processing_status != ProcessingStatus.PROCESSING:
        mark_item_processing(session, item)

    try:
        with tracer.observation(
            "clothing_analysis",
            input={"item_id": item.id, "user_id": item.user_id},
        ):
            with tracer.observation(
                "upload_guardrail",
                as_type="generation",
                model=settings.openrouter_guardrail_model,
                model_parameters={"temperature": settings.guardrail_temperature},
            ):
                guardrail = provider.classify_image(image_path)

            if not guardrail.allows_metadata_extraction:
                rejection = guardrail.decision
                if rejection == ClothingGuardrailDecision.VALID_GARMENT_PHOTO:
                    rejection = ClothingGuardrailDecision.INVALID_IMAGE
                return item, rejection

            with tracer.observation(
                "vision_analysis",
                as_type="generation",
                model=settings.openrouter_vision_model,
                model_parameters={"temperature": settings.vision_temperature},
            ):
                metadata = provider.analyze_image(image_path)

            with tracer.observation("metadata_validation"):
                validated_metadata = ClothingMetadata.model_validate(metadata)

            return save_generated_metadata(session, item, validated_metadata), None
    except Exception as error:
        if isinstance(error, ClothingAnalysisError):
            raise
        raise ClothingAnalysisError("Clothing analysis failed") from error

"""Synchronous clothing guardrail, vision analysis, and tracing workflow."""

from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any, Protocol

from sqlmodel import Session

from app.core.config import Settings
from app.models.clothing_item import ClothingItem, ProcessingStatus
from app.schemas.wardrobe import ClothingGuardrailResult, ClothingMetadata
from app.services.wardrobe import (
    mark_item_failed,
    mark_item_processing,
    reject_item_image,
    save_generated_metadata,
)


class ClothingAnalysisError(Exception):
    """Base error for safe clothing-analysis failures."""


class ClothingVisionProvider(Protocol):
    """Small boundary that lets tests replace paid AI calls with a fake."""

    def classify_image(self, image_path: Path) -> ClothingGuardrailResult: ...

    def analyze_image(self, image_path: Path) -> ClothingMetadata: ...


class ClothingAnalysisTracer:
    """Create Langfuse observations only when telemetry is explicitly enabled."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any | None = None

    def observation(
        self,
        name: str,
        *,
        as_type: str = "span",
        **attributes: Any,
    ) -> AbstractContextManager[Any]:
        if not self.settings.langfuse_enabled:
            return nullcontext()
        if self._client is None:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=self.settings.langfuse_public_key,
                secret_key=self.settings.langfuse_secret_key.get_secret_value(),
                base_url=self.settings.langfuse_base_url,
            )
        return self._client.start_as_current_observation(
            as_type=as_type,
            name=name,
            **attributes,
        )


def analyze_clothing_item(
    session: Session,
    item: ClothingItem,
    image_path: Path,
    provider: ClothingVisionProvider,
    settings: Settings,
) -> tuple[ClothingItem, str | None]:
    """Run guardrail then metadata analysis and persist a reviewable draft.

    The returned optional path is the rejected file that the route must delete
    after its database reference has safely been cleared.
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

            if not guardrail.is_clothing:
                return item, reject_item_image(session, item)

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
        mark_item_failed(session, item)
        if isinstance(error, ClothingAnalysisError):
            raise
        raise ClothingAnalysisError("Clothing analysis failed") from error

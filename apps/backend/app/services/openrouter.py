"""Minimal OpenRouter vision client with strict structured outputs."""

import base64
import json
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.schemas.wardrobe import (
    ClothingMetadata,
    GarmentSubjectGuardrailResult,
    ImageMediumGuardrailResult,
)
from app.services.clothing_analysis import ClothingAnalysisError


SchemaType = TypeVar("SchemaType", bound=BaseModel)


class OpenRouterConfigurationError(ClothingAnalysisError):
    """Raised when required OpenRouter settings are missing."""


class OpenRouterResponseError(ClothingAnalysisError):
    """Raised when OpenRouter fails or returns invalid structured data."""


class OpenRouterVisionProvider:
    """Call independently scoped vision tasks through OpenRouter."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def classify_image_medium(
        self,
        image_path: Path,
    ) -> ImageMediumGuardrailResult:
        prompt = (
            "Perform only the image-medium gate. Do not identify clothing, infer a "
            "garment category, or decide whether the upload belongs in a wardrobe. "
            "Classify the depicted visual content, not merely the file format. Use "
            "real_photograph only when the visible scene and its relevant subjects "
            "are real physical objects captured by a camera. Use non_photographic "
            "for cartoons, illustrations, vector drawings, paintings, anime, memes, "
            "posters, screenshots, generated artwork, 3D renders, product drawings, "
            "and photographs or screenshots whose relevant depicted subject is "
            "artwork. A drawn person wearing a realistic white button-up shirt is "
            "non_photographic. Use uncertain whenever photographic authenticity "
            "cannot be judged confidently. When in doubt between real_photograph "
            "and uncertain, choose uncertain. Explain only visible evidence."
        )
        return self._request(
            image_path=image_path,
            model=self.settings.openrouter_guardrail_model,
            temperature=self.settings.guardrail_temperature,
            prompt=prompt,
            schema=ImageMediumGuardrailResult,
            schema_name="image_medium_guardrail",
        )

    def classify_garment_subject(
        self,
        image_path: Path,
    ) -> GarmentSubjectGuardrailResult:
        prompt = (
            "Perform only the garment-subject gate. Identify the visually dominant "
            "primary subject of the whole composition, not the most recognizable "
            "clothing category. Use physical_garment only when one real garment, "
            "shoe, bag, or fashion accessory is presented as the main standalone "
            "subject, such as laid flat, on a hanger, or in a product-style photo. "
            "Use person_or_face whenever a visible person, face, body, pose, or "
            "activity is the main composition, even if their clothing is large, "
            "clear, and easy to describe. Do not classify a shirt worn by the main "
            "person as physical_garment. Use multiple_or_unrelated for multiple "
            "competing items, unsafe content, or an unrelated main subject. Use "
            "uncertain whenever the dominant subject cannot be judged confidently. "
            "Set garment_visibility to clear only when the standalone physical "
            "garment is sufficiently visible to identify category and colour; "
            "otherwise use unclear or not_applicable. Explain only visible evidence."
        )
        return self._request(
            image_path=image_path,
            model=self.settings.openrouter_guardrail_model,
            temperature=self.settings.guardrail_temperature,
            prompt=prompt,
            schema=GarmentSubjectGuardrailResult,
            schema_name="garment_subject_guardrail",
        )

    def analyze_image(self, image_path: Path) -> ClothingMetadata:
        prompt = (
            "Describe only the single visible fashion item. Produce concise, "
            "editable wardrobe metadata. Use only visible evidence; do not infer "
            "brand, exact fabric, ownership, price, condition, or other unsupported "
            "claims. The category must be one of the schema values."
        )
        return self._request(
            image_path=image_path,
            model=self.settings.openrouter_vision_model,
            temperature=self.settings.vision_temperature,
            prompt=prompt,
            schema=ClothingMetadata,
            schema_name="clothing_metadata",
        )

    def _request(
        self,
        *,
        image_path: Path,
        model: str,
        temperature: float,
        prompt: str,
        schema: type[SchemaType],
        schema_name: str,
    ) -> SchemaType:
        api_key = self.settings.openrouter_api_key.get_secret_value()
        if not api_key or not model:
            raise OpenRouterConfigurationError(
                "OpenRouter API key and model settings are required"
            )

        image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
        media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(image_path.suffix.lower())
        if media_type is None:
            raise OpenRouterResponseError("Unsupported stored image format")

        payload = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_data}"
                            },
                        },
                    ],
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            },
            "provider": {"require_parameters": True},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": self.settings.app_name,
        }

        try:
            response = httpx.post(
                f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.settings.openrouter_timeout_seconds,
            )
            response.raise_for_status()
            response_body: dict[str, Any] = response.json()
            content = response_body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("message content is not text")
            return schema.model_validate(json.loads(content))
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise OpenRouterResponseError("OpenRouter returned an invalid response") from error

"""Minimal OpenRouter vision client with strict structured outputs."""

import base64
import json
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.schemas.wardrobe import ClothingGuardrailResult, ClothingMetadata
from app.services.clothing_analysis import ClothingAnalysisError


SchemaType = TypeVar("SchemaType", bound=BaseModel)


class OpenRouterConfigurationError(ClothingAnalysisError):
    """Raised when required OpenRouter settings are missing."""


class OpenRouterResponseError(ClothingAnalysisError):
    """Raised when OpenRouter fails or returns invalid structured data."""


class OpenRouterVisionProvider:
    """Call two independently configured vision tasks through OpenRouter."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def classify_image(self, image_path: Path) -> ClothingGuardrailResult:
        prompt = (
            "Decide whether this image contains exactly one clearly visible main "
            "clothing, footwear, bag, or fashion-accessory item. Reject selfies, "
            "people wearing an outfit, multiple main items, food, pets, documents, "
            "screenshots, furniture, unsafe content, and unclear images. Base the "
            "decision only on visible evidence."
        )
        return self._request(
            image_path=image_path,
            model=self.settings.openrouter_guardrail_model,
            temperature=self.settings.guardrail_temperature,
            prompt=prompt,
            schema=ClothingGuardrailResult,
            schema_name="clothing_guardrail",
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

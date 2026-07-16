"""Phase 9 chat workflow: guard, run one stylist, and ground ownership."""

from contextlib import AbstractContextManager, nullcontext
from typing import Any

from app.core.config import Settings
from app.models.user import User
from app.schemas.chat import ChatScopeDecision, StylistResponse
from app.services.chat_guardrails import (
    ChatScopeClassifier,
    contains_prompt_injection,
)
from app.services.stylist_agent import StylistAgentError, StylistRunner


class StylistGroundingError(StylistAgentError):
    """Raised when the final owned IDs are not backed by wardrobe tool output."""


class RecommendationTracer:
    """Create the Phase 9 Langfuse trace only when explicitly enabled."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any | None = None

    def observation(
        self, name: str, *, as_type: str = "span", **attributes: Any
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
            as_type=as_type, name=name, **attributes
        )


def _blocked_response(decision: ChatScopeDecision) -> StylistResponse:
    if decision.reason == "out_of_scope":
        return StylistResponse(
            status="redirected",
            message=(
                "I can help with your wardrobe, outfit combinations, and style or "
                "occasion questions. Please ask a fashion-related question."
            ),
            required_categories=[],
            owned_items=[],
            missing_categories=[],
        )
    return StylistResponse(
        status="rejected",
        message="I can’t follow that request. I can still help with a normal wardrobe or outfit question.",
        required_categories=[],
        owned_items=[],
        missing_categories=[],
    )


async def create_stylist_response(
    *,
    message: str,
    current_user: User,
    classifier: ChatScopeClassifier,
    runner: StylistRunner,
    settings: Settings,
) -> StylistResponse:
    """Return a scoped response without trusting model-created ownership claims."""

    tracer = RecommendationTracer(settings)
    with tracer.observation(
        "outfit_recommendation",
        input={"user_id": current_user.id, "message_length": len(message)},
    ):
        with tracer.observation(
            "input_guardrail",
            as_type="generation",
            model=settings.openrouter_chat_guardrail_model,
            model_parameters={"temperature": settings.chat_guardrail_temperature},
        ):
            if contains_prompt_injection(message):
                return _blocked_response(
                    ChatScopeDecision(allowed=False, reason="prompt_injection")
                )
            decision = await classifier.classify(message)

        if not decision.allowed:
            return _blocked_response(decision)

        with tracer.observation(
            "stylist_generation",
            as_type="generation",
            model=settings.openrouter_stylist_model,
            model_parameters={"temperature": settings.stylist_temperature},
        ):
            outcome = await runner.run(message, current_user)

        if outcome.response.status != "recommendation":
            raise StylistGroundingError("Stylist returned the wrong response status")
        if not outcome.response.required_categories:
            raise StylistGroundingError("Stylist did not plan required categories")

        if not any(
            name in {"search_wardrobe", "get_clothing_item", "list_wardrobe_categories"}
            for name in outcome.tool_names
        ):
            raise StylistGroundingError("Stylist did not inspect the wardrobe")

        returned_ids = {item.item_id for item in outcome.response.owned_items}
        if returned_ids:
            if "save_recommendation" not in outcome.tool_names:
                raise StylistGroundingError("Recommendation was not ownership-checked")
            if returned_ids != outcome.validated_item_ids:
                raise StylistGroundingError("Recommendation item IDs were not validated")
        elif outcome.validated_item_ids:
            raise StylistGroundingError("Validated items were omitted from the response")

        return outcome.response

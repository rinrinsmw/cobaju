"""Guard, generate, evaluate, and deterministically validate recommendations."""

from contextlib import AbstractContextManager, nullcontext
from typing import Any

from sqlmodel import Session

from app.core.config import Settings
from app.models.user import User
from app.schemas.chat import ChatScopeDecision, OutfitEvaluation, StylistResponse
from app.services.chat_guardrails import (
    ChatScopeClassifier,
    contains_prompt_injection,
)
from app.services.outfit_evaluator import (
    OutfitEvaluator,
    RecommendationValidationError,
    get_owned_item_evidence,
    validate_recommendation,
)
from app.services.stylist_agent import StylistRunOutcome, StylistRunner


# Compatibility name retained for callers of the Phase 9 service boundary.
StylistGroundingError = RecommendationValidationError


class RecommendationTracer:
    """Create the recommendation Langfuse trace only when explicitly enabled."""

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
    evaluator: OutfitEvaluator,
    session: Session,
    settings: Settings,
) -> StylistResponse:
    """Return only a scoped recommendation accepted by both validation layers."""

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

        retry_feedback: str | None = None
        for attempt in range(2):
            with tracer.observation(
                "stylist_generation",
                as_type="generation",
                model=settings.openrouter_stylist_model,
                model_parameters={"temperature": settings.stylist_temperature},
                metadata={"attempt": attempt + 1},
            ):
                outcome = await runner.run(message, current_user, retry_feedback)

            grounding_violations = _grounding_violations(outcome)
            evidence = get_owned_item_evidence(
                session, current_user.id, outcome.response
            )
            with tracer.observation(
                "evaluator",
                as_type="generation",
                model=settings.openrouter_evaluator_model,
                model_parameters={"temperature": settings.evaluator_temperature},
                metadata={"attempt": attempt + 1},
            ):
                evaluation = await evaluator.evaluate(
                    message, outcome.response, evidence
                )
            evaluator_violations = _evaluator_violations(evaluation)
            deterministic = validate_recommendation(outcome.response, evidence)
            violations = (
                grounding_violations
                + evaluator_violations
                + deterministic.violations
            )
            hallucination_detected = bool(
                evaluation.unsupported_claims or deterministic.violations
            )
            with tracer.observation(
                "deterministic_validation",
                input={"candidate_item_count": len(outcome.response.owned_items)},
                output={
                    "accepted": not violations,
                    "violations": violations,
                    "hallucination_detected": hallucination_detected,
                },
                metadata={"attempt": attempt + 1},
            ):
                pass

            if not violations:
                with tracer.observation(
                    "final_response",
                    output={
                        "status": outcome.response.status,
                        "retry_count": attempt,
                        "hallucination_detected": False,
                    },
                ):
                    return outcome.response

            retry_feedback = " ".join(violations)

        raise RecommendationValidationError(
            "Recommendation remained invalid after one retry"
        )


def _grounding_violations(outcome: StylistRunOutcome) -> list[str]:
    """Turn Phase 9 grounding rules into retryable validation feedback."""

    violations: list[str] = []
    if outcome.response.status != "recommendation":
        violations.append("Return a recommendation response.")
    if not outcome.response.required_categories:
        violations.append("Plan at least one required clothing category.")
    if not any(
        name in {"search_wardrobe", "get_clothing_item", "list_wardrobe_categories"}
        for name in outcome.tool_names
    ):
        violations.append("Inspect the wardrobe with a wardrobe tool.")

    returned_ids = {item.item_id for item in outcome.response.owned_items}
    if returned_ids and "save_recommendation" not in outcome.tool_names:
        violations.append("Validate selected IDs with save_recommendation.")
    if returned_ids != outcome.validated_item_ids:
        violations.append("Return exactly the item IDs accepted by save_recommendation.")
    return violations


def _evaluator_violations(evaluation: OutfitEvaluation) -> list[str]:
    """Do not trust an evaluator's accepted flag when any detailed check fails."""

    failures: list[str] = []
    checks = {
        "occasion relevance": evaluation.occasion_appropriate,
        "outfit completeness": evaluation.complete,
        "color compatibility": evaluation.colors_compatible,
        "style compatibility": evaluation.styles_compatible,
    }
    failures.extend(
        f"Evaluator rejected {name}."
        for name, passed in checks.items()
        if not passed
    )
    failures.extend(
        f"Unsupported claim: {claim}" for claim in evaluation.unsupported_claims
    )
    if not evaluation.accepted and not failures:
        failures.append(f"Evaluator rejected the candidate: {evaluation.feedback}")
    if evaluation.accepted and failures:
        failures.append("Evaluator verdict was internally inconsistent.")
    return failures

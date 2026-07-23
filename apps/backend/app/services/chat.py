"""Guard, retrieve once through MCP, generate, validate, and prepare optional saving."""

from collections import Counter
from contextlib import nullcontext

from app.core.config import Settings
from app.core.security import create_recommendation_save_token
from app.models.clothing_item import ClothingItem
from app.models.user import User
from app.observability import (
    Observation,
    Observability,
    current_request_context,
    get_observability,
    record_recommendation_diagnostics,
    set_failing_stage,
    structured_log,
)
from app.schemas.chat import (
    ChatScopeDecision,
    OutfitEvaluation,
    StylistApiResponse,
    StylistResponse,
)
from app.services.chat_guardrails import ChatScopeClassifier, contains_prompt_injection
from app.services.outfit_evaluator import (
    OutfitEvaluator,
    RecommendationValidationError,
    evaluate_recommendation_quality,
    validate_recommendation,
)
from app.services.stylist_agent import StylistRunOutcome, StylistRunner


StylistGroundingError = RecommendationValidationError


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
    settings: Settings,
    observability: Observability | None = None,
) -> StylistResponse:
    """Return a deterministically valid recommendation without persisting it."""

    telemetry = observability or get_observability()
    request_context = current_request_context()
    existing_root = request_context.root_observation if request_context else None
    request_scope = (
        nullcontext(existing_root)
        if existing_root is not None
        else telemetry.observe(
            "stylist_request",
            as_type="agent",
            input={"message_length": len(message)},
            metadata={"prompt_version": settings.stylist_prompt_version},
        )
    )
    with request_scope as request_observation:
        with telemetry.observe(
            "guardrail.validate",
            as_type="generation",
            model=settings.openrouter_chat_guardrail_model,
            model_parameters={"temperature": settings.chat_guardrail_temperature},
            metadata={"prompt_version": settings.chat_guardrail_prompt_version},
        ):
            set_failing_stage("guardrail.validate")
            if contains_prompt_injection(message):
                return _blocked_response(
                    ChatScopeDecision(allowed=False, reason="prompt_injection")
                )
            decision = await classifier.classify(message)

        if not decision.allowed:
            return _blocked_response(decision)

        # The session context encloses generation, optional repair, final
        # validation. It is entered exactly once.
        async with runner.open_request(current_user) as stylist_request:
            set_failing_stage("stylist.generate")
            outcome = await stylist_request.run(message)
            structured_log(
                "stylist_initial_recommendation",
                recommendation=_recommendation_log_payload(outcome.response),
            )

            tool_counts = Counter(outcome.tool_invocation_counts)
            last_hallucination_detected = False
            last_validation_result: dict[str, object] = {}

            for attempt in range(2):
                evidence = _cached_item_evidence(outcome, current_user)
                grounding_violations = _grounding_violations(outcome)
                deterministic = validate_recommendation(outcome.response, evidence)
                violations = grounding_violations + deterministic.violations
                validation_failure_codes = _failure_codes(violations)
                record_recommendation_diagnostics(
                    validation_failures=validation_failure_codes,
                    evaluator_failures=[],
                    evaluator_scores={},
                )

                with telemetry.observe(
                    "recommendation.validate",
                    input={"candidate_item_count": len(outcome.response.owned_items)},
                    output={
                        "accepted": not violations,
                        "violations": violations,
                        "hallucination_detected": bool(violations),
                    },
                    metadata={
                        "attempt": attempt + 1,
                        "candidate_source": "generation" if attempt == 0 else "repair",
                    },
                ):
                    pass

                evaluation: OutfitEvaluation | None = None
                quality = None
                if not violations:
                    with telemetry.observe(
                        "evaluator",
                        as_type="generation",
                        model=settings.openrouter_evaluator_model,
                        model_parameters={"temperature": settings.evaluator_temperature},
                        metadata={
                            "attempt": attempt + 1,
                            "prompt_version": settings.evaluator_prompt_version,
                        },
                    ):
                        set_failing_stage("evaluator")
                        evaluation = await evaluator.evaluate(
                            message, outcome.response, evidence
                        )
                    evaluator_failures = _evaluator_failure_codes(evaluation)
                    # Evaluator quality judgments are observability signals, not
                    # a second authority for rules already checked in Python.
                    # A verified unsupported claim remains blocking because the
                    # deterministic validator does not inspect prose semantics.
                    violations = _blocking_evaluator_failure_codes(evaluation)
                    record_recommendation_diagnostics(
                        validation_failures=[],
                        evaluator_failures=evaluator_failures,
                        evaluator_scores=_sanitized_evaluator_scores(evaluation),
                    )
                    quality = evaluate_recommendation_quality(
                        outcome.response, evaluation, deterministic
                    )
                    if request_observation is not None:
                        _record_evaluator_scores(
                            request_observation, evaluation, quality.explanation_present
                        )

                last_validation_result = {
                    "accepted": not violations,
                    "grounding_violations": grounding_violations,
                    "deterministic_violations": deterministic.violations,
                    "evaluator_violations": (
                        _evaluator_failure_codes(evaluation) if evaluation else []
                    ),
                    "blocking_evaluator_violations": (
                        _blocking_evaluator_failure_codes(evaluation)
                        if evaluation
                        else []
                    ),
                    "evaluator_result": (
                        evaluation.model_dump(mode="json") if evaluation else None
                    ),
                    "final_blocking_violations": violations,
                    "evidence_item_ids": [
                        item.id for item in evidence if item.id is not None
                    ],
                }

                last_hallucination_detected = bool(
                    deterministic.violations
                    or grounding_violations
                    or (evaluation and evaluation.unsupported_claims)
                )
                if not violations:
                    if evaluation is None or quality is None:
                        raise RecommendationValidationError(
                            "Recommendation was not evaluated"
                        )
                    if current_user.id is None:
                        raise RecommendationValidationError(
                            "Authenticated user has no persisted ID"
                        )

                    record_recommendation_diagnostics(
                        tool_call_count=sum(tool_counts.values())
                    )

                    metrics = stylist_request.metrics.as_dict()
                    if request_observation is not None:
                        request_observation.score_trace(
                            name="hallucination_detected", value="false"
                        )
                        request_observation.update(
                            output={
                                "status": outcome.response.status,
                                "retry_count": attempt,
                                "repair_count": attempt,
                                "tool_invocation_counts": dict(tool_counts),
                                "validation_failures": [],
                                "evaluator_failures": evaluator_failures,
                                "evaluator_nonblocking": bool(evaluator_failures),
                                "evaluator_scores": _sanitized_evaluator_scores(
                                    evaluation
                                ),
                                **metrics,
                            }
                        )
                    with telemetry.observe(
                        "response_formatting",
                        output={
                            "status": outcome.response.status,
                            "retry_count": attempt,
                            "repair_count": attempt,
                            "hallucination_detected": False,
                            "evaluation_score": evaluation.evaluation_score,
                            "tool_invocation_counts": dict(tool_counts),
                            "validation_failures": [],
                            "evaluator_failures": evaluator_failures,
                            "evaluator_nonblocking": bool(evaluator_failures),
                            "evaluator_scores": _sanitized_evaluator_scores(evaluation),
                            "quality": quality.as_dict(),
                            **metrics,
                        },
                    ):
                        return StylistApiResponse(
                            **outcome.response.model_dump(),
                            lookbook_save_token=create_recommendation_save_token(
                                user_id=current_user.id,
                                user_request=message,
                                item_ids=[
                                    item.item_id
                                    for item in outcome.response.owned_items
                                ],
                                explanation=outcome.response.message,
                                evaluation_score=evaluation.evaluation_score,
                            ),
                        )

                if attempt == 0:
                    repair_violations = list(violations)
                    if evaluation is not None and evaluation.unsupported_claims:
                        repair_violations.extend(
                            f"UNSUPPORTED_CLAIM: {claim}"
                            for claim in evaluation.unsupported_claims
                        )
                        if evaluation.feedback:
                            repair_violations.append(
                                f"EVALUATOR_FEEDBACK: {evaluation.feedback}"
                            )
                    with telemetry.observe(
                        "recommendation.repair",
                        as_type="generation",
                        input={
                            "violation_count": len(violations),
                            "candidate_count": len(outcome.available_items),
                            "cache_reused": True,
                        },
                        model=settings.openrouter_stylist_model,
                        model_parameters={
                            "temperature": settings.stylist_repair_temperature
                        },
                        metadata={
                            "prompt_version": settings.stylist_repair_prompt_version,
                        },
                    ):
                        set_failing_stage("recommendation.repair")
                        repaired = await stylist_request.repair(
                            message, outcome.response, repair_violations
                        )
                    structured_log(
                        "stylist_repaired_recommendation",
                        recommendation=_recommendation_log_payload(repaired),
                    )
                    outcome.response = repaired

            if request_observation is not None:
                request_observation.score_trace(
                    name="hallucination_detected",
                    value="true" if last_hallucination_detected else "false",
                )
                request_observation.update(output=stylist_request.metrics.as_dict())
            structured_log(
                "stylist_recommendation_validation_failed",
                recommendation=_recommendation_log_payload(outcome.response),
                validation=last_validation_result,
            )
            raise RecommendationValidationError(
                "Recommendation remained invalid after one targeted repair"
            )


def _recommendation_log_payload(response: StylistResponse) -> dict[str, object]:
    """Return the complete schema-bounded candidate for validation diagnostics."""

    return response.model_dump(mode="json")


def _cached_item_evidence(
    outcome: StylistRunOutcome, current_user: User
) -> list[ClothingItem]:
    """Convert the cached MCP candidates for existing validators/evaluator."""

    if current_user.id is None:
        return []
    selected_ids = {item.item_id for item in outcome.response.owned_items}
    return [
        ClothingItem(
            id=item.item_id,
            user_id=current_user.id,
            name=item.name,
            category=item.category,
            color=item.color,
            description=item.description,
        )
        for item in outcome.available_items
        if item.item_id in selected_ids
    ]


def _grounding_violations(outcome: StylistRunOutcome) -> list[str]:
    """Require one high-level retrieval and selection only from its cache."""

    violations: list[str] = []
    if outcome.response.status != "recommendation":
        violations.append("INVALID_RESPONSE_STATUS")
    if not outcome.response.required_categories:
        violations.append("REQUIRED_CATEGORIES_EMPTY")
    if outcome.tool_names.count("get_styling_candidates") != 1:
        violations.append("MCP_RETRIEVAL_COUNT_INVALID")
    returned_ids = {item.item_id for item in outcome.response.owned_items}
    available_ids = {item.item_id for item in outcome.available_items}
    unavailable_ids = returned_ids - available_ids
    if unavailable_ids:
        violations.append(
            "ITEM_ID_NOT_IN_CACHED_EVIDENCE: "
            f"{sorted(unavailable_ids)}."
        )
    anchor = outcome.candidate_bundle.anchor_item if outcome.candidate_bundle else None
    if anchor is not None and anchor.item_id not in returned_ids:
        violations.append(f"ANCHOR_ITEM_MISSING: {anchor.item_id}.")
    return violations


def _failure_codes(failures: list[str]) -> list[str]:
    """Strip bounded diagnostic details from stable validation codes."""

    return list(dict.fromkeys(failure.split(":", 1)[0] for failure in failures))


def _evaluator_failure_codes(evaluation: OutfitEvaluation) -> list[str]:
    """Return every failed evaluator dimension, including nonblocking quality."""

    checks = {
        "EVALUATOR_OCCASION_RELEVANCE_LOW": evaluation.occasion_appropriate,
        "EVALUATOR_REQUIRED_COMPONENTS_MISSING": evaluation.complete,
        "EVALUATOR_COLOR_COHERENCE_LOW": evaluation.colors_compatible,
        "EVALUATOR_STYLE_COHERENCE_LOW": evaluation.styles_compatible,
    }
    failures = [code for code, passed in checks.items() if not passed]
    if evaluation.unsupported_claims:
        failures.append("EVALUATOR_UNSUPPORTED_CLAIMS")
    if not evaluation.accepted:
        failures.append("EVALUATOR_OVERALL_REJECTED")
    if evaluation.accepted and failures:
        failures.append("EVALUATOR_VERDICT_INCONSISTENT")
    return failures


def _blocking_evaluator_failure_codes(evaluation: OutfitEvaluation) -> list[str]:
    """Block only semantic safety failures not already validated in Python."""

    failures: list[str] = []
    if evaluation.unsupported_claims:
        failures.append("EVALUATOR_UNSUPPORTED_CLAIMS")
    return failures


def _sanitized_evaluator_scores(
    evaluation: OutfitEvaluation,
) -> dict[str, bool | float | int]:
    return {
        "accepted": evaluation.accepted,
        "occasion_appropriate": evaluation.occasion_appropriate,
        "complete": evaluation.complete,
        "colors_compatible": evaluation.colors_compatible,
        "styles_compatible": evaluation.styles_compatible,
        "evaluation_score": evaluation.evaluation_score,
        "unsupported_claim_count": len(evaluation.unsupported_claims),
    }


def _record_evaluator_scores(
    observation: Observation,
    evaluation: OutfitEvaluation,
    explanation_present: bool,
) -> None:
    """Record evaluator quality dimensions without making them HTTP blockers."""

    scores: dict[str, float] = {
        "recommendation_quality": evaluation.evaluation_score / 10,
        "occasion_relevance": float(evaluation.occasion_appropriate),
        "outfit_completeness": float(evaluation.complete),
        "color_coherence": float(evaluation.colors_compatible),
        "style_coherence": float(evaluation.styles_compatible),
        "explanation_present": float(explanation_present),
    }
    for name, value in scores.items():
        observation.score_trace(name=name, value=value)

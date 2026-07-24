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
    StyleCriticEvaluation,
    StylistApiResponse,
    StylistResponse,
)
from app.services.chat_guardrails import ChatScopeClassifier, contains_prompt_injection
from app.services.style_critic import (
    RecommendationValidationError,
    StyleCritic,
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
    evaluator: StyleCritic,
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

        # One request-scoped MCP session encloses generation and at most one
        # repair. The Style Critic itself has no tools.
        async with runner.open_request(current_user) as stylist_request:
            set_failing_stage("stylist_generation")
            outcome = await stylist_request.run(message)
            structured_log(
                "stylist_initial_recommendation",
                recommendation=_recommendation_log_payload(outcome.response),
            )

            tool_counts = Counter(outcome.tool_invocation_counts)
            evidence = _cached_item_evidence(outcome, current_user)
            grounding_violations = _grounding_violations(outcome)
            deterministic = validate_recommendation(outcome.response, evidence)
            violations = grounding_violations + deterministic.violations
            record_recommendation_diagnostics(
                validation_failures=_failure_codes(violations),
                evaluator_failures=[],
                evaluator_scores={},
            )
            with telemetry.observe(
                "deterministic_validation",
                input={"candidate_item_count": len(outcome.response.owned_items)},
                output={
                    "status": "approved" if not violations else "rejected",
                    "failure_reason": _failure_codes(violations),
                },
                metadata={"candidate_source": "generation"},
            ):
                pass

            critic_result: StyleCriticEvaluation | None = None
            repair_reasons = list(violations)
            if not violations:
                with telemetry.observe(
                    "style_critic",
                    as_type="generation",
                    model=settings.resolved_style_critic_model,
                    model_parameters={
                        "temperature": settings.style_critic_temperature
                    },
                    metadata={
                        "prompt_version": (
                            settings.resolved_style_critic_prompt_version
                        ),
                    },
                ) as critic_observation:
                    set_failing_stage("style_critic")
                    try:
                        critic_result = await evaluator.evaluate(
                            message, outcome.response, evidence
                        )
                    except Exception as error:
                        if critic_observation is not None:
                            critic_observation.update(
                                output={
                                    "status": "failed",
                                    "failure_reason": type(error).__name__,
                                }
                            )
                        raise
                    if critic_observation is not None:
                        critic_observation.update(
                            output={
                                "status": (
                                    "approved"
                                    if critic_result.approved
                                    else "rejected"
                                ),
                                "failure_reason": (
                                    None
                                    if critic_result.approved
                                    else "STYLE_CRITIC_REJECTED"
                                ),
                                "issue_count": len(critic_result.issues),
                            }
                        )
                critic_failures = (
                    [] if critic_result.approved else ["STYLE_CRITIC_REJECTED"]
                )
                record_recommendation_diagnostics(
                    validation_failures=[],
                    evaluator_failures=critic_failures,
                    evaluator_scores={
                        "approved": critic_result.approved,
                        "issue_count": len(critic_result.issues),
                    },
                )
                if critic_result.approved:
                    return _finalize_response(
                        message=message,
                        current_user=current_user,
                        response=outcome.response,
                        tool_counts=tool_counts,
                        metrics=stylist_request.metrics.as_dict(),
                        repaired=False,
                        critic_result=critic_result,
                        request_observation=request_observation,
                        telemetry=telemetry,
                    )
                repair_reasons = [
                    *(f"STYLE_CRITIC_ISSUE: {issue}" for issue in critic_result.issues),
                    (
                        "STYLE_CRITIC_REPAIR_INSTRUCTION: "
                        f"{critic_result.repair_instruction}"
                    ),
                ]

            with telemetry.observe(
                "targeted_repair",
                as_type="generation",
                input={
                    "violation_count": len(repair_reasons),
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
            ) as repair_observation:
                set_failing_stage("targeted_repair")
                try:
                    repaired = await stylist_request.repair(
                        message, outcome.response, repair_reasons
                    )
                except Exception as error:
                    if repair_observation is not None:
                        repair_observation.update(
                            output={
                                "status": "failed",
                                "failure_reason": type(error).__name__,
                            }
                        )
                    raise
                if repair_observation is not None:
                    repair_observation.update(
                        output={"status": "completed", "failure_reason": None}
                    )
            structured_log(
                "stylist_repaired_recommendation",
                recommendation=_recommendation_log_payload(repaired),
            )
            outcome.response = repaired

            final_evidence = _cached_item_evidence(outcome, current_user)
            final_grounding = _grounding_violations(outcome)
            final_deterministic = validate_recommendation(
                outcome.response, final_evidence
            )
            final_violations = final_grounding + final_deterministic.violations
            record_recommendation_diagnostics(
                validation_failures=_failure_codes(final_violations),
                tool_call_count=sum(tool_counts.values()),
            )
            with telemetry.observe(
                "final_validation",
                input={"candidate_item_count": len(outcome.response.owned_items)},
                output={
                    "status": "approved" if not final_violations else "rejected",
                    "failure_reason": _failure_codes(final_violations),
                },
                metadata={"candidate_source": "repair"},
            ):
                pass

            if final_violations:
                if request_observation is not None:
                    request_observation.score_trace(
                        name="hallucination_detected", value="true"
                    )
                    request_observation.update(
                        output=stylist_request.metrics.as_dict()
                    )
                structured_log(
                    "stylist_recommendation_validation_failed",
                    recommendation=_recommendation_log_payload(outcome.response),
                    validation={
                        "accepted": False,
                        "grounding_violations": final_grounding,
                        "deterministic_violations": (
                            final_deterministic.violations
                        ),
                        "style_critic_result": (
                            critic_result.model_dump(mode="json")
                            if critic_result
                            else None
                        ),
                        "final_blocking_violations": final_violations,
                        "evidence_item_ids": [
                            item.id
                            for item in final_evidence
                            if item.id is not None
                        ],
                    },
                )
                raise RecommendationValidationError(
                    "Recommendation remained invalid after one targeted repair"
                )

            return _finalize_response(
                message=message,
                current_user=current_user,
                response=outcome.response,
                tool_counts=tool_counts,
                metrics=stylist_request.metrics.as_dict(),
                repaired=True,
                critic_result=critic_result,
                request_observation=request_observation,
                telemetry=telemetry,
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


def _finalize_response(
    *,
    message: str,
    current_user: User,
    response: StylistResponse,
    tool_counts: Counter[str],
    metrics: dict[str, int | float | bool],
    repaired: bool,
    critic_result: StyleCriticEvaluation | None,
    request_observation: Observation | None,
    telemetry: Observability,
) -> StylistApiResponse:
    """Build the unchanged API response after all required gates pass."""

    if current_user.id is None:
        raise RecommendationValidationError(
            "Authenticated user has no persisted ID"
        )
    critic_summary = {
        "approved": critic_result.approved if critic_result else None,
        "issue_count": len(critic_result.issues) if critic_result else 0,
    }
    if request_observation is not None:
        request_observation.score_trace(
            name="hallucination_detected", value="false"
        )
        request_observation.update(
            output={
                "status": response.status,
                "retry_count": int(repaired),
                "repair_count": int(repaired),
                "tool_invocation_counts": dict(tool_counts),
                "validation_failures": [],
                "style_critic": critic_summary,
                **metrics,
            }
        )

    with telemetry.observe(
        "response_formatting",
        output={
            "status": response.status,
            "retry_count": int(repaired),
            "repair_count": int(repaired),
            "hallucination_detected": False,
            "tool_invocation_counts": dict(tool_counts),
            "validation_failures": [],
            "style_critic": critic_summary,
            **metrics,
        },
    ):
        return StylistApiResponse(
            **response.model_dump(),
            lookbook_save_token=create_recommendation_save_token(
                user_id=current_user.id,
                user_request=message,
                item_ids=[item.item_id for item in response.owned_items],
                explanation=response.message,
                # The critic contract deliberately has no user-facing score.
                # Keep the existing signed Lookbook payload shape unchanged.
                evaluation_score=10.0,
            ),
        )

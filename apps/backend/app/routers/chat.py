"""Authenticated wardrobe-stylist chat endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.dependencies import (
    get_chat_scope_classifier,
    get_current_user,
    get_outfit_evaluator,
    get_stylist_runner,
)
from app.models.user import User
from app.observability import (
    log_development_traceback,
    structured_log,
    stylist_failure_fields,
)
from app.schemas.chat import ChatRequest, StylistApiResponse, StylistResponse
from app.services.chat import create_stylist_response
from app.services.chat_guardrails import ChatGuardrailError, ChatScopeClassifier
from app.services.outfit_evaluator import OutfitEvaluator
from app.services.stylist_agent import StylistAgentError, StylistRunner


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/recommendations", response_model=StylistApiResponse)
async def recommend_outfit(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    classifier: ChatScopeClassifier = Depends(get_chat_scope_classifier),
    runner: StylistRunner = Depends(get_stylist_runner),
    evaluator: OutfitEvaluator = Depends(get_outfit_evaluator),
) -> StylistResponse:
    """Guard one request, then run one wardrobe-grounded stylist agent."""

    try:
        response = await create_stylist_response(
            message=request.message,
            current_user=current_user,
            classifier=classifier,
            runner=runner,
            evaluator=evaluator,
            settings=get_settings(),
        )
        diagnostics = stylist_failure_fields()
        total_latency_ms = diagnostics.pop("duration_ms")
        evaluator_failures = diagnostics.get("evaluator_failures", [])
        structured_log(
            "stylist_request_completed",
            status=status.HTTP_200_OK,
            total_latency_ms=total_latency_ms,
            evaluator_nonblocking=bool(evaluator_failures),
            **diagnostics,
        )
        return response
    except (ChatGuardrailError, StylistAgentError) as error:
        structured_log(
            "stylist_request_failed",
            error_type=type(error).__name__,
            **stylist_failure_fields(),
        )
        log_development_traceback(error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Wardrobe stylist is temporarily unavailable",
        ) from error

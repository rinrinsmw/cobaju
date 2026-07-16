"""Authenticated wardrobe-stylist chat endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.dependencies import (
    get_chat_scope_classifier,
    get_current_user,
    get_stylist_runner,
)
from app.models.user import User
from app.schemas.chat import ChatRequest, StylistResponse
from app.services.chat import create_stylist_response
from app.services.chat_guardrails import ChatGuardrailError, ChatScopeClassifier
from app.services.stylist_agent import StylistAgentError, StylistRunner


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/recommendations", response_model=StylistResponse)
async def recommend_outfit(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    classifier: ChatScopeClassifier = Depends(get_chat_scope_classifier),
    runner: StylistRunner = Depends(get_stylist_runner),
) -> StylistResponse:
    """Guard one request, then run one wardrobe-grounded stylist agent."""

    try:
        return await create_stylist_response(
            message=request.message,
            current_user=current_user,
            classifier=classifier,
            runner=runner,
            settings=get_settings(),
        )
    except (ChatGuardrailError, StylistAgentError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Wardrobe stylist is temporarily unavailable",
        ) from error

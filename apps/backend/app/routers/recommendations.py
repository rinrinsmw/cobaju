"""Authenticated recommendation-history API."""

import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlmodel import Session

from app.core.security import decode_recommendation_save_token
from app.database import get_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.recommendation import (
    RecommendationHistoryRead,
    RecommendationSaveClaims,
    RecommendationSaved,
    RecommendationSaveRequest,
)
from app.observability import structured_log, user_observability_id
from app.services.recommendations import (
    InvalidRecommendationItemsError,
    RecommendationNotFoundError,
    delete_recommendation,
    list_recommendation_history,
    save_completed_recommendation_values,
)


router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("", response_model=RecommendationSaved, status_code=status.HTTP_201_CREATED)
def save_recommendation_to_lookbook(
    request: RecommendationSaveRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RecommendationSaved:
    """Save an evaluated look only after the authenticated user requests it."""

    if current_user.id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    payload = decode_recommendation_save_token(request.save_token, current_user.id)
    try:
        claims = RecommendationSaveClaims.model_validate(payload)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This recommendation can no longer be saved",
        ) from error

    try:
        saved = save_completed_recommendation_values(
            session,
            user_id=current_user.id,
            original_request=request.display_title or claims.user_request,
            item_ids=claims.item_ids,
            explanation=claims.explanation,
            evaluation_score=claims.evaluation_score,
        )
    except InvalidRecommendationItemsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more wardrobe items are no longer available",
        ) from error
    if saved.id is None:
        raise RuntimeError("Saved recommendation has no ID")
    return RecommendationSaved(id=saved.id)


@router.get("", response_model=list[RecommendationHistoryRead])
def recommendation_history(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[RecommendationHistoryRead]:
    """Return completed recommendations belonging to the authenticated user."""

    if current_user.id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    return list_recommendation_history(session, current_user.id)


@router.delete("/{recommendation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recommendation_history_entry(
    recommendation_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete one owned Lookbook entry without changing wardrobe data."""

    if current_user.id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    started_at = time.perf_counter()
    delete_success = False
    try:
        delete_recommendation(
            session,
            recommendation_id=recommendation_id,
            user_id=current_user.id,
        )
        delete_success = True
    except RecommendationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recommendation not found",
        ) from error
    finally:
        structured_log(
            "recommendation_deleted",
            recommendation_id=recommendation_id,
            user_id=user_observability_id(current_user.id),
            delete_success=delete_success,
            delete_latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )

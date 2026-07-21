"""Authenticated recommendation-history API."""

import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.recommendation import RecommendationHistoryRead
from app.observability import structured_log, user_observability_id
from app.services.recommendations import (
    RecommendationNotFoundError,
    delete_recommendation,
    list_recommendation_history,
)


router = APIRouter(prefix="/recommendations", tags=["recommendations"])


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

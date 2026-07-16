"""Authenticated recommendation-history API."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.recommendation import RecommendationHistoryRead
from app.services.recommendations import list_recommendation_history


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

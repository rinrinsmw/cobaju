"""Persistence and ownership-safe retrieval for completed recommendations."""

from sqlmodel import Session, select

from app.models.clothing_item import ClothingItem, ProcessingStatus
from app.models.recommendation import Recommendation
from app.schemas.chat import StylistResponse
from app.schemas.recommendation import (
    HistoricalClothingItem,
    RecommendationHistoryRead,
)


class InvalidRecommendationItemsError(Exception):
    """Raised when selected IDs are not all owned by the saving user."""


class RecommendationNotFoundError(Exception):
    """Raised when a recommendation does not belong to the requesting user."""


def save_completed_recommendation(
    session: Session,
    *,
    user_id: int,
    original_request: str,
    response: StylistResponse,
    evaluation_score: float,
) -> Recommendation:
    """Persist one final recommendation after rechecking every selected ID."""

    item_ids = [item.item_id for item in response.owned_items]
    if item_ids:
        statement = select(ClothingItem.id).where(
            ClothingItem.user_id == user_id,
            ClothingItem.id.in_(item_ids),  # type: ignore[union-attr]
            ClothingItem.processing_status == ProcessingStatus.COMPLETED,
        )
        owned_ids = set(session.exec(statement).all())
        if owned_ids != set(item_ids):
            raise InvalidRecommendationItemsError

    recommendation = Recommendation(
        user_id=user_id,
        original_request=original_request,
        selected_item_ids=item_ids,
        explanation=response.message,
        evaluation_score=evaluation_score,
    )
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)
    return recommendation


def list_recommendation_history(
    session: Session, user_id: int
) -> list[RecommendationHistoryRead]:
    """List only the user's history, newest first, resolving current items."""

    statement = (
        select(Recommendation)
        .where(Recommendation.user_id == user_id)
        .order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
    )
    recommendations = list(session.exec(statement).all())
    all_item_ids = {
        item_id
        for recommendation in recommendations
        for item_id in recommendation.selected_item_ids
    }
    items_by_id: dict[int, ClothingItem] = {}
    if all_item_ids:
        item_statement = select(ClothingItem).where(
            ClothingItem.user_id == user_id,
            ClothingItem.id.in_(all_item_ids),  # type: ignore[union-attr]
        )
        items_by_id = {
            item.id: item
            for item in session.exec(item_statement).all()
            if item.id is not None
        }

    history: list[RecommendationHistoryRead] = []
    for recommendation in recommendations:
        if recommendation.id is None:
            continue
        resolved_items = []
        for item_id in recommendation.selected_item_ids:
            item = items_by_id.get(item_id)
            resolved_items.append(
                HistoricalClothingItem(
                    item_id=item_id,
                    available=item is not None,
                    name=item.name if item else None,
                    category=item.category if item else None,
                    color=item.color if item else None,
                )
            )
        history.append(
            RecommendationHistoryRead(
                id=recommendation.id,
                original_request=recommendation.original_request,
                selected_item_ids=recommendation.selected_item_ids,
                items=resolved_items,
                explanation=recommendation.explanation,
                evaluation_score=recommendation.evaluation_score,
                created_at=recommendation.created_at,
            )
        )
    return history


def delete_recommendation(
    session: Session, *, recommendation_id: int, user_id: int
) -> None:
    """Delete only one recommendation owned by the authenticated user."""

    statement = select(Recommendation).where(
        Recommendation.id == recommendation_id,
        Recommendation.user_id == user_id,
    )
    recommendation = session.exec(statement).first()
    if recommendation is None:
        raise RecommendationNotFoundError

    session.delete(recommendation)
    session.commit()

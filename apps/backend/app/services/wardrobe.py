"""Business logic for ownership-safe wardrobe management."""

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.clothing_item import ClothingItem, ProcessingStatus
from app.schemas.wardrobe import (
    ClothingItemCreate,
    ClothingItemUpdate,
    ClothingMetadata,
)


MAX_CONFIRMED_ITEMS = 15


class ClothingItemNotFoundError(Exception):
    """Raised when an item is missing or is not owned by the current user."""


class WardrobeLimitReachedError(Exception):
    """Raised when a user already owns the maximum confirmed items."""


class InvalidProcessingStateError(Exception):
    """Raised when an item cannot perform the requested workflow transition."""


def count_confirmed_items(session: Session, user_id: int) -> int:
    """Count completed items belonging to one user."""

    statement = (
        select(func.count())
        .select_from(ClothingItem)
        .where(
            ClothingItem.user_id == user_id,
            ClothingItem.processing_status == ProcessingStatus.COMPLETED,
        )
    )
    return session.exec(statement).one()


def create_clothing_item(
    session: Session,
    user_id: int,
    item_create: ClothingItemCreate,
) -> ClothingItem:
    """Create a confirmed manual item when the user's wardrobe has space."""

    if count_confirmed_items(session, user_id) >= MAX_CONFIRMED_ITEMS:
        raise WardrobeLimitReachedError

    item = ClothingItem(
        user_id=user_id,
        processing_status=ProcessingStatus.COMPLETED,
        **item_create.model_dump(),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def list_clothing_items(session: Session, user_id: int) -> list[ClothingItem]:
    """Return only items owned by one authenticated user."""

    statement = (
        select(ClothingItem)
        .where(ClothingItem.user_id == user_id)
        .order_by(ClothingItem.id)
    )
    return list(session.exec(statement).all())


def get_owned_clothing_item(
    session: Session,
    user_id: int,
    item_id: int,
) -> ClothingItem:
    """Find an item using both its ID and trusted owner ID."""

    statement = select(ClothingItem).where(
        ClothingItem.id == item_id,
        ClothingItem.user_id == user_id,
    )
    item = session.exec(statement).first()
    if item is None:
        raise ClothingItemNotFoundError
    return item


def update_clothing_item(
    session: Session,
    user_id: int,
    item_id: int,
    item_update: ClothingItemUpdate,
) -> ClothingItem:
    """Apply only explicitly supplied metadata fields to an owned item."""

    item = get_owned_clothing_item(session, user_id, item_id)
    for field_name, value in item_update.model_dump(exclude_unset=True).items():
        setattr(item, field_name, value)

    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def attach_image_to_clothing_item(
    session: Session,
    item: ClothingItem,
    original_image_path: str,
) -> ClothingItem:
    """Record a safely stored original image and mark it ready for Phase 5."""

    item.original_image_path = original_image_path
    item.analysis_completed = False
    item.processing_status = ProcessingStatus.PENDING
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def mark_item_processing(session: Session, item: ClothingItem) -> ClothingItem:
    """Move an uploaded item into synchronous vision processing."""

    if item.original_image_path is None or item.processing_status not in {
        ProcessingStatus.PENDING,
        ProcessingStatus.FAILED,
    }:
        raise InvalidProcessingStateError
    item.analysis_completed = False
    item.processing_status = ProcessingStatus.PROCESSING
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def save_generated_metadata(
    session: Session,
    item: ClothingItem,
    metadata: ClothingMetadata,
) -> ClothingItem:
    """Save validated AI metadata as an unconfirmed, user-editable draft."""

    for field_name, value in metadata.model_dump().items():
        setattr(item, field_name, value)
    item.analysis_completed = True
    item.processing_status = ProcessingStatus.PENDING
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def mark_item_failed(session: Session, item: ClothingItem) -> ClothingItem:
    """Record an analysis failure while retaining the image for a retry."""

    item.processing_status = ProcessingStatus.FAILED
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def reject_item_image(session: Session, item: ClothingItem) -> str | None:
    """Detach a rejected image so non-clothing content is not kept."""

    rejected_path = item.original_image_path
    item.original_image_path = None
    item.analysis_completed = False
    item.processing_status = ProcessingStatus.FAILED
    session.add(item)
    session.commit()
    session.refresh(item)
    return rejected_path


def confirm_analyzed_item(session: Session, item: ClothingItem) -> ClothingItem:
    """Confirm a reviewed draft after the user has optionally edited it."""

    if (
        item.original_image_path is None
        or not item.analysis_completed
        or item.processing_status != ProcessingStatus.PENDING
    ):
        raise InvalidProcessingStateError
    if count_confirmed_items(session, item.user_id) >= MAX_CONFIRMED_ITEMS:
        raise WardrobeLimitReachedError
    item.processing_status = ProcessingStatus.COMPLETED
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def delete_clothing_item(
    session: Session,
    user_id: int,
    item_id: int,
) -> str | None:
    """Delete an item only after resolving it through its trusted owner."""

    item = get_owned_clothing_item(session, user_id, item_id)
    original_image_path = item.original_image_path
    session.delete(item)
    session.commit()
    return original_image_path

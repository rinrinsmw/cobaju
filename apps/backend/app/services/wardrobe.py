"""Business logic for ownership-safe wardrobe management."""

from typing import Protocol

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.clothing_item import ClothingCategory, ClothingItem, ProcessingStatus
from app.schemas.wardrobe import (
    ClothingItemCreate,
    ClothingItemUpdate,
    ClothingMetadata,
)


MAX_CONFIRMED_ITEMS = 15
PENDING_ITEM_NAME = "Pending analysis"
PENDING_ITEM_COLOR = "Unknown"


class ClothingItemNotFoundError(Exception):
    """Raised when an item is missing or is not owned by the current user."""


class WardrobeLimitReachedError(Exception):
    """Raised when a user already owns the maximum confirmed items."""


class InvalidProcessingStateError(Exception):
    """Raised when an item cannot perform the requested workflow transition."""


class WardrobeIndex(Protocol):
    """Minimal vector-index behavior needed by wardrobe lifecycle changes."""

    def upsert_item(self, item: ClothingItem) -> None: ...

    def delete_item(self, item_id: int) -> None: ...


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
    vector_index: WardrobeIndex | None = None,
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
    session.flush()
    try:
        if vector_index is not None:
            vector_index.upsert_item(item)
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(item)
    return item


def create_uploaded_clothing_item(
    session: Session,
    user_id: int,
    original_image_path: str,
) -> ClothingItem:
    """Create the pending database record for a newly stored image.

    Vision analysis replaces the temporary metadata before the user can
    confirm the item. Keeping this small operation in the service lets the
    multipart route cleanly remove the stored file if the commit fails.
    """

    item = ClothingItem(
        user_id=user_id,
        name=PENDING_ITEM_NAME,
        category=ClothingCategory.ACCESSORY,
        color=PENDING_ITEM_COLOR,
        original_image_path=original_image_path,
        analysis_completed=False,
        is_temporary_upload=True,
        processing_status=ProcessingStatus.PENDING,
    )
    session.add(item)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(item)
    return item


def list_clothing_items(session: Session, user_id: int) -> list[ClothingItem]:
    """Return owned wardrobe items without internal new-upload placeholders."""

    statement = (
        select(ClothingItem)
        .where(
            ClothingItem.user_id == user_id,
            ClothingItem.is_temporary_upload.is_(False),
        )
        .order_by(ClothingItem.id)
    )
    return list(session.exec(statement).all())


def list_confirmed_clothing_items(
    session: Session,
    user_id: int,
) -> list[ClothingItem]:
    """Return confirmed items eligible for one user's retrieval index."""

    statement = (
        select(ClothingItem)
        .where(
            ClothingItem.user_id == user_id,
            ClothingItem.processing_status == ProcessingStatus.COMPLETED,
        )
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
    vector_index: WardrobeIndex | None = None,
) -> ClothingItem:
    """Apply only explicitly supplied metadata fields to an owned item."""

    item = get_owned_clothing_item(session, user_id, item_id)
    for field_name, value in item_update.model_dump(exclude_unset=True).items():
        setattr(item, field_name, value)

    session.add(item)
    session.flush()
    try:
        if vector_index is not None and item.id is not None:
            if item.processing_status == ProcessingStatus.COMPLETED:
                vector_index.upsert_item(item)
            else:
                vector_index.delete_item(item.id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(item)
    return item


def attach_image_to_clothing_item(
    session: Session,
    item: ClothingItem,
    original_image_path: str,
    vector_index: WardrobeIndex | None = None,
) -> ClothingItem:
    """Record a safely stored original image and mark it ready for Phase 5."""

    # Pending uploads are not searchable. Remove the confirmed vector before
    # changing database state so an index failure cannot leave a broken image
    # reference committed by an API request that reports failure.
    if vector_index is not None and item.id is not None:
        vector_index.delete_item(item.id)
    item.original_image_path = original_image_path
    item.analysis_completed = False
    item.processing_status = ProcessingStatus.PENDING
    session.add(item)
    try:
        session.commit()
    except Exception:
        session.rollback()
        if vector_index is not None:
            vector_index.upsert_item(item)
        raise
    session.refresh(item)
    return item


def mark_item_processing(session: Session, item: ClothingItem) -> ClothingItem:
    """Claim an uploaded item for vision processing."""

    if (
        item.original_image_path is None
        or item.analysis_completed
        or item.processing_status
        not in {ProcessingStatus.PENDING, ProcessingStatus.FAILED}
    ):
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
    item.is_temporary_upload = False
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


def restore_item_pending(session: Session, item: ClothingItem) -> ClothingItem:
    """Make an item retryable when its task could not reach the broker."""

    if item.processing_status != ProcessingStatus.PROCESSING:
        raise InvalidProcessingStateError
    item.processing_status = ProcessingStatus.PENDING
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def reject_item_image(session: Session, item: ClothingItem) -> str | None:
    """Detach a rejected image while preserving a pre-existing wardrobe item."""

    rejected_path = item.original_image_path
    item.original_image_path = None
    item.analysis_completed = False
    item.processing_status = ProcessingStatus.COMPLETED
    session.add(item)
    session.commit()
    session.refresh(item)
    return rejected_path


def delete_temporary_upload(session: Session, item: ClothingItem) -> None:
    """Delete only a placeholder created by the combined new-upload route."""

    if not item.is_temporary_upload:
        raise InvalidProcessingStateError
    session.delete(item)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


def confirm_analyzed_item(
    session: Session,
    item: ClothingItem,
    vector_index: WardrobeIndex | None = None,
) -> ClothingItem:
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
    session.flush()
    try:
        if vector_index is not None:
            vector_index.upsert_item(item)
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(item)
    return item


def delete_clothing_item(
    session: Session,
    user_id: int,
    item_id: int,
    vector_index: WardrobeIndex | None = None,
) -> str | None:
    """Delete an item only after resolving it through its trusted owner."""

    item = get_owned_clothing_item(session, user_id, item_id)
    original_image_path = item.original_image_path
    if vector_index is not None:
        vector_index.delete_item(item_id)
    session.delete(item)
    session.commit()
    return original_image_path

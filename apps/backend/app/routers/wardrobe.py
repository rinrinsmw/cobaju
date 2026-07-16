"""Authenticated wardrobe CRUD and image-upload API routes."""

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.core.config import get_settings
from app.database import get_session
from app.dependencies import get_current_user
from app.models.clothing_item import ClothingItem, ProcessingStatus
from app.models.user import User
from app.schemas.wardrobe import (
    ClothingItemCreate,
    ClothingItemRead,
    ClothingItemUpdate,
    ClothingProcessingStatusRead,
)
from app.services.image_uploads import (
    ImageTooLargeError,
    UnsupportedImageError,
    delete_stored_image,
    save_original_image,
)
from app.tasks.clothing_processing import (
    ClothingTaskEnqueueError,
    enqueue_clothing_analysis,
)
from app.services.wardrobe import (
    ClothingItemNotFoundError,
    InvalidProcessingStateError,
    WardrobeLimitReachedError,
    attach_image_to_clothing_item,
    confirm_analyzed_item,
    create_clothing_item,
    delete_clothing_item,
    get_owned_clothing_item,
    list_clothing_items,
    mark_item_processing,
    restore_item_pending,
    update_clothing_item,
)


router = APIRouter(prefix="/wardrobe/items", tags=["wardrobe"])


def require_user_id(current_user: User) -> int:
    """Return the persisted ID guaranteed by the authentication dependency."""

    if current_user.id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    return current_user.id


def not_found_response() -> HTTPException:
    """Use one response for absent and cross-user items."""

    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Clothing item not found",
    )


@router.post("", response_model=ClothingItemRead, status_code=status.HTTP_201_CREATED)
def create_item(
    item_create: ClothingItemCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClothingItem:
    """Create manually confirmed metadata for the authenticated user."""

    try:
        return create_clothing_item(
            session,
            require_user_id(current_user),
            item_create,
        )
    except WardrobeLimitReachedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wardrobe limit of 15 confirmed items reached",
        ) from error


@router.get("", response_model=list[ClothingItemRead])
def list_items(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ClothingItem]:
    """List the authenticated user's wardrobe in creation order."""

    return list_clothing_items(session, require_user_id(current_user))


@router.get("/{item_id}", response_model=ClothingItemRead)
def read_item(
    item_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClothingItem:
    """Return one item only when it belongs to the authenticated user."""

    try:
        return get_owned_clothing_item(
            session,
            require_user_id(current_user),
            item_id,
        )
    except ClothingItemNotFoundError as error:
        raise not_found_response() from error


@router.post(
    "/{item_id}/image",
    response_model=ClothingItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_item_image(
    item_id: int,
    image: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClothingItem:
    """Store one validated original image for an owned clothing item."""

    user_id = require_user_id(current_user)
    try:
        item = get_owned_clothing_item(session, user_id, item_id)
    except ClothingItemNotFoundError as error:
        raise not_found_response() from error

    if item.original_image_path is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Clothing item already has an image",
        )

    settings = get_settings()
    stored_path: str | None = None
    image_attached = False
    try:
        stored_path = await save_original_image(
            image,
            settings.resolved_upload_directory,
            user_id,
        )
        updated_item = attach_image_to_clothing_item(session, item, stored_path)
        image_attached = True
        return updated_item
    except UnsupportedImageError as error:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Image must be a valid JPG, PNG, or WebP file",
        ) from error
    except ImageTooLargeError as error:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image must not exceed 5 MB",
        ) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save image metadata",
        ) from error
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store image",
        ) from error
    finally:
        if stored_path is not None and not image_attached:
            try:
                delete_stored_image(settings.resolved_upload_directory, stored_path)
            except OSError:
                pass
        await image.close()


@router.post(
    "/{item_id}/analyze",
    response_model=ClothingItemRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_item_image(
    item_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClothingItem:
    """Claim one owned upload and send its analysis to the Celery worker."""

    try:
        item = get_owned_clothing_item(
            session,
            require_user_id(current_user),
            item_id,
        )
    except ClothingItemNotFoundError as error:
        raise not_found_response() from error

    settings = get_settings()
    if item.original_image_path is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Clothing item has no image to analyze",
        )
    image_path = (
        settings.resolved_upload_directory / item.original_image_path
    ).resolve()
    if (
        not image_path.is_relative_to(settings.resolved_upload_directory)
        or not image_path.is_file()
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored image is unavailable",
        )

    try:
        queued_item = mark_item_processing(session, item)
    except InvalidProcessingStateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Clothing item is not ready for analysis",
        ) from error

    try:
        enqueue_clothing_analysis(item_id)
    except ClothingTaskEnqueueError as error:
        restore_item_pending(session, queued_item)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clothing analysis could not be queued",
        ) from error
    return queued_item


@router.get(
    "/{item_id}/status",
    response_model=ClothingProcessingStatusRead,
)
def read_item_processing_status(
    item_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClothingProcessingStatusRead:
    """Return a compact, ownership-safe status for frontend polling."""

    try:
        item = get_owned_clothing_item(
            session,
            require_user_id(current_user),
            item_id,
        )
    except ClothingItemNotFoundError as error:
        raise not_found_response() from error

    if item.processing_status == ProcessingStatus.FAILED:
        analysis_status = ProcessingStatus.FAILED
    elif item.analysis_completed:
        analysis_status = ProcessingStatus.COMPLETED
    else:
        analysis_status = item.processing_status

    return ClothingProcessingStatusRead(
        item_id=item_id,
        status=analysis_status,
        analysis_completed=item.analysis_completed,
        needs_confirmation=(
            item.analysis_completed
            and item.processing_status == ProcessingStatus.PENDING
        ),
    )


@router.post("/{item_id}/confirm", response_model=ClothingItemRead)
def confirm_item_metadata(
    item_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClothingItem:
    """Confirm an analyzed draft after the user has reviewed its metadata."""

    try:
        item = get_owned_clothing_item(
            session,
            require_user_id(current_user),
            item_id,
        )
        return confirm_analyzed_item(session, item)
    except ClothingItemNotFoundError as error:
        raise not_found_response() from error
    except InvalidProcessingStateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Clothing item has no analyzed draft to confirm",
        ) from error
    except WardrobeLimitReachedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wardrobe limit of 15 confirmed items reached",
        ) from error


@router.patch("/{item_id}", response_model=ClothingItemRead)
def update_item(
    item_id: int,
    item_update: ClothingItemUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClothingItem:
    """Partially update metadata on an owned item."""

    try:
        return update_clothing_item(
            session,
            require_user_id(current_user),
            item_id,
            item_update,
        )
    except ClothingItemNotFoundError as error:
        raise not_found_response() from error


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete an owned item and return an empty success response."""

    try:
        original_image_path = delete_clothing_item(
            session,
            require_user_id(current_user),
            item_id,
        )
    except ClothingItemNotFoundError as error:
        raise not_found_response() from error

    if original_image_path is not None:
        try:
            delete_stored_image(
                get_settings().resolved_upload_directory,
                original_image_path,
            )
        except OSError:
            # The database deletion succeeded; a missing/unavailable local file
            # must not turn that successful API operation into a false failure.
            pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)

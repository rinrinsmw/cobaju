"""Authenticated wardrobe CRUD API routes."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_current_user
from app.models.clothing_item import ClothingItem
from app.models.user import User
from app.schemas.wardrobe import (
    ClothingItemCreate,
    ClothingItemRead,
    ClothingItemUpdate,
)
from app.services.wardrobe import (
    ClothingItemNotFoundError,
    WardrobeLimitReachedError,
    create_clothing_item,
    delete_clothing_item,
    get_owned_clothing_item,
    list_clothing_items,
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
        delete_clothing_item(
            session,
            require_user_id(current_user),
            item_id,
        )
    except ClothingItemNotFoundError as error:
        raise not_found_response() from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)

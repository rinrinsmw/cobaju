"""Registration, login, and current-user API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.security import create_access_token
from app.database import get_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import AccessToken, LoginRequest, UserCreate, UserRead
from app.services.users import (
    EmailAlreadyRegisteredError,
    authenticate_user,
    create_user,
)


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
def register(
    user_create: UserCreate,
    session: Session = Depends(get_session),
) -> User:
    """Create a user without exposing its password hash."""

    try:
        return create_user(session, user_create)
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from error


@router.post("/login", response_model=AccessToken)
def login(
    credentials: LoginRequest,
    session: Session = Depends(get_session),
) -> AccessToken:
    """Exchange valid credentials for a short-lived JWT."""

    user = authenticate_user(session, str(credentials.email), credentials.password)
    if user is None or user.id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AccessToken(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    """Return the user identified by the Bearer token."""

    return current_user

"""User registration and credential verification services."""

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import UserCreate


class EmailAlreadyRegisteredError(Exception):
    """Raised when registration uses an existing normalized email."""


def get_user_by_email(session: Session, email: str) -> User | None:
    """Find one user by normalized email."""

    return session.exec(select(User).where(User.email == email.lower())).first()


def create_user(session: Session, user_create: UserCreate) -> User:
    """Hash credentials and persist a new user account."""

    if get_user_by_email(session, str(user_create.email)) is not None:
        raise EmailAlreadyRegisteredError

    user = User(
        email=str(user_create.email),
        hashed_password=hash_password(user_create.password),
    )
    session.add(user)

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise EmailAlreadyRegisteredError from error

    session.refresh(user)
    return user


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    """Return the user only when both email and password are valid."""

    user = get_user_by_email(session, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None

    return user

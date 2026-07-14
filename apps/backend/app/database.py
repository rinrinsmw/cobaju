"""SQLModel engine and FastAPI session dependency."""

from collections.abc import Generator

from sqlmodel import Session, create_engine, select

from app.core.config import get_settings


settings = get_settings()
connect_args = (
    {"check_same_thread": False}
    if settings.resolved_database_url.startswith("sqlite:")
    else {}
)
engine = create_engine(settings.resolved_database_url, connect_args=connect_args)


def get_session() -> Generator[Session, None, None]:
    """Provide one database session for the duration of a request."""

    with Session(engine) as session:
        yield session


def verify_database_connection(session: Session) -> None:
    """Run the smallest useful query to prove the database is reachable."""

    session.exec(select(1)).one()

"""Database model for completed, evaluated outfit recommendations."""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """Return an aware UTC timestamp for newly completed recommendations."""

    return datetime.now(timezone.utc)


class Recommendation(SQLModel, table=True):
    """One accepted outfit recommendation owned by one authenticated user."""

    __tablename__ = "recommendations"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    original_request: str = Field(max_length=500)
    selected_item_ids: list[int] = Field(sa_column=Column(JSON, nullable=False))
    explanation: str = Field(max_length=1200)
    evaluation_score: float = Field(ge=0, le=10)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )

"""Database model for an authenticated Cobaju user."""

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """A registered account with a safely hashed password."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=320)
    hashed_password: str = Field(max_length=255)

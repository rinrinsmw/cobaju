"""Database model and enums for wardrobe clothing items."""

from enum import Enum

from sqlalchemy import Column, Enum as SQLAlchemyEnum, text
from sqlmodel import Field, SQLModel


class ClothingCategory(str, Enum):
    """Supported high-level wardrobe categories for the MVP."""

    TOP = "top"
    BOTTOM = "bottom"
    DRESS = "dress"
    OUTERWEAR = "outerwear"
    SHOES = "shoes"
    BAG = "bag"
    ACCESSORY = "accessory"


class ProcessingStatus(str, Enum):
    """Lifecycle states used by current and future clothing workflows."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def enum_values(enum_class: type[Enum]) -> list[str]:
    """Store an enum's public values instead of its Python member names."""

    return [str(member.value) for member in enum_class]


class ClothingItem(SQLModel, table=True):
    """One clothing item owned by exactly one authenticated user."""

    __tablename__ = "clothing_items"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=100)
    category: ClothingCategory = Field(
        sa_column=Column(
            SQLAlchemyEnum(
                ClothingCategory,
                name="clothing_category",
                native_enum=False,
                create_constraint=True,
                values_callable=enum_values,
            ),
            nullable=False,
        )
    )
    color: str = Field(max_length=50)
    description: str | None = Field(default=None, max_length=500)
    processing_status: ProcessingStatus = Field(
        default=ProcessingStatus.COMPLETED,
        sa_column=Column(
            SQLAlchemyEnum(
                ProcessingStatus,
                name="processing_status",
                native_enum=False,
                create_constraint=True,
                values_callable=enum_values,
            ),
            nullable=False,
            server_default=text("'completed'"),
        ),
    )

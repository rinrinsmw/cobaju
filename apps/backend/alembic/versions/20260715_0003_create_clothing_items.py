"""Create the clothing_items table.

Revision ID: 20260715_0003
Revises: 20260715_0002
Create Date: 2026-07-15
"""

import sqlalchemy as sa
from alembic import op


revision: str = "20260715_0003"
down_revision: str | None = "20260715_0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create ownership-scoped clothing metadata records."""

    op.create_table(
        "clothing_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "top",
                "bottom",
                "dress",
                "outerwear",
                "shoes",
                "bag",
                "accessory",
                name="clothing_category",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("color", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "processing_status",
            sa.Enum(
                "pending",
                "processing",
                "completed",
                "failed",
                name="processing_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default=sa.text("'completed'"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_clothing_items_user_id"),
        "clothing_items",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove clothing metadata while leaving user accounts intact."""

    op.drop_index(op.f("ix_clothing_items_user_id"), table_name="clothing_items")
    op.drop_table("clothing_items")

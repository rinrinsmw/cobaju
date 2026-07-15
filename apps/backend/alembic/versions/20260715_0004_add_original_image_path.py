"""Add original image paths to clothing items.

Revision ID: 20260715_0004
Revises: 20260715_0003
Create Date: 2026-07-15
"""

import sqlalchemy as sa
from alembic import op


revision: str = "20260715_0004"
down_revision: str | None = "20260715_0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Allow one portable local image path per clothing item."""

    op.add_column(
        "clothing_items",
        sa.Column("original_image_path", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    """Remove stored image path metadata."""

    op.drop_column("clothing_items", "original_image_path")

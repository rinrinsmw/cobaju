"""Mark internal rows created by the combined upload flow.

Revision ID: 20260721_0007
Revises: 20260716_0006
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op


revision: str = "20260721_0007"
down_revision: str | None = "20260716_0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Keep unfinished new uploads out of the permanent wardrobe."""

    op.add_column(
        "clothing_items",
        sa.Column(
            "is_temporary_upload",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        op.f("ix_clothing_items_is_temporary_upload"),
        "clothing_items",
        ["is_temporary_upload"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the internal upload marker."""

    op.drop_index(
        op.f("ix_clothing_items_is_temporary_upload"),
        table_name="clothing_items",
    )
    op.drop_column("clothing_items", "is_temporary_upload")

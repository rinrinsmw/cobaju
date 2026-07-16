"""Add analysis completion marker for the review workflow.

Revision ID: 20260715_0005
Revises: 20260715_0004
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260715_0005"
down_revision: str | None = "20260715_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Track whether AI metadata is ready for explicit confirmation."""

    op.add_column(
        "clothing_items",
        sa.Column(
            "analysis_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Remove the Phase 5 analysis marker."""

    op.drop_column("clothing_items", "analysis_completed")

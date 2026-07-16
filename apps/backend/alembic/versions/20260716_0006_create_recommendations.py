"""Create the recommendations table.

Revision ID: 20260716_0006
Revises: 20260715_0005
Create Date: 2026-07-16
"""

import sqlalchemy as sa
from alembic import op


revision: str = "20260716_0006"
down_revision: str | None = "20260715_0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Store only recommendations that completed every validation step."""

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("original_request", sa.String(length=500), nullable=False),
        sa.Column("selected_item_ids", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.String(length=1200), nullable=False),
        sa.Column("evaluation_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "evaluation_score >= 0 AND evaluation_score <= 10",
            name="ck_recommendations_evaluation_score",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recommendations_user_id"),
        "recommendations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recommendations_created_at"),
        "recommendations",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove recommendation history without changing wardrobe records."""

    op.drop_index(op.f("ix_recommendations_created_at"), table_name="recommendations")
    op.drop_index(op.f("ix_recommendations_user_id"), table_name="recommendations")
    op.drop_table("recommendations")

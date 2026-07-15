"""Create the users table.

Revision ID: 20260715_0002
Revises: 20260714_0001
Create Date: 2026-07-15
"""

import sqlalchemy as sa
from alembic import op


revision: str = "20260715_0002"
down_revision: str | None = "20260714_0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create registered users with unique indexed emails."""

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)


def downgrade() -> None:
    """Remove the users table when rolling back this revision."""

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

"""Establish the initial migration chain.

Revision ID: 20260714_0001
Revises:
Create Date: 2026-07-14
"""


revision: str = "20260714_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create the Phase 1 schema.

    Phase 1 intentionally has no domain models. Alembic still records this
    revision so future table migrations have a stable starting point.
    """

    pass


def downgrade() -> None:
    """Return to the state before the initial revision."""

    pass

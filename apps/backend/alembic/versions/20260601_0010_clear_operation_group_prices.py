"""clear prices from operation groups

Revision ID: 20260601_0010
Revises: 20260601_0009
Create Date: 2026-06-01 18:30:00
"""

from alembic import op

revision = "20260601_0010"
down_revision = "20260601_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE operations
        SET price_cents = NULL
        WHERE id IN (
            SELECT DISTINCT parent_id
            FROM operations
            WHERE parent_id IS NOT NULL
        )
        """
    )


def downgrade() -> None:
    pass

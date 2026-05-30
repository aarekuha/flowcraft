"""add work order completion marker

Revision ID: 20260530_0002
Revises: 20260422_0001
Create Date: 2026-05-30 12:30:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260530_0002"
down_revision = "20260422_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_orders",
        sa.Column("completed_at", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("work_orders", "completed_at")

"""prevent simultaneous active workers on one order operation

Revision ID: 20261104_0024
Revises: 20261029_0023
Create Date: 2026-11-04 22:15:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20261104_0024"
down_revision = "20261029_0023"
branch_labels = None
depends_on = None


ACTIVE_OPERATION_PREDICATE = (
    "ended_at IS NULL AND deleted_at IS NULL "
    "AND timer_type_code = 2 "
    "AND order_id IS NOT NULL AND operation_id IS NOT NULL"
)


def upgrade() -> None:
    op.create_index(
        "uq_timer_sessions_active_order_operation",
        "timer_sessions",
        ["order_id", "operation_id"],
        unique=True,
        sqlite_where=sa.text(ACTIVE_OPERATION_PREDICATE),
        postgresql_where=sa.text(ACTIVE_OPERATION_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_timer_sessions_active_order_operation",
        table_name="timer_sessions",
    )

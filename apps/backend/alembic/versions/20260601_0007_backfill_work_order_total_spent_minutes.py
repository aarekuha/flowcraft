"""backfill work order total spent minutes

Revision ID: 20260601_0007
Revises: 20260601_0006
Create Date: 2026-06-01 15:10:00
"""

from alembic import op

revision = "20260601_0007"
down_revision = "20260601_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE work_orders
        SET total_spent_minutes = COALESCE(
            (
                SELECT CAST(
                    SUM(timer_sessions.ended_at - timer_sessions.started_at) / 60000
                    AS INTEGER
                )
                FROM timer_sessions
                WHERE timer_sessions.order_id = work_orders.id
                  AND timer_sessions.timer_type_code = 2
                  AND timer_sessions.ended_at IS NOT NULL
            ),
            0
        )
        """
    )


def downgrade() -> None:
    pass

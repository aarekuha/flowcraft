"""separate work order estimated minutes

Revision ID: 20260601_0006
Revises: 20260601_0005
Create Date: 2026-06-01 14:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260601_0006"
down_revision = "20260601_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(
            sa.Column(
                "estimated_minutes",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    op.execute(
        "UPDATE work_orders SET estimated_minutes = total_spent_minutes"
    )
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
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("estimated_minutes")

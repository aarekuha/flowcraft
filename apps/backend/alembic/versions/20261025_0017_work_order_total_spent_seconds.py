"""store work order total spent time in seconds

Revision ID: 20261025_0017
Revises: 20261019_0016
Create Date: 2026-10-25 10:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20261025_0017"
down_revision = "20261019_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "work_orders" not in inspector.get_table_names():
        return

    has_minutes = _has_column(bind, "work_orders", "total_spent_minutes")
    has_seconds = _has_column(bind, "work_orders", "total_spent_seconds")

    if not has_seconds:
        with op.batch_alter_table("work_orders") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "total_spent_seconds",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )

    if has_minutes:
        if "timer_sessions" in inspector.get_table_names():
            op.execute(
                """
                UPDATE work_orders
                SET total_spent_seconds = COALESCE(
                    (
                        SELECT CAST(
                            SUM(timer_sessions.ended_at - timer_sessions.started_at)
                            / 1000 AS INTEGER
                        )
                        FROM timer_sessions
                        WHERE timer_sessions.order_id = work_orders.id
                          AND timer_sessions.timer_type_code = 2
                          AND timer_sessions.ended_at IS NOT NULL
                    ),
                    total_spent_minutes * 60,
                    0
                )
                """
            )
        else:
            op.execute(
                """
                UPDATE work_orders
                SET total_spent_seconds = total_spent_minutes * 60
                """
            )

        with op.batch_alter_table("work_orders") as batch_op:
            batch_op.drop_column("total_spent_minutes")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "work_orders" not in inspector.get_table_names():
        return

    has_minutes = _has_column(bind, "work_orders", "total_spent_minutes")
    has_seconds = _has_column(bind, "work_orders", "total_spent_seconds")

    if not has_minutes:
        with op.batch_alter_table("work_orders") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "total_spent_minutes",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )

    if has_seconds:
        op.execute(
            """
            UPDATE work_orders
            SET total_spent_minutes = CAST(total_spent_seconds / 60 AS INTEGER)
            """
        )

        with op.batch_alter_table("work_orders") as batch_op:
            batch_op.drop_column("total_spent_seconds")


def _has_column(
    bind: sa.engine.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )

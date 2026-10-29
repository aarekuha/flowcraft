"""add work order sewing start

Revision ID: 20261029_0023
Revises: 20261028_0022
Create Date: 2026-10-29 10:30:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_0023"
down_revision = "20261028_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(
            sa.Column("sewing_started_at", sa.BigInteger(), nullable=True)
        )

    op.execute(
        """
        WITH sewing_operation_starts AS (
            SELECT
                timer_sessions.order_id AS order_id,
                timer_sessions.started_at AS started_at
            FROM timer_sessions
            JOIN operations
              ON operations.id = timer_sessions.operation_id
            LEFT JOIN operation_catalog_entries
              ON operation_catalog_entries.id = operations.operation_catalog_entry_id
            WHERE timer_sessions.order_id IS NOT NULL
              AND timer_sessions.timer_type_code = 2
              AND timer_sessions.deleted_at IS NULL
              AND (
                  operation_catalog_entries.id IS NULL
                  OR operation_catalog_entries.operation_kind = 'regular'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM work_order_time_allocations
                  WHERE work_order_time_allocations.timer_session_id = timer_sessions.id
              )

            UNION ALL

            SELECT
                work_order_time_allocations.work_order_id AS order_id,
                timer_sessions.started_at AS started_at
            FROM work_order_time_allocations
            JOIN timer_sessions
              ON timer_sessions.id = work_order_time_allocations.timer_session_id
            JOIN operations
              ON operations.id = timer_sessions.operation_id
            LEFT JOIN operation_catalog_entries
              ON operation_catalog_entries.id = operations.operation_catalog_entry_id
            WHERE work_order_time_allocations.allocated_seconds > 0
              AND timer_sessions.timer_type_code = 2
              AND timer_sessions.deleted_at IS NULL
              AND (
                  operation_catalog_entries.id IS NULL
                  OR operation_catalog_entries.operation_kind = 'regular'
              )
        ),
        first_sewing_starts AS (
            SELECT order_id, MIN(started_at) AS started_at
            FROM sewing_operation_starts
            GROUP BY order_id
        )
        UPDATE work_orders
        SET sewing_started_at = (
            SELECT first_sewing_starts.started_at
            FROM first_sewing_starts
            WHERE first_sewing_starts.order_id = work_orders.id
        )
        WHERE EXISTS (
            SELECT 1
            FROM first_sewing_starts
            WHERE first_sewing_starts.order_id = work_orders.id
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("sewing_started_at")

"""add work order cutting stage

Revision ID: 20261025_0019
Revises: 20261025_0018
Create Date: 2026-10-25 14:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20261025_0019"
down_revision = "20261025_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(
            sa.Column(
                "production_stage",
                sa.String(length=16),
                nullable=True,
                server_default="created",
            )
        )
        batch_op.add_column(
            sa.Column(
                "cutting_spent_seconds",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("cutting_started_at", sa.BigInteger(), nullable=True)
        )

    op.execute(
        """
        UPDATE work_orders
        SET production_stage = CASE
            WHEN taken_at IS NOT NULL THEN 'in_work'
            ELSE 'created'
        END
        """
    )

    op.execute(
        """
        UPDATE work_orders
        SET cutting_started_at = (
            SELECT MIN(timer_sessions.started_at)
            FROM timer_sessions
            JOIN operations
              ON operations.id = timer_sessions.operation_id
            JOIN operation_catalog_entries
              ON operation_catalog_entries.id = operations.operation_catalog_entry_id
            WHERE timer_sessions.timer_type_code = 2
              AND operation_catalog_entries.operation_kind = 'cutting'
              AND (
                    timer_sessions.order_id = work_orders.id
                    OR EXISTS (
                        SELECT 1
                        FROM work_order_time_allocations
                        WHERE work_order_time_allocations.timer_session_id = timer_sessions.id
                          AND work_order_time_allocations.work_order_id = work_orders.id
                    )
              )
        )
        """
    )

    op.execute(
        """
        UPDATE work_orders
        SET cutting_spent_seconds =
            COALESCE(
                (
                    SELECT CAST(
                        SUM(timer_sessions.ended_at - timer_sessions.started_at)
                        / 1000 AS INTEGER
                    )
                    FROM timer_sessions
                    JOIN operations
                      ON operations.id = timer_sessions.operation_id
                    JOIN operation_catalog_entries
                      ON operation_catalog_entries.id = operations.operation_catalog_entry_id
                    WHERE timer_sessions.order_id = work_orders.id
                      AND timer_sessions.timer_type_code = 2
                      AND timer_sessions.ended_at IS NOT NULL
                      AND operation_catalog_entries.operation_kind = 'cutting'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM work_order_time_allocations
                          WHERE work_order_time_allocations.timer_session_id = timer_sessions.id
                      )
                ),
                0
            )
            + COALESCE(
                (
                    SELECT SUM(work_order_time_allocations.allocated_seconds)
                    FROM work_order_time_allocations
                    JOIN timer_sessions
                      ON timer_sessions.id = work_order_time_allocations.timer_session_id
                    JOIN operations
                      ON operations.id = timer_sessions.operation_id
                    JOIN operation_catalog_entries
                      ON operation_catalog_entries.id = operations.operation_catalog_entry_id
                    WHERE work_order_time_allocations.work_order_id = work_orders.id
                      AND timer_sessions.ended_at IS NOT NULL
                      AND operation_catalog_entries.operation_kind = 'cutting'
                ),
                0
            )
        """
    )

    op.execute(
        """
        UPDATE work_orders
        SET taken_at = (
            SELECT MIN(timer_sessions.started_at)
            FROM timer_sessions
            WHERE timer_sessions.timer_type_code = 2
              AND timer_sessions.ended_at IS NOT NULL
              AND timer_sessions.ended_at > timer_sessions.started_at
              AND (
                    (
                        timer_sessions.order_id = work_orders.id
                        AND NOT EXISTS (
                            SELECT 1
                            FROM work_order_time_allocations
                            WHERE work_order_time_allocations.timer_session_id = timer_sessions.id
                        )
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM work_order_time_allocations
                        WHERE work_order_time_allocations.timer_session_id = timer_sessions.id
                          AND work_order_time_allocations.work_order_id = work_orders.id
                          AND work_order_time_allocations.allocated_seconds > 0
                    )
              )
        )
        """
    )

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.alter_column("production_stage", nullable=False)
        batch_op.create_check_constraint(
            "ck_work_orders_production_stage",
            "production_stage IN ('created', 'cutting', 'in_work')",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_cutting_spent_seconds",
            "cutting_spent_seconds >= 0",
        )
        batch_op.create_index(
            "ix_work_orders_production_stage",
            ["production_stage"],
        )


def downgrade() -> None:
    op.execute(
        """
        UPDATE work_orders
        SET taken_at = COALESCE(taken_at, updated_at)
        WHERE production_stage = 'in_work'
          AND taken_at IS NULL
        """
    )

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_index("ix_work_orders_production_stage")
        batch_op.drop_constraint(
            "ck_work_orders_cutting_spent_seconds",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_work_orders_production_stage",
            type_="check",
        )
        batch_op.drop_column("cutting_started_at")
        batch_op.drop_column("cutting_spent_seconds")
        batch_op.drop_column("production_stage")

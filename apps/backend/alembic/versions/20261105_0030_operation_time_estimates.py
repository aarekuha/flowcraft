"""add statistical operation time estimates

Revision ID: 20261105_0030
Revises: 20261105_0029
Create Date: 2026-11-05 16:00:00
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20261105_0030"
down_revision = "20261105_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_time_estimates",
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("seconds_per_item", sa.Integer(), nullable=True),
        sa.Column("completed_orders_count", sa.Integer(), nullable=False),
        sa.Column("items_count", sa.Integer(), nullable=False),
        sa.Column("calculated_at", sa.BigInteger(), nullable=True),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("dirty_at", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "seconds_per_item IS NULL OR seconds_per_item >= 0",
            name="ck_operation_time_estimates_seconds",
        ),
        sa.CheckConstraint(
            "completed_orders_count >= 0",
            name="ck_operation_time_estimates_orders_count",
        ),
        sa.CheckConstraint(
            "items_count >= 0",
            name="ck_operation_time_estimates_items_count",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["operations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("operation_id"),
    )
    op.create_index(
        "ix_operation_time_estimates_dirty_at",
        "operation_time_estimates",
        ["dirty_at"],
    )
    op.add_column(
        "planning_operation_results",
        sa.Column("standard_time_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "planning_operation_results",
        sa.Column("standard_time_source", sa.String(length=16), nullable=True),
    )

    now = int(datetime.now(UTC).timestamp() * 1000)
    op.execute(
        sa.text(
            """
            INSERT INTO operation_time_estimates (
                operation_id,
                seconds_per_item,
                completed_orders_count,
                items_count,
                calculated_at,
                algorithm_version,
                dirty_at
            )
            SELECT
                operation.id,
                NULL,
                0,
                0,
                NULL,
                'weighted-median-v1',
                :dirty_at
            FROM operations AS operation
            WHERE NOT EXISTS (
                SELECT 1
                FROM operations AS child
                WHERE child.parent_id = operation.id
            )
            """
        ).bindparams(dirty_at=now)
    )


def downgrade() -> None:
    op.drop_column("planning_operation_results", "standard_time_source")
    op.drop_column("planning_operation_results", "standard_time_seconds")
    op.drop_index(
        "ix_operation_time_estimates_dirty_at",
        table_name="operation_time_estimates",
    )
    op.drop_table("operation_time_estimates")

"""add production planning runs and results

Revision ID: 20261105_0029
Revises: 20261105_0028
Create Date: 2026-11-05 12:00:00
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20261105_0029"
down_revision = "20261105_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planning_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("input_revision", sa.BigInteger(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.BigInteger(), nullable=False),
        sa.Column("completed_at", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_details", sa.String(length=2000), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'stale', 'failed')",
            name="ck_planning_runs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_planning_runs_input_revision",
        "planning_runs",
        ["input_revision"],
    )
    op.create_index("ix_planning_runs_status", "planning_runs", ["status"])

    op.create_table(
        "production_planning_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("input_revision", sa.BigInteger(), nullable=False),
        sa.Column("requested_revision", sa.BigInteger(), nullable=False),
        sa.Column("active_run_id", sa.Integer(), nullable=True),
        sa.Column("calculation_status", sa.String(length=16), nullable=False),
        sa.Column("running_revision", sa.BigInteger(), nullable=True),
        sa.Column("worker_heartbeat_at", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "calculation_status IN ('idle', 'pending', 'running', 'error')",
            name="ck_production_planning_state_status",
        ),
        sa.ForeignKeyConstraint(
            ["active_run_id"],
            ["planning_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "planning_order_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("resource_finish_date", sa.Date(), nullable=True),
        sa.Column("calculated_finish_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("issue_codes", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["work_orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["planning_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "order_id",
            name="uq_planning_order_results_run_order",
        ),
    )
    op.create_index(
        "ix_planning_order_results_order_id",
        "planning_order_results",
        ["order_id"],
    )
    op.create_index(
        "ix_planning_order_results_run_id",
        "planning_order_results",
        ["run_id"],
    )

    op.create_table(
        "planning_operation_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("workload_seconds", sa.BigInteger(), nullable=False),
        sa.Column("actual_seconds", sa.BigInteger(), nullable=False),
        sa.Column("remaining_seconds", sa.BigInteger(), nullable=False),
        sa.Column("preparation_seconds", sa.BigInteger(), nullable=False),
        sa.Column("first_planned_date", sa.Date(), nullable=True),
        sa.Column("last_planned_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("issue_codes", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["operations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["work_orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["planning_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "order_id",
            "operation_id",
            name="uq_planning_operation_results_run_order_operation",
        ),
    )
    op.create_index(
        "ix_planning_operation_results_operation_id",
        "planning_operation_results",
        ["operation_id"],
    )
    op.create_index(
        "ix_planning_operation_results_order_id",
        "planning_operation_results",
        ["order_id"],
    )
    op.create_index(
        "ix_planning_operation_results_run_id",
        "planning_operation_results",
        ["run_id"],
    )

    op.create_table(
        "planning_worker_day_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("work_seconds", sa.BigInteger(), nullable=False),
        sa.Column("preparation_seconds", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "preparation_seconds >= 0",
            name="ck_planning_worker_day_allocations_preparation",
        ),
        sa.CheckConstraint(
            "work_seconds >= 0",
            name="ck_planning_worker_day_allocations_work",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["operations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["work_orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["planning_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "user_id",
            "work_date",
            "order_id",
            "operation_id",
            name="uq_planning_worker_day_allocations_task",
        ),
    )
    op.create_index(
        "ix_planning_worker_day_allocations_operation_id",
        "planning_worker_day_allocations",
        ["operation_id"],
    )
    op.create_index(
        "ix_planning_worker_day_allocations_order_id",
        "planning_worker_day_allocations",
        ["order_id"],
    )
    op.create_index(
        "ix_planning_worker_day_allocations_run_id",
        "planning_worker_day_allocations",
        ["run_id"],
    )
    op.create_index(
        "ix_planning_worker_day_allocations_user_id",
        "planning_worker_day_allocations",
        ["user_id"],
    )
    op.create_index(
        "ix_planning_worker_day_allocations_work_date",
        "planning_worker_day_allocations",
        ["work_date"],
    )

    now = int(datetime.now(UTC).timestamp() * 1000)
    op.execute(
        sa.text(
            """
            INSERT INTO production_planning_state (
                id,
                input_revision,
                requested_revision,
                active_run_id,
                calculation_status,
                running_revision,
                worker_heartbeat_at,
                updated_at
            ) VALUES (1, 1, 1, NULL, 'pending', NULL, NULL, :updated_at)
            """
        ).bindparams(updated_at=now)
    )


def downgrade() -> None:
    op.drop_index(
        "ix_planning_worker_day_allocations_work_date",
        table_name="planning_worker_day_allocations",
    )
    op.drop_index(
        "ix_planning_worker_day_allocations_user_id",
        table_name="planning_worker_day_allocations",
    )
    op.drop_index(
        "ix_planning_worker_day_allocations_run_id",
        table_name="planning_worker_day_allocations",
    )
    op.drop_index(
        "ix_planning_worker_day_allocations_order_id",
        table_name="planning_worker_day_allocations",
    )
    op.drop_index(
        "ix_planning_worker_day_allocations_operation_id",
        table_name="planning_worker_day_allocations",
    )
    op.drop_table("planning_worker_day_allocations")
    op.drop_index(
        "ix_planning_operation_results_run_id",
        table_name="planning_operation_results",
    )
    op.drop_index(
        "ix_planning_operation_results_order_id",
        table_name="planning_operation_results",
    )
    op.drop_index(
        "ix_planning_operation_results_operation_id",
        table_name="planning_operation_results",
    )
    op.drop_table("planning_operation_results")
    op.drop_index(
        "ix_planning_order_results_run_id",
        table_name="planning_order_results",
    )
    op.drop_index(
        "ix_planning_order_results_order_id",
        table_name="planning_order_results",
    )
    op.drop_table("planning_order_results")
    op.drop_table("production_planning_state")
    op.drop_index("ix_planning_runs_status", table_name="planning_runs")
    op.drop_index(
        "ix_planning_runs_input_revision",
        table_name="planning_runs",
    )
    op.drop_table("planning_runs")

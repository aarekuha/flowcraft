"""add production planning priority queue

Revision ID: 20261105_0028
Revises: 20261105_0027
Create Date: 2026-11-05 10:30:00
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20261105_0028"
down_revision = "20261105_0027"
branch_labels = None
depends_on = None

PRIORITY_RANK_STEP = 1024


def upgrade() -> None:
    op.add_column(
        "work_orders",
        sa.Column("planning_priority_rank", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "work_orders",
        sa.Column("planning_excluded_at", sa.BigInteger(), nullable=True),
    )

    connection = op.get_bind()
    work_orders = sa.table(
        "work_orders",
        sa.column("id", sa.Integer()),
        sa.column("created_at", sa.BigInteger()),
        sa.column("updated_at", sa.BigInteger()),
        sa.column("completed_at", sa.BigInteger()),
        sa.column("planning_priority_rank", sa.BigInteger()),
        sa.column("planning_excluded_at", sa.BigInteger()),
    )
    rows = connection.execute(
        sa.select(
            work_orders.c.id,
            work_orders.c.created_at,
            work_orders.c.updated_at,
            work_orders.c.completed_at,
        ).order_by(work_orders.c.created_at.asc(), work_orders.c.id.asc())
    ).all()
    for position, row in enumerate(rows, start=1):
        connection.execute(
            work_orders.update()
            .where(work_orders.c.id == row.id)
            .values(
                planning_priority_rank=position * PRIORITY_RANK_STEP,
                planning_excluded_at=(
                    row.completed_at
                    if row.completed_at is not None
                    else None
                ),
            )
        )

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.alter_column(
            "planning_priority_rank",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
    op.create_index(
        "ix_work_orders_planning_queue",
        "work_orders",
        [
            "planning_excluded_at",
            "deleted_at",
            "completed_at",
            "planning_priority_rank",
        ],
    )

    op.create_table(
        "planning_queue_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO planning_queue_state (
                id,
                revision,
                updated_at,
                updated_by_user_id
            ) VALUES (1, 0, :updated_at, NULL)
            """
        ).bindparams(updated_at=int(datetime.now(UTC).timestamp() * 1000))
    )


def downgrade() -> None:
    op.drop_table("planning_queue_state")
    op.drop_index("ix_work_orders_planning_queue", table_name="work_orders")
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("planning_excluded_at")
        batch_op.drop_column("planning_priority_rank")

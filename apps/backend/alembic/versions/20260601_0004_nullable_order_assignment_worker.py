"""allow empty work order assignment worker

Revision ID: 20260601_0004
Revises: 20260531_0003
Create Date: 2026-06-01 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260601_0004"
down_revision = "20260531_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_order_assignments") as batch_op:
        batch_op.alter_column(
            "worker_user_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("work_order_assignments") as batch_op:
        batch_op.alter_column(
            "worker_user_id",
            existing_type=sa.Integer(),
            nullable=False,
        )

"""add work order lifecycle timestamps

Revision ID: 20260601_0005
Revises: 20260601_0004
Create Date: 2026-06-01 12:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260601_0005"
down_revision = "20260601_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(sa.Column("taken_at", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.BigInteger(), nullable=True))

    op.execute(
        "UPDATE work_orders SET taken_at = created_at WHERE taken_at IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("taken_at")

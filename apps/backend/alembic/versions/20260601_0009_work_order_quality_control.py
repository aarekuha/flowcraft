"""add work order quality control stage

Revision ID: 20260601_0009
Revises: 20260601_0008
Create Date: 2026-06-01 17:10:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260601_0009"
down_revision = "20260601_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(
            sa.Column("quality_control_at", sa.BigInteger(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "defect_quantity",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    op.execute(
        """
        UPDATE work_orders
        SET quality_control_at = completed_at
        WHERE completed_at IS NOT NULL
          AND quality_control_at IS NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("defect_quantity")
        batch_op.drop_column("quality_control_at")

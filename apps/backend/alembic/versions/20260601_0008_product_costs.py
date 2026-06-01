"""add product and operation costs

Revision ID: 20260601_0008
Revises: 20260601_0007
Create Date: 2026-06-01 16:30:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260601_0008"
down_revision = "20260601_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column("material_cost_cents", sa.Integer(), nullable=True)
        )

    with op.batch_alter_table("operations") as batch_op:
        batch_op.add_column(sa.Column("price_cents", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("operations") as batch_op:
        batch_op.drop_column("price_cents")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("material_cost_cents")

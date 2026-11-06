"""add product production stages

Revision ID: 20261104_0026
Revises: 20261104_0025
Create Date: 2026-11-04 23:30:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20261104_0026"
down_revision = "20261104_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column(
                "stage_count",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.create_check_constraint(
            "ck_products_stage_count",
            "stage_count >= 1",
        )

    with op.batch_alter_table("operations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "stage_start",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "stage_end",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.create_check_constraint(
            "ck_operations_stage_start",
            "stage_start >= 1",
        )
        batch_op.create_check_constraint(
            "ck_operations_stage_end",
            "stage_end >= stage_start",
        )


def downgrade() -> None:
    with op.batch_alter_table("operations") as batch_op:
        batch_op.drop_constraint(
            "ck_operations_stage_end",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_operations_stage_start",
            type_="check",
        )
        batch_op.drop_column("stage_end")
        batch_op.drop_column("stage_start")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint(
            "ck_products_stage_count",
            type_="check",
        )
        batch_op.drop_column("stage_count")

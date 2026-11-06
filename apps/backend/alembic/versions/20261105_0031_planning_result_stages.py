"""store stages in planning operation results

Revision ID: 20261105_0031
Revises: 20261105_0030
Create Date: 2026-11-05 17:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20261105_0031"
down_revision = "20261105_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "planning_operation_results",
        sa.Column("stage_start", sa.Integer(), nullable=True),
    )
    op.add_column(
        "planning_operation_results",
        sa.Column("stage_end", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE planning_operation_results
            SET
                stage_start = COALESCE(
                    (
                        SELECT operations.stage_start
                        FROM operations
                        WHERE operations.id = planning_operation_results.operation_id
                    ),
                    1
                ),
                stage_end = COALESCE(
                    (
                        SELECT operations.stage_end
                        FROM operations
                        WHERE operations.id = planning_operation_results.operation_id
                    ),
                    1
                )
            """
        )
    )
    with op.batch_alter_table("planning_operation_results") as batch_op:
        batch_op.alter_column(
            "stage_start",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "stage_end",
            existing_type=sa.Integer(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("planning_operation_results") as batch_op:
        batch_op.drop_column("stage_end")
        batch_op.drop_column("stage_start")

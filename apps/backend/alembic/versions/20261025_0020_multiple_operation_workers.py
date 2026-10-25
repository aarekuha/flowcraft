"""allow multiple workers per work order operation

Revision ID: 20261025_0020
Revises: 20261025_0019
Create Date: 2026-10-25 15:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20261025_0020"
down_revision = "20261025_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_order_assignments") as batch_op:
        batch_op.drop_constraint(
            "uq_work_order_assignments_work_order_operation",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_work_order_assignments_order_operation_worker",
            ["work_order_id", "operation_id", "worker_user_id"],
        )


def downgrade() -> None:
    connection = op.get_bind()
    duplicate_assignment_ids = connection.execute(
        sa.text(
            """
            SELECT duplicate.id
            FROM work_order_assignments AS duplicate
            WHERE duplicate.id NOT IN (
                SELECT MIN(original.id)
                FROM work_order_assignments AS original
                GROUP BY original.work_order_id, original.operation_id
            )
            """
        )
    ).scalars().all()
    if duplicate_assignment_ids:
        connection.execute(
            sa.text(
                """
                DELETE FROM work_order_assignment_worker_states
                WHERE assignment_id IN :assignment_ids
                """
            ).bindparams(
                sa.bindparam(
                    "assignment_ids",
                    expanding=True,
                    value=duplicate_assignment_ids,
                )
            )
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM work_order_assignments
                WHERE id IN :assignment_ids
                """
            ).bindparams(
                sa.bindparam(
                    "assignment_ids",
                    expanding=True,
                    value=duplicate_assignment_ids,
                )
            )
        )

    with op.batch_alter_table("work_order_assignments") as batch_op:
        batch_op.drop_constraint(
            "uq_work_order_assignments_order_operation_worker",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_work_order_assignments_work_order_operation",
            ["work_order_id", "operation_id"],
        )

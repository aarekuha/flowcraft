"""add work order planned completion date

Revision ID: 20260911_0014
Revises: 20260831_0013
Create Date: 2026-09-11 12:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260911_0014"
down_revision = "20260831_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "work_orders" not in inspector.get_table_names() or _has_column(
        bind,
        "work_orders",
        "planned_completion_date",
    ):
        return

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(
            sa.Column("planned_completion_date", sa.Date(), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "work_orders" not in inspector.get_table_names() or not _has_column(
        bind,
        "work_orders",
        "planned_completion_date",
    ):
        return

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("planned_completion_date")


def _has_column(
    bind: sa.engine.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )

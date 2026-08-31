"""add operation standard time

Revision ID: 20260831_0013
Revises: 20260609_0012
Create Date: 2026-08-31 12:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260831_0013"
down_revision = "20260609_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "operations" not in inspector.get_table_names() or _has_column(
        bind,
        "operations",
        "standard_time_seconds",
    ):
        return

    with op.batch_alter_table("operations") as batch_op:
        batch_op.add_column(
            sa.Column("standard_time_seconds", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "operations" not in inspector.get_table_names() or not _has_column(
        bind,
        "operations",
        "standard_time_seconds",
    ):
        return

    with op.batch_alter_table("operations") as batch_op:
        batch_op.drop_column("standard_time_seconds")


def _has_column(
    bind: sa.engine.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )

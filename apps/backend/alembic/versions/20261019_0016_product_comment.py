"""add product comment

Revision ID: 20261019_0016
Revises: 20261019_0015
Create Date: 2026-10-19 22:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20261019_0016"
down_revision = "20261019_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "products" not in inspector.get_table_names() or _has_column(
        bind,
        "products",
        "comment",
    ):
        return

    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(sa.Column("comment", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "products" not in inspector.get_table_names() or not _has_column(
        bind,
        "products",
        "comment",
    ):
        return

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("comment")


def _has_column(
    bind: sa.engine.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )

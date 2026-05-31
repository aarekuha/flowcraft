"""add leather types

Revision ID: 20260531_0003
Revises: 20260530_0002
Create Date: 2026-05-31 12:10:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260531_0003"
down_revision = "20260530_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table_names = inspector.get_table_names()

    if "leather_types" not in table_names:
        op.create_table(
            "leather_types",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name="uq_leather_types_name"),
        )

    work_order_columns = {
        column["name"] for column in inspector.get_columns("work_orders")
    }
    if "leather_type_id" not in work_order_columns:
        with op.batch_alter_table("work_orders") as batch_op:
            batch_op.add_column(
                sa.Column("leather_type_id", sa.Integer(), nullable=True),
            )
            batch_op.create_index(
                "ix_work_orders_leather_type_id",
                ["leather_type_id"],
                unique=False,
            )
            batch_op.create_foreign_key(
                "fk_work_orders_leather_type_id",
                "leather_types",
                ["leather_type_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "leather_type_id" in {
        column["name"] for column in inspector.get_columns("work_orders")
    }:
        with op.batch_alter_table("work_orders") as batch_op:
            batch_op.drop_constraint(
                "fk_work_orders_leather_type_id",
                type_="foreignkey",
            )
            batch_op.drop_index("ix_work_orders_leather_type_id")
            batch_op.drop_column("leather_type_id")

    if "leather_types" in inspector.get_table_names():
        op.drop_table("leather_types")

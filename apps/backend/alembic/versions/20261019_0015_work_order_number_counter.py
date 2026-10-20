"""add work order number counter

Revision ID: 20261019_0015
Revises: 20260911_0014
Create Date: 2026-10-19 21:30:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20261019_0015"
down_revision = "20260911_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "work_order_number_counters" not in table_names:
        op.create_table(
            "work_order_number_counters",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("last_value", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    counter_table = sa.table(
        "work_order_number_counters",
        sa.column("id", sa.Integer()),
        sa.column("last_value", sa.Integer()),
    )
    existing_counter = bind.execute(
        sa.select(counter_table.c.id).where(counter_table.c.id == 1)
    ).scalar_one_or_none()
    if existing_counter is not None:
        return

    last_value = 9999
    if "work_orders" in table_names:
        work_orders_table = sa.table(
            "work_orders",
            sa.column("order_number", sa.String()),
        )
        order_numbers = bind.execute(
            sa.select(work_orders_table.c.order_number)
        ).scalars()
        numeric_order_numbers = [
            int(order_number.strip())
            for order_number in order_numbers
            if order_number.strip().isdecimal()
        ]
        if numeric_order_numbers:
            last_value = max(last_value, *numeric_order_numbers)

    bind.execute(counter_table.insert().values(id=1, last_value=last_value))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "work_order_number_counters" in inspector.get_table_names():
        op.drop_table("work_order_number_counters")

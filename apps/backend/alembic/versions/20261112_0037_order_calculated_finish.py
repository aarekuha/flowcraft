"""Persist calculated finish dates on orders"""

import sqlalchemy as sa

from alembic import op

revision = "20261112_0037"
down_revision = "20261111_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_orders", sa.Column("calculated_finish_date", sa.Date(), nullable=True),
    )
    op.execute(sa.text("""
        UPDATE work_orders
        SET calculated_finish_date = (
            SELECT result.calculated_finish_date
            FROM planning_order_results AS result
            JOIN production_planning_state AS state
                ON state.active_run_id = result.run_id AND state.id = 1
            WHERE result.order_id = work_orders.id
        )
    """))


def downgrade() -> None:
    op.drop_column("work_orders", "calculated_finish_date")

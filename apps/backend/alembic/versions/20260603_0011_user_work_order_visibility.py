"""add user work order visibility

Revision ID: 20260603_0011
Revises: 20260601_0010
Create Date: 2026-06-03 12:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20260603_0011"
down_revision = "20260601_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_work_order_visibility",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_work_order_visibility_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
            name="fk_user_work_order_visibility_work_order_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "work_order_id",
            name="pk_user_work_order_visibility",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_work_order_visibility")

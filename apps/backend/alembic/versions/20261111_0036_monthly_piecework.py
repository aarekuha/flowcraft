"""Store monthly manual piecework amounts"""

import sqlalchemy as sa

from alembic import op

revision = "20261111_0036"
down_revision = "20261110_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_piecework",
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("month", sa.Integer(), primary_key=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("year BETWEEN 2000 AND 9998", name="ck_piecework_year"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_piecework_month"),
        sa.CheckConstraint("amount_cents >= 0", name="ck_piecework_amount"),
    )


def downgrade() -> None:
    op.drop_table("monthly_piecework")

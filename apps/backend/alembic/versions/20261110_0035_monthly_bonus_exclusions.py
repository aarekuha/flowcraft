"""Store excluded employee bonuses per month"""

import sqlalchemy as sa

from alembic import op

revision = "20261110_0035"
down_revision = "20261110_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_bonus_exclusions",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("month", sa.Integer(), primary_key=True),
        sa.Column(
            "bonus_id",
            sa.Integer(),
            sa.ForeignKey("bonuses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.CheckConstraint(
            "year BETWEEN 2000 AND 9998", name="ck_bonus_exclusion_year"
        ),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_bonus_exclusion_month"),
    )


def downgrade() -> None:
    op.drop_table("monthly_bonus_exclusions")

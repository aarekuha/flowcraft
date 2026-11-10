"""Add bonus directory and employee assignments"""

import sqlalchemy as sa

from alembic import op

revision = "20261110_0034"
down_revision = "20261110_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bonuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("amount_cents >= 0", name="ck_bonus_amount"),
    )
    op.create_table(
        "user_bonuses",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "bonus_id",
            sa.Integer(),
            sa.ForeignKey("bonuses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_bonuses")
    op.drop_table("bonuses")

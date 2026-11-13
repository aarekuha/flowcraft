"""Add personal work report visibility setting"""

import sqlalchemy as sa

from alembic import op

revision = "20261113_0046"
down_revision = "20261113_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "planning_settings",
        sa.Column(
            "show_personal_work_report",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("planning_settings") as batch:
        batch.drop_column("show_personal_work_report")

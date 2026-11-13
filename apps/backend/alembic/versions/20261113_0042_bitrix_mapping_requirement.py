"""Store products that do not require Bitrix mapping"""

import sqlalchemy as sa

from alembic import op

revision = "20261113_0042"
down_revision = "20261113_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "bitrix_mapping_not_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.drop_column("bitrix_mapping_not_required")

"""Store Bitrix deals and their product rows"""

import sqlalchemy as sa

from alembic import op

revision = "20261113_0040"
down_revision = "20261112_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bitrix_connection", sa.Column("job_kind", sa.String(20)))
    op.add_column(
        "bitrix_connection",
        sa.Column("deals_metadata", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column("bitrix_connection", sa.Column("deals_synced_at", sa.BigInteger()))
    op.add_column("bitrix_connection", sa.Column("deals_last_error", sa.String(500)))
    op.create_table(
        "bitrix_deals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("stage_id", sa.String(100), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("product_rows", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_bitrix_deals_category_id", "bitrix_deals", ["category_id"])
    op.create_index("ix_bitrix_deals_closed", "bitrix_deals", ["closed"])


def downgrade() -> None:
    op.drop_table("bitrix_deals")
    with op.batch_alter_table("bitrix_connection") as batch:
        for name in (
            "job_kind",
            "deals_metadata",
            "deals_synced_at",
            "deals_last_error",
        ):
            batch.drop_column(name)

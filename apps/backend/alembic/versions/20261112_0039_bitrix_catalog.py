"""Store Bitrix catalog, prices, credentials and product mappings"""

import sqlalchemy as sa

from alembic import op

revision = "20261112_0039"
down_revision = "20261112_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bitrix_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portal", sa.String(255), nullable=False),
        sa.Column("encrypted_webhook", sa.Text(), nullable=False),
        sa.Column("catalog_metadata", sa.JSON(), nullable=False),
        sa.Column("synced_at", sa.BigInteger()),
        sa.Column("job_id", sa.String(36)),
        sa.Column("started_at", sa.BigInteger()),
        sa.Column("last_error", sa.String(500)),
    )
    op.create_table(
        "bitrix_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("parent_id", sa.Integer()),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("prices", sa.JSON(), nullable=False),
    )
    op.create_index("ix_bitrix_products_catalog_id", "bitrix_products", ["catalog_id"])
    op.create_table(
        "bitrix_mappings",
        sa.Column(
            "bitrix_id",
            sa.Integer(),
            sa.ForeignKey("bitrix_products.id"),
            primary_key=True,
        ),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_bitrix_mappings_product_id", "bitrix_mappings", ["product_id"])


def downgrade() -> None:
    op.drop_table("bitrix_mappings")
    op.drop_table("bitrix_products")
    op.drop_table("bitrix_connection")

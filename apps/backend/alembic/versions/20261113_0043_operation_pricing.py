# ruff: noqa: I001
"""Replace manual operation prices with hourly rate and coefficients"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "20261113_0043"
down_revision = "20261113_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "planning_settings",
        sa.Column(
            "base_rate_cents", sa.Integer(), nullable=False, server_default="35000"
        ),
    )
    op.add_column(
        "operations",
        sa.Column(
            "coefficient_units", sa.BigInteger(), nullable=False, server_default="10000"
        ),
    )
    op.create_table(
        "operation_price_migration_report",
        sa.Column("operation_id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("operation_name", sa.Text(), nullable=False),
        sa.Column("old_price_cents", sa.BigInteger()),
        sa.Column("seconds_per_item", sa.Integer()),
        sa.Column("coefficient_units", sa.BigInteger(), nullable=False),
        sa.Column("new_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("delta_cents", sa.BigInteger()),
    )
    path = (
        Path(__file__).resolve().parents[2] / "scripts" / "migrate_operation_pricing.py"
    )
    spec = importlib.util.spec_from_file_location("pricing_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.migrate(op.get_bind())


def downgrade() -> None:
    op.execute(
        "UPDATE operations SET price_cents=(SELECT old_price_cents "
        "FROM operation_price_migration_report r WHERE r.operation_id=operations.id) "
        "WHERE id IN (SELECT operation_id FROM operation_price_migration_report)"
    )
    op.drop_table("operation_price_migration_report")
    with op.batch_alter_table("operations") as batch:
        batch.drop_column("coefficient_units")
    with op.batch_alter_table("planning_settings") as batch:
        batch.drop_column("base_rate_cents")

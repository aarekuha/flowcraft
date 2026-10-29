"""add adjacent operation kind

Revision ID: 20261028_0021
Revises: 20261025_0020
Create Date: 2026-10-28 10:00:00
"""

from alembic import op

revision = "20261028_0021"
down_revision = "20261025_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("operation_catalog_entries") as batch_op:
        batch_op.drop_constraint(
            "ck_operation_catalog_entries_kind",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_operation_catalog_entries_kind",
            "operation_kind IN ('regular', 'cutting', 'adjacent')",
        )


def downgrade() -> None:
    op.execute(
        """
        UPDATE operation_catalog_entries
        SET operation_kind = 'regular'
        WHERE operation_kind = 'adjacent'
        """
    )
    with op.batch_alter_table("operation_catalog_entries") as batch_op:
        batch_op.drop_constraint(
            "ck_operation_catalog_entries_kind",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_operation_catalog_entries_kind",
            "operation_kind IN ('regular', 'cutting')",
        )

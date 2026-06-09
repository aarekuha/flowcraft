"""allow operation groups without catalog entries

Revision ID: 20260609_0012
Revises: 20260608_0011
Create Date: 2026-06-09 12:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260609_0012"
down_revision = "20260608_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "operations" not in table_names or not _has_column(
        bind,
        "operations",
        "operation_catalog_entry_id",
    ):
        return

    with op.batch_alter_table("operations") as batch_op:
        batch_op.alter_column(
            "operation_catalog_entry_id",
            existing_type=sa.Integer(),
            nullable=True,
        )

    bind.execute(
        sa.text(
            """
            UPDATE operations
            SET operation_catalog_entry_id = NULL
            WHERE EXISTS (
                SELECT 1
                FROM operations AS child
                WHERE child.parent_id = operations.id
            )
            """
        )
    )

    _validate_leaf_operation_catalog_ids(bind)
    _validate_product_leaf_operation_uniqueness(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "operations" not in table_names or not _has_column(
        bind,
        "operations",
        "operation_catalog_entry_id",
    ):
        return

    missing_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM operations
            WHERE operation_catalog_entry_id IS NULL
            """
        )
    ).scalar_one()
    if missing_count:
        raise RuntimeError(
            "Cannot downgrade operations: some rows do not map to operation catalog."
        )

    with op.batch_alter_table("operations") as batch_op:
        batch_op.alter_column(
            "operation_catalog_entry_id",
            existing_type=sa.Integer(),
            nullable=False,
        )


def _validate_leaf_operation_catalog_ids(bind: sa.engine.Connection) -> None:
    missing_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM operations
            WHERE operation_catalog_entry_id IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM operations AS child
                  WHERE child.parent_id = operations.id
              )
            """
        )
    ).scalar_one()
    if missing_count:
        raise RuntimeError(
            "Cannot migrate operations: some leaf rows do not map to operation catalog."
        )


def _validate_product_leaf_operation_uniqueness(
    bind: sa.engine.Connection,
) -> None:
    duplicate_rows = bind.execute(
        sa.text(
            """
            SELECT product_id, operation_catalog_entry_id, COUNT(*) AS rows_count
            FROM operations
            WHERE operation_catalog_entry_id IS NOT NULL
            GROUP BY product_id, operation_catalog_entry_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if duplicate_rows:
        raise RuntimeError(
            "Cannot migrate operations: duplicate operation names exist within a "
            "single product."
        )


def _has_column(
    bind: sa.engine.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )

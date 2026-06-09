"""add operation catalog and worker assignment states

Revision ID: 20260608_0011
Revises: 20260603_0011
Create Date: 2026-06-08 12:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260608_0011"
down_revision = "20260603_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "operation_catalog_entries" not in table_names:
        op.create_table(
            "operation_catalog_entries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "name",
                name="uq_operation_catalog_entries_name",
            ),
        )

    if "operations" in table_names:
        _backfill_operation_catalog_entries(bind)
        _add_operation_catalog_column_if_needed(bind)
        _backfill_operations_catalog_ids(bind)
        _validate_operations_catalog_ids(bind)
        _validate_product_operation_uniqueness(bind)
        _add_assignment_catalog_temp_column_if_needed(bind, table_names)
        _backfill_assignment_catalog_temp_ids(bind, table_names)
        _validate_assignment_catalog_temp_ids(bind, table_names)
        _enforce_operation_catalog_constraints(bind)
        _drop_assignment_catalog_temp_column_if_needed(bind, table_names)

    if "work_order_assignment_worker_states" not in table_names:
        op.create_table(
            "work_order_assignment_worker_states",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("assignment_id", sa.Integer(), nullable=False),
            sa.Column("worker_user_id", sa.Integer(), nullable=False),
            sa.Column("hidden_at", sa.BigInteger(), nullable=True),
            sa.Column("completed_at", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.ForeignKeyConstraint(
                ["assignment_id"],
                ["work_order_assignments.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["worker_user_id"],
                ["users.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "assignment_id",
                "worker_user_id",
                name="uq_work_order_assignment_worker_states_assignment_worker",
            ),
        )
        op.create_index(
            "ix_work_order_assignment_worker_states_assignment_id",
            "work_order_assignment_worker_states",
            ["assignment_id"],
            unique=False,
        )
        op.create_index(
            "ix_work_order_assignment_worker_states_worker_user_id",
            "work_order_assignment_worker_states",
            ["worker_user_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "work_order_assignment_worker_states" in table_names:
        op.drop_index(
            "ix_work_order_assignment_worker_states_worker_user_id",
            table_name="work_order_assignment_worker_states",
        )
        op.drop_index(
            "ix_work_order_assignment_worker_states_assignment_id",
            table_name="work_order_assignment_worker_states",
        )
        op.drop_table("work_order_assignment_worker_states")

    if "operations" in table_names and _has_column(
        bind,
        "operations",
        "operation_catalog_entry_id",
    ):
        with op.batch_alter_table("operations") as batch_op:
            batch_op.drop_constraint(
                "uq_operations_product_catalog_entry",
                type_="unique",
            )
            batch_op.drop_constraint(
                "fk_operations_operation_catalog_entry_id",
                type_="foreignkey",
            )
            batch_op.drop_index("ix_operations_operation_catalog_entry_id")
            batch_op.drop_column("operation_catalog_entry_id")

    if "operation_catalog_entries" in table_names:
        op.drop_table("operation_catalog_entries")


def _backfill_operation_catalog_entries(bind: sa.engine.Connection) -> None:
    now_ts = 1
    bind.execute(
        sa.text(
            """
            INSERT INTO operation_catalog_entries
                (name, is_active, created_at, updated_at)
            SELECT DISTINCT TRIM(operations.name), 1, :created_at, :updated_at
            FROM operations
            WHERE TRIM(operations.name) <> ''
              AND NOT EXISTS (
                  SELECT 1
                  FROM operations AS child
                  WHERE child.parent_id = operations.id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM operation_catalog_entries
                  WHERE operation_catalog_entries.name = TRIM(operations.name)
              )
            ORDER BY TRIM(operations.name)
            """
        ),
        {"created_at": now_ts, "updated_at": now_ts},
    )


def _add_operation_catalog_column_if_needed(bind: sa.engine.Connection) -> None:
    if _has_column(bind, "operations", "operation_catalog_entry_id"):
        return

    op.add_column(
        "operations",
        sa.Column("operation_catalog_entry_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_operations_operation_catalog_entry_id",
        "operations",
        ["operation_catalog_entry_id"],
        unique=False,
    )


def _backfill_operations_catalog_ids(bind: sa.engine.Connection) -> None:
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
    bind.execute(
        sa.text(
            """
            UPDATE operations
            SET operation_catalog_entry_id = (
                SELECT operation_catalog_entries.id
                FROM operation_catalog_entries
                WHERE operation_catalog_entries.name = TRIM(operations.name)
            )
            WHERE operation_catalog_entry_id IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM operations AS child
                  WHERE child.parent_id = operations.id
              )
            """
        )
    )


def _validate_operations_catalog_ids(bind: sa.engine.Connection) -> None:
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
            "Cannot migrate operations: some rows do not map to operation catalog."
        )


def _validate_product_operation_uniqueness(bind: sa.engine.Connection) -> None:
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


def _add_assignment_catalog_temp_column_if_needed(
    bind: sa.engine.Connection,
    table_names: list[str],
) -> None:
    if "work_order_assignments" not in table_names:
        return
    if _has_column(bind, "work_order_assignments", "operation_catalog_entry_id"):
        return

    op.add_column(
        "work_order_assignments",
        sa.Column("operation_catalog_entry_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_work_order_assignments_operation_catalog_entry_id",
        "work_order_assignments",
        ["operation_catalog_entry_id"],
        unique=False,
    )


def _backfill_assignment_catalog_temp_ids(
    bind: sa.engine.Connection,
    table_names: list[str],
) -> None:
    if "work_order_assignments" not in table_names:
        return
    if not _has_column(bind, "work_order_assignments", "operation_catalog_entry_id"):
        return

    bind.execute(
        sa.text(
            """
            UPDATE work_order_assignments
            SET operation_catalog_entry_id = (
                SELECT operations.operation_catalog_entry_id
                FROM operations
                WHERE operations.id = work_order_assignments.operation_id
            )
            WHERE operation_catalog_entry_id IS NULL
            """
        )
    )


def _validate_assignment_catalog_temp_ids(
    bind: sa.engine.Connection,
    table_names: list[str],
) -> None:
    if "work_order_assignments" not in table_names:
        return
    if not _has_column(bind, "work_order_assignments", "operation_catalog_entry_id"):
        return

    missing_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM work_order_assignments
            WHERE operation_catalog_entry_id IS NULL
            """
        )
    ).scalar_one()
    if missing_count:
        raise RuntimeError(
            "Cannot migrate assignments: some rows do not map to operation catalog."
        )


def _enforce_operation_catalog_constraints(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("operations")
    }
    foreign_keys = {
        foreign_key["name"] for foreign_key in inspector.get_foreign_keys("operations")
    }

    with op.batch_alter_table("operations") as batch_op:
        batch_op.alter_column(
            "operation_catalog_entry_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        if "fk_operations_operation_catalog_entry_id" not in foreign_keys:
            batch_op.create_foreign_key(
                "fk_operations_operation_catalog_entry_id",
                "operation_catalog_entries",
                ["operation_catalog_entry_id"],
                ["id"],
            )
        if "uq_operations_product_catalog_entry" not in unique_constraints:
            batch_op.create_unique_constraint(
                "uq_operations_product_catalog_entry",
                ["product_id", "operation_catalog_entry_id"],
            )


def _drop_assignment_catalog_temp_column_if_needed(
    bind: sa.engine.Connection,
    table_names: list[str],
) -> None:
    if "work_order_assignments" not in table_names:
        return
    if not _has_column(bind, "work_order_assignments", "operation_catalog_entry_id"):
        return

    with op.batch_alter_table("work_order_assignments") as batch_op:
        batch_op.drop_index("ix_work_order_assignments_operation_catalog_entry_id")
        batch_op.drop_column("operation_catalog_entry_id")


def _has_column(
    bind: sa.engine.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )

"""add work order split and merge structures

Revision ID: 20261025_0018
Revises: 20261025_0017
Create Date: 2026-10-25 13:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20261025_0018"
down_revision = "20261025_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operation_catalog_entries",
        sa.Column(
            "operation_kind",
            sa.String(length=16),
            nullable=False,
            server_default="regular",
        ),
    )
    with op.batch_alter_table("operation_catalog_entries") as batch_op:
        batch_op.create_check_constraint(
            "ck_operation_catalog_entries_kind",
            "operation_kind IN ('regular', 'cutting')",
        )

    op.create_table(
        "work_order_families",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("base_order_number", sa.String(length=64), nullable=False),
        sa.Column(
            "last_part_number",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "last_part_number >= 1",
            name="ck_work_order_families_last_part_number",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "base_order_number",
            name="uq_work_order_families_base_order_number",
        ),
    )

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(sa.Column("family_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("part_number", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_work_orders_family_id",
            "work_order_families",
            ["family_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_work_orders_family_part_number",
            ["family_id", "part_number"],
        )
        batch_op.create_check_constraint(
            "ck_work_orders_part_number",
            "part_number IS NULL OR part_number >= 1",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_family_part_consistency",
            "(family_id IS NULL AND part_number IS NULL) OR "
            "(family_id IS NOT NULL AND part_number IS NOT NULL)",
        )
        batch_op.create_index("ix_work_orders_family_id", ["family_id"])

    op.create_table(
        "work_order_time_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timer_session_id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("allocated_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "allocated_seconds >= 0",
            name="ck_work_order_time_allocations_seconds",
        ),
        sa.ForeignKeyConstraint(
            ["timer_session_id"],
            ["timer_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "timer_session_id",
            "work_order_id",
            name="uq_work_order_time_allocations_session_order",
        ),
    )
    op.create_index(
        "ix_work_order_time_allocations_timer_session_id",
        "work_order_time_allocations",
        ["timer_session_id"],
    )
    op.create_index(
        "ix_work_order_time_allocations_work_order_id",
        "work_order_time_allocations",
        ["work_order_id"],
    )

    op.create_table(
        "work_order_qr_references",
        sa.Column("legacy_order_id", sa.Integer(), nullable=False),
        sa.Column("order_reference", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("legacy_order_id"),
    )
    op.create_index(
        "ix_work_order_qr_references_order_reference",
        "work_order_qr_references",
        ["order_reference"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_work_order_qr_references_order_reference",
        table_name="work_order_qr_references",
    )
    op.drop_table("work_order_qr_references")

    op.drop_index(
        "ix_work_order_time_allocations_work_order_id",
        table_name="work_order_time_allocations",
    )
    op.drop_index(
        "ix_work_order_time_allocations_timer_session_id",
        table_name="work_order_time_allocations",
    )
    op.drop_table("work_order_time_allocations")

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_index("ix_work_orders_family_id")
        batch_op.drop_constraint(
            "ck_work_orders_family_part_consistency",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_work_orders_part_number",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_work_orders_family_part_number",
            type_="unique",
        )
        batch_op.drop_constraint("fk_work_orders_family_id", type_="foreignkey")
        batch_op.drop_column("part_number")
        batch_op.drop_column("family_id")

    op.drop_table("work_order_families")

    with op.batch_alter_table("operation_catalog_entries") as batch_op:
        batch_op.drop_constraint(
            "ck_operation_catalog_entries_kind",
            type_="check",
        )
        batch_op.drop_column("operation_kind")

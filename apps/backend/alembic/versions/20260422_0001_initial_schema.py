"""initial schema

Revision ID: 20260422_0001
Revises:
Create Date: 2026-04-22 23:59:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260422_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("deleted_at", sa.BigInteger(), nullable=True),
        sa.Column("author_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_products_name_version"),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_name", sa.String(length=255), nullable=False),
        sa.Column("user_roles", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("last_seen_at", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("idle_expires_at", sa.BigInteger(), nullable=False),
        sa.Column("revoked_at", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_auth_sessions_token"),
    )
    op.create_index("ix_auth_sessions_token", "auth_sessions", ["token"], unique=False)
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)
    op.create_index(
        "ix_auth_sessions_revoked_at",
        "auth_sessions",
        ["revoked_at"],
        unique=False,
    )

    op.create_table(
        "operations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["operations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operations_parent_id", "operations", ["parent_id"], unique=False)
    op.create_index("ix_operations_product_id", "operations", ["product_id"], unique=False)

    op.create_table(
        "work_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("total_spent_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number", name="uq_work_orders_order_number"),
    )
    op.create_index("ix_work_orders_product_id", "work_orders", ["product_id"], unique=False)

    op.create_table(
        "work_order_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("worker_user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["operations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worker_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "work_order_id",
            "operation_id",
            name="uq_work_order_assignments_work_order_operation",
        ),
    )
    op.create_index(
        "ix_work_order_assignments_operation_id",
        "work_order_assignments",
        ["operation_id"],
        unique=False,
    )
    op.create_index(
        "ix_work_order_assignments_work_order_id",
        "work_order_assignments",
        ["work_order_id"],
        unique=False,
    )
    op.create_index(
        "ix_work_order_assignments_worker_user_id",
        "work_order_assignments",
        ["worker_user_id"],
        unique=False,
    )

    op.create_table(
        "work_shifts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.BigInteger(), nullable=False),
        sa.Column("ended_at", sa.BigInteger(), nullable=True),
        sa.Column("business_date", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_shifts_business_date", "work_shifts", ["business_date"], unique=False)
    op.create_index("ix_work_shifts_user_id", "work_shifts", ["user_id"], unique=False)

    op.create_table(
        "timer_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shift_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("timer_type_code", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("operation_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.BigInteger(), nullable=False),
        sa.Column("ended_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["operations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shift_id"], ["work_shifts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_timer_sessions_operation_id",
        "timer_sessions",
        ["operation_id"],
        unique=False,
    )
    op.create_index("ix_timer_sessions_order_id", "timer_sessions", ["order_id"], unique=False)
    op.create_index("ix_timer_sessions_shift_id", "timer_sessions", ["shift_id"], unique=False)
    op.create_index(
        "ix_timer_sessions_timer_type_code",
        "timer_sessions",
        ["timer_type_code"],
        unique=False,
    )
    op.create_index("ix_timer_sessions_user_id", "timer_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_timer_sessions_user_id", table_name="timer_sessions")
    op.drop_index("ix_timer_sessions_timer_type_code", table_name="timer_sessions")
    op.drop_index("ix_timer_sessions_shift_id", table_name="timer_sessions")
    op.drop_index("ix_timer_sessions_order_id", table_name="timer_sessions")
    op.drop_index("ix_timer_sessions_operation_id", table_name="timer_sessions")
    op.drop_table("timer_sessions")

    op.drop_index("ix_work_shifts_user_id", table_name="work_shifts")
    op.drop_index("ix_work_shifts_business_date", table_name="work_shifts")
    op.drop_table("work_shifts")

    op.drop_index("ix_work_order_assignments_worker_user_id", table_name="work_order_assignments")
    op.drop_index("ix_work_order_assignments_work_order_id", table_name="work_order_assignments")
    op.drop_index("ix_work_order_assignments_operation_id", table_name="work_order_assignments")
    op.drop_table("work_order_assignments")

    op.drop_index("ix_work_orders_product_id", table_name="work_orders")
    op.drop_table("work_orders")

    op.drop_index("ix_operations_product_id", table_name="operations")
    op.drop_index("ix_operations_parent_id", table_name="operations")
    op.drop_table("operations")

    op.drop_index("ix_auth_sessions_revoked_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_token", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    op.drop_table("products")

    op.drop_index("ix_users_phone", table_name="users")
    op.drop_table("users")

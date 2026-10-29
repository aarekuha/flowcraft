"""add admin work time editing structures

Revision ID: 20261028_0022
Revises: 20261028_0021
Create Date: 2026-10-28 11:30:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20261028_0022"
down_revision = "20261028_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("timer_sessions") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.BigInteger(), nullable=True))
        batch_op.add_column(
            sa.Column("deleted_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_timer_sessions_deleted_by_user_id",
            "users",
            ["deleted_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_timer_sessions_user_time_window",
            ["user_id", "deleted_at", "started_at", "ended_at"],
        )

    op.execute(
        "UPDATE timer_sessions SET updated_at = created_at WHERE updated_at IS NULL"
    )

    with op.batch_alter_table("timer_sessions") as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.BigInteger(),
            nullable=False,
        )

    op.create_table(
        "timer_session_audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timer_session_id", sa.Integer(), nullable=True),
        sa.Column("admin_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("before_payload", sa.JSON(), nullable=True),
        sa.Column("after_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'delete')",
            name="ck_timer_session_audit_log_action",
        ),
        sa.ForeignKeyConstraint(
            ["timer_session_id"],
            ["timer_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_timer_session_audit_log_timer_session_id",
        "timer_session_audit_log",
        ["timer_session_id"],
    )
    op.create_index(
        "ix_timer_session_audit_log_admin_user_id",
        "timer_session_audit_log",
        ["admin_user_id"],
    )
    op.create_index(
        "ix_timer_session_audit_log_created_at",
        "timer_session_audit_log",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_timer_session_audit_log_created_at",
        table_name="timer_session_audit_log",
    )
    op.drop_index(
        "ix_timer_session_audit_log_admin_user_id",
        table_name="timer_session_audit_log",
    )
    op.drop_index(
        "ix_timer_session_audit_log_timer_session_id",
        table_name="timer_session_audit_log",
    )
    op.drop_table("timer_session_audit_log")

    with op.batch_alter_table("timer_sessions") as batch_op:
        batch_op.drop_index("ix_timer_sessions_user_time_window")
        batch_op.drop_constraint(
            "fk_timer_sessions_deleted_by_user_id",
            type_="foreignkey",
        )
        batch_op.drop_column("deleted_by_user_id")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("updated_at")

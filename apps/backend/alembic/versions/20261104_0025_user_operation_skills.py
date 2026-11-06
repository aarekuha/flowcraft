"""add user operation skills

Revision ID: 20261104_0025
Revises: 20261104_0024
Create Date: 2026-11-04 22:45:00
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20261104_0025"
down_revision = "20261104_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_operation_skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("operation_catalog_entry_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["operation_catalog_entry_id"],
            ["operation_catalog_entries.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "operation_catalog_entry_id",
            name="uq_user_operation_skills_user_operation",
        ),
    )
    op.create_index(
        "ix_user_operation_skills_user_id",
        "user_operation_skills",
        ["user_id"],
    )
    op.create_index(
        "ix_user_operation_skills_operation_catalog_entry_id",
        "user_operation_skills",
        ["operation_catalog_entry_id"],
    )

    created_at = int(datetime.now(UTC).timestamp() * 1000)
    op.execute(
        sa.text(
            """
            INSERT INTO user_operation_skills (
                user_id,
                operation_catalog_entry_id,
                created_at,
                created_by_user_id
            )
            SELECT DISTINCT
                work_order_assignments.worker_user_id,
                operations.operation_catalog_entry_id,
                :created_at,
                NULL
            FROM work_order_assignments
            JOIN operations
              ON operations.id = work_order_assignments.operation_id
            WHERE work_order_assignments.worker_user_id IS NOT NULL
              AND operations.operation_catalog_entry_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM user_operation_skills
                  WHERE user_operation_skills.user_id
                        = work_order_assignments.worker_user_id
                    AND user_operation_skills.operation_catalog_entry_id
                        = operations.operation_catalog_entry_id
              )
            """
        ).bindparams(created_at=created_at)
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_operation_skills_operation_catalog_entry_id",
        table_name="user_operation_skills",
    )
    op.drop_index(
        "ix_user_operation_skills_user_id",
        table_name="user_operation_skills",
    )
    op.drop_table("user_operation_skills")

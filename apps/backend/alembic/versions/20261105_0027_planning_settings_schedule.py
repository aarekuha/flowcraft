"""add planning settings and worker schedule

Revision ID: 20261105_0027
Revises: 20261104_0026
Create Date: 2026-11-05 07:15:00
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20261105_0027"
down_revision = "20261104_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planning_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("display_offset_days", sa.Integer(), nullable=False),
        sa.Column("preparation_seconds", sa.Integer(), nullable=False),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "display_offset_days >= 0",
            name="ck_planning_settings_display_offset",
        ),
        sa.CheckConstraint(
            "preparation_seconds >= 0",
            name="ck_planning_settings_preparation",
        ),
        sa.CheckConstraint(
            "horizon_months IN (1, 3, 6, 12)",
            name="ck_planning_settings_horizon",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_work_schedule_days",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("available_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "available_seconds BETWEEN 3600 AND 57600",
            name="ck_user_work_schedule_days_available_seconds",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "work_date",
            name="uq_user_work_schedule_days_user_date",
        ),
    )
    op.create_index(
        "ix_user_work_schedule_days_user_id",
        "user_work_schedule_days",
        ["user_id"],
    )
    op.create_index(
        "ix_user_work_schedule_days_work_date",
        "user_work_schedule_days",
        ["work_date"],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO planning_settings (
                id,
                display_offset_days,
                preparation_seconds,
                horizon_months,
                updated_at,
                updated_by_user_id
            ) VALUES (1, 2, 3600, 3, :updated_at, NULL)
            """
        ).bindparams(updated_at=int(datetime.now(UTC).timestamp() * 1000))
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_work_schedule_days_work_date",
        table_name="user_work_schedule_days",
    )
    op.drop_index(
        "ix_user_work_schedule_days_user_id",
        table_name="user_work_schedule_days",
    )
    op.drop_table("user_work_schedule_days")
    op.drop_table("planning_settings")

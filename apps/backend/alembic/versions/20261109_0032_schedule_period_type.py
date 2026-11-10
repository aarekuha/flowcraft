"""Add work schedule period types

Revision ID: 20261109_0032
Revises: 20261105_0031
"""

import sqlalchemy as sa

from alembic import op

revision = "20261109_0032"
down_revision = "20261105_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_work_schedule_days") as batch_op:
        batch_op.add_column(
            sa.Column(
                "period_type", sa.String(16), nullable=False, server_default="work"
            )
        )
        batch_op.drop_constraint(
            "ck_user_work_schedule_days_available_seconds", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_user_work_schedule_days_available_seconds",
            "(period_type = 'work' AND available_seconds BETWEEN 3600 AND 57600) "
            "OR (period_type IN ('sick_leave', 'vacation', 'absence') "
            "AND available_seconds = 0)",
        )


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM user_work_schedule_days "
                "WHERE period_type != 'work' LIMIT 1"
            )
        )
        .first()
    ):
        raise RuntimeError(
            "Remove absence periods before downgrading the schedule schema"
        )
    with op.batch_alter_table("user_work_schedule_days") as batch_op:
        batch_op.drop_constraint(
            "ck_user_work_schedule_days_available_seconds", type_="check"
        )
        batch_op.drop_column("period_type")
        batch_op.create_check_constraint(
            "ck_user_work_schedule_days_available_seconds",
            "available_seconds BETWEEN 3600 AND 57600",
        )

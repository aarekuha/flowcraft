"""Store user-submitted diagnostic reports"""

import sqlalchemy as sa

from alembic import op

revision = "20261112_0038"
down_revision = "20261112_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("report_key", sa.String(36), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "report_key", name="uq_diagnostic_report_user_key"
        ),
    )
    op.create_index("ix_diagnostic_reports_user_id", "diagnostic_reports", ["user_id"])
    op.create_index(
        "ix_diagnostic_reports_created_at", "diagnostic_reports", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("diagnostic_reports")

"""Store production calendar imports, days and monthly totals

Revision ID: 20261110_0033
Revises: 20261109_0032
"""

import sqlalchemy as sa

from alembic import op

revision = "20261110_0033"
down_revision = "20261109_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_calendar_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("imported_at", sa.BigInteger(), nullable=False),
        sa.Column(
            "imported_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("week_days", sa.Integer(), nullable=False),
        sa.Column("week_hours", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "production_calendar_years",
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column(
            "import_id",
            sa.Integer(),
            sa.ForeignKey("production_calendar_imports.id"),
            nullable=False,
        ),
    )
    op.create_table(
        "production_calendar_days",
        sa.Column("calendar_date", sa.Date(), primary_key=True),
        sa.Column(
            "year",
            sa.Integer(),
            sa.ForeignKey("production_calendar_years.year", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("is_working", sa.Boolean(), nullable=False),
        sa.Column("is_holiday", sa.Boolean(), nullable=False),
        sa.Column("is_shortened", sa.Boolean(), nullable=False),
        sa.Column("name", sa.String(500)),
        sa.Column("transferred_from", sa.Date()),
    )
    op.create_index(
        "ix_production_calendar_days_year", "production_calendar_days", ["year"]
    )
    op.create_table(
        "production_calendar_months",
        sa.Column(
            "year",
            sa.Integer(),
            sa.ForeignKey("production_calendar_years.year", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("month", sa.Integer(), primary_key=True),
        sa.Column("calendar_days", sa.Integer(), nullable=False),
        sa.Column("working_days", sa.Integer(), nullable=False),
        sa.Column("non_working_days", sa.Integer(), nullable=False),
        sa.Column("holiday_days", sa.Integer(), nullable=False),
        sa.Column("shortened_days", sa.Integer(), nullable=False),
        sa.Column("working_hours", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("production_calendar_months")
    op.drop_table("production_calendar_days")
    op.drop_table("production_calendar_years")
    op.drop_table("production_calendar_imports")

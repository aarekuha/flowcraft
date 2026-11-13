"""Add editable work order comment"""
import sqlalchemy as sa

from alembic import op

revision = "20261113_0045"
down_revision = "20261113_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_orders", sa.Column("comment", sa.String(4000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch:
        batch.drop_column("comment")

"""Persist Bitrix synchronization progress"""

import sqlalchemy as sa

from alembic import op

revision = "20261113_0041"
down_revision = "20261113_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bitrix_connection", sa.Column("sync_progress", sa.JSON()))


def downgrade() -> None:
    with op.batch_alter_table("bitrix_connection") as batch:
        batch.drop_column("sync_progress")

"""Recalculate prices using manual time before statistics"""

import sqlalchemy as sa

from alembic import op

revision = "20261113_0044"
down_revision = "20261113_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rate = connection.execute(
        sa.text("SELECT base_rate_cents FROM planning_settings WHERE id=1")
    ).scalar()
    rate = 35000 if rate is None else rate
    rows = (
        connection.execute(
            sa.text("""
        SELECT o.id, o.coefficient_units,
               COALESCE(o.standard_time_seconds, t.seconds_per_item, 0) AS seconds
        FROM operations o LEFT JOIN operation_time_estimates t ON t.operation_id=o.id
        WHERE NOT EXISTS(SELECT 1 FROM operations child WHERE child.parent_id=o.id)
    """)
        )
        .mappings()
        .all()
    )
    for row in rows:
        cents = (
            rate * row["coefficient_units"] * row["seconds"] + 35999999
        ) // 36000000
        connection.execute(
            sa.text("UPDATE operations SET price_cents=:price WHERE id=:id"),
            {"price": cents, "id": row["id"]},
        )


def downgrade() -> None:
    # Изменение данных не отменяет сохранённые коэффициенты и расценки
    pass

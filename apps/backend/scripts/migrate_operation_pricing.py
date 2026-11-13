# ruff: noqa: I001
"""Convert legacy operation prices and preserve an auditable migration report"""

from decimal import Decimal, ROUND_HALF_UP

import sqlalchemy as sa


def migrate(connection) -> None:
    rows = (
        connection.execute(
            sa.text("""
        SELECT o.id, o.product_id, o.name, o.price_cents,
               COALESCE(o.standard_time_seconds, t.seconds_per_item)
                   AS seconds_per_item,
               EXISTS(SELECT 1 FROM operations child
                      WHERE child.parent_id=o.id) AS is_group
        FROM operations o LEFT JOIN operation_time_estimates t ON t.operation_id=o.id
    """)
        )
        .mappings()
        .all()
    )
    for row in rows:
        if row["is_group"]:
            connection.execute(
                sa.text("UPDATE operations SET price_cents=NULL WHERE id=:id"),
                {"id": row["id"]},
            )
            continue
        seconds = row["seconds_per_item"] or 0
        old = row["price_cents"]
        coefficient = (
            int(
                (Decimal(old or 0) * 3600 * 10000 / (35000 * seconds)).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP
                )
            )
            if seconds > 0 and old is not None
            else 10000
        )
        numerator = 35000 * coefficient * seconds
        price = (numerator + 36000000 - 1) // 36000000
        connection.execute(
            sa.text(
                "UPDATE operations SET coefficient_units=:coefficient, "
                "price_cents=:price WHERE id=:id"
            ),
            {"id": row["id"], "coefficient": coefficient, "price": price},
        )
        connection.execute(
            sa.text("""INSERT INTO operation_price_migration_report
            (operation_id, product_id, operation_name, old_price_cents,
             seconds_per_item, coefficient_units, new_price_cents, delta_cents)
            VALUES (:id, :product_id, :name, :old, :seconds,
                    :coefficient, :price, :delta)"""),
            {
                "id": row["id"],
                "product_id": row["product_id"],
                "name": row["name"],
                "old": old,
                "seconds": row["seconds_per_item"],
                "coefficient": coefficient,
                "price": price,
                "delta": price - old if old is not None else None,
            },
        )


if __name__ == "__main__":
    import argparse
    import csv
    import sqlite3

    parser = argparse.ArgumentParser(
        description="Export preserved pricing migration report from SQLite"
    )
    parser.add_argument("database")
    parser.add_argument("output")
    args = parser.parse_args()
    with sqlite3.connect(f"file:{args.database}?mode=ro", uri=True) as db:
        cursor = db.execute(
            "SELECT * FROM operation_price_migration_report ORDER BY operation_id"
        )
        with open(args.output, "w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([column[0] for column in cursor.description])
            writer.writerows(cursor)

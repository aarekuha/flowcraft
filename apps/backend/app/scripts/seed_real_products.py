from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.core.database import SessionLocal
from app.models.auth_session import AuthSession
from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.product import Product
from app.models.user import User
from app.scripts.seed_demo import (
    build_operation_tree,
    build_operations,
    create_operation_catalog_entries,
    create_seed_users,
)


@dataclass(frozen=True)
class ProductSeedSpec:
    name: str
    version: str
    category: str
    author: str
    is_active: bool
    variant: str = "base"


def main() -> None:
    specs = build_product_specs()

    session = SessionLocal()
    try:
        session.execute(delete(AuthSession))
        session.execute(delete(Operation))
        session.execute(delete(OperationCatalogEntry))
        session.execute(delete(Product))
        session.execute(delete(User))

        base_timestamp = datetime(2026, 4, 22, 9, 0, tzinfo=UTC)
        author_users = create_seed_users(session, specs, base_timestamp)
        operation_catalog_entries = create_operation_catalog_entries(
            session,
            specs,
            base_timestamp,
        )

        for index, spec in enumerate(specs):
            product = Product(
                name=spec.name,
                version=spec.version,
                author=spec.author,
                author_user_id=author_users[spec.author].id,
                is_active=spec.is_active,
                created_at=int(
                    (base_timestamp + timedelta(minutes=index * 23)).timestamp() * 1000
                ),
            )

            for sort_order, operation in enumerate(
                build_operations(spec.category, spec.variant)
            ):
                product.operations.append(
                    build_operation_tree(
                        payload=operation,
                        sort_order=sort_order,
                        product=product,
                        operation_catalog_entries=operation_catalog_entries,
                    )
                )

            session.add(product)

        session.commit()
        print(f"Seed completed. Recreated {len(specs)} real products.")
    finally:
        session.close()


def build_product_specs() -> list[ProductSeedSpec]:
    return [
        ProductSeedSpec(
            "Кошелек City Bifold", "1.0", "wallet", "Марина Волкова", True, "base"
        ),
        ProductSeedSpec(
            "Кошелек Travel Long", "1.0", "wallet", "Антон Беляев", True, "zip-pocket"
        ),
        ProductSeedSpec(
            "Кардхолдер Magnetic Pass",
            "1.0",
            "cardholder",
            "Дмитрий Орлов",
            True,
            "magnet",
        ),
        ProductSeedSpec(
            "Обложка на паспорт Heritage",
            "1.0",
            "cover",
            "Ольга Левина",
            True,
            "pen-loop",
        ),
        ProductSeedSpec(
            "Ремень Classic 35", "1.0", "belt", "Илья Сергеев", True, "stitched-edge"
        ),
        ProductSeedSpec(
            "Сумка Shopper Daily", "1.0", "bag", "Елена Жукова", True, "zip-pocket"
        ),
        ProductSeedSpec(
            "Сумка Crossbody Urban", "1.0", "bag", "Елена Жукова", True, "divider"
        ),
        ProductSeedSpec(
            "Рюкзак Field Pack",
            "1.0",
            "backpack",
            "Антон Беляев",
            True,
            "laptop-sleeve",
        ),
        ProductSeedSpec(
            "Папка для ноутбука Office Sleeve",
            "1.0",
            "sleeve",
            "Ольга Левина",
            True,
            "magnetic-closure",
        ),
        ProductSeedSpec(
            "Фартук Leather Apron Pro",
            "1.0",
            "apron",
            "Наталья Воронова",
            True,
            "chest-pocket",
        ),
    ]


if __name__ == "__main__":
    main()

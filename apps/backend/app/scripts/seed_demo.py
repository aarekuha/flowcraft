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


@dataclass(frozen=True)
class ProductSeedSpec:
    name: str
    version: str
    category: str
    author: str
    is_active: bool
    variant: str = "base"


OperationSeed = dict[str, object]


def main() -> None:
    specs = build_product_specs()

    session = SessionLocal()
    try:
        session.execute(delete(AuthSession))
        session.execute(delete(Operation))
        session.execute(delete(OperationCatalogEntry))
        session.execute(delete(Product))
        session.execute(delete(User))

        base_timestamp = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)
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
                    (base_timestamp + timedelta(minutes=index * 17)).timestamp() * 1000
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
        print(f"Seed completed. Recreated {len(specs)} products.")
    finally:
        session.close()


def create_operation_catalog_entries(
    session,
    specs: list[ProductSeedSpec],
    base_timestamp: datetime,
) -> dict[str, OperationCatalogEntry]:
    operation_names: set[str] = set()
    for spec in specs:
        collect_operation_names(
            build_operations(spec.category, spec.variant),
            operation_names,
        )

    operation_catalog_entries: dict[str, OperationCatalogEntry] = {}
    for index, name in enumerate(sorted(operation_names)):
        timestamp = int(
            (base_timestamp - timedelta(days=10, minutes=index)).timestamp() * 1000
        )
        entry = OperationCatalogEntry(
            name=name,
            is_active=True,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(entry)
        operation_catalog_entries[name] = entry

    session.flush()
    return operation_catalog_entries


def collect_operation_names(
    operations: list[OperationSeed],
    names: set[str],
) -> None:
    for operation in operations:
        names.add(str(operation["name"]))
        collect_operation_names(operation.get("children", []), names)


def create_seed_users(
    session,
    specs: list[ProductSeedSpec],
    base_timestamp: datetime,
) -> dict[str, User]:
    author_names = sorted({spec.author for spec in specs})
    author_users: dict[str, User] = {}

    admin_timestamp = int((base_timestamp - timedelta(days=45)).timestamp() * 1000)
    admin_user = User(
        name="Администратор FlowCraft",
        phone="+79990000000",
        password_hash=None,
        roles=["admin"],
        is_active=True,
        created_at=admin_timestamp,
        updated_at=admin_timestamp,
        deleted_at=None,
    )
    session.add(admin_user)
    session.flush()
    admin_user.author_user_id = admin_user.id

    for index, author_name in enumerate(author_names):
        timestamp = int(
            (base_timestamp - timedelta(days=30 - index)).timestamp() * 1000
        )
        user = User(
            name=author_name,
            phone=f"+7999000{index + 1:04d}",
            password_hash=None,
            roles=["constructor"],
            is_active=True,
            created_at=timestamp,
            updated_at=timestamp,
            deleted_at=None,
        )
        session.add(user)
        session.flush()
        user.author_user_id = user.id
        author_users[author_name] = user

    return author_users


def build_product_specs() -> list[ProductSeedSpec]:
    specs = [
        ProductSeedSpec(
            "Кошелек City Bifold", "1.0", "wallet", "Марина Волкова", True, "base"
        ),
        ProductSeedSpec(
            "Кошелек City Bifold", "1.1", "wallet", "Марина Волкова", True, "rfid"
        ),
        ProductSeedSpec(
            "Кошелек City Bifold",
            "2.0",
            "wallet",
            "Марина Волкова",
            False,
            "hidden-pocket",
        ),
        ProductSeedSpec(
            "Кошелек Travel Long", "1.0", "wallet", "Антон Беляев", True, "base"
        ),
        ProductSeedSpec(
            "Кошелек Travel Long", "1.2", "wallet", "Антон Беляев", True, "zip-pocket"
        ),
        ProductSeedSpec(
            "Портмоне Classic Fold", "1.0", "wallet", "Ольга Левина", True, "base"
        ),
        ProductSeedSpec(
            "Портмоне Classic Fold",
            "1.1",
            "wallet",
            "Ольга Левина",
            False,
            "double-edge",
        ),
        ProductSeedSpec(
            "Кардхолдер Slim Pocket",
            "1.0",
            "cardholder",
            "Марина Волкова",
            True,
            "base",
        ),
        ProductSeedSpec(
            "Кардхолдер Slim Pocket",
            "1.1",
            "cardholder",
            "Марина Волкова",
            True,
            "thumb-slot",
        ),
        ProductSeedSpec(
            "Кардхолдер Slim Pocket",
            "1.2",
            "cardholder",
            "Марина Волкова",
            False,
            "pull-tab",
        ),
        ProductSeedSpec(
            "Кардхолдер Magnetic Pass",
            "1.0",
            "cardholder",
            "Дмитрий Орлов",
            True,
            "base",
        ),
        ProductSeedSpec(
            "Кардхолдер Magnetic Pass",
            "2.0",
            "cardholder",
            "Дмитрий Орлов",
            False,
            "magnet",
        ),
        ProductSeedSpec(
            "Обложка на паспорт Heritage", "1.0", "cover", "Ольга Левина", True, "base"
        ),
        ProductSeedSpec(
            "Обложка на паспорт Heritage",
            "1.1",
            "cover",
            "Ольга Левина",
            True,
            "pen-loop",
        ),
        ProductSeedSpec(
            "Обложка для документов Road Case",
            "1.0",
            "cover",
            "Антон Беляев",
            True,
            "base",
        ),
        ProductSeedSpec(
            "Ремень Classic 35", "1.0", "belt", "Илья Сергеев", True, "base"
        ),
        ProductSeedSpec(
            "Ремень Classic 35", "1.1", "belt", "Илья Сергеев", True, "stitched-edge"
        ),
        ProductSeedSpec(
            "Ремень Classic 35", "1.2", "belt", "Илья Сергеев", False, "double-keeper"
        ),
        ProductSeedSpec(
            "Ремень Work Line 40", "1.0", "belt", "Наталья Воронова", True, "base"
        ),
        ProductSeedSpec(
            "Ремень Work Line 40",
            "2.0",
            "belt",
            "Наталья Воронова",
            False,
            "chicago-screws",
        ),
        ProductSeedSpec(
            "Ремень Casual Edge 30", "1.0", "belt", "Наталья Воронова", True, "base"
        ),
        ProductSeedSpec(
            "Сумка Saddle Mini", "1.0", "bag", "Марина Волкова", True, "base"
        ),
        ProductSeedSpec(
            "Сумка Saddle Mini", "1.1", "bag", "Марина Волкова", True, "magnetic-clasp"
        ),
        ProductSeedSpec(
            "Сумка Shopper Daily", "1.0", "bag", "Елена Жукова", True, "base"
        ),
        ProductSeedSpec(
            "Сумка Shopper Daily", "1.1", "bag", "Елена Жукова", True, "zip-pocket"
        ),
        ProductSeedSpec(
            "Сумка Shopper Daily", "2.0", "bag", "Елена Жукова", False, "bag-feet"
        ),
        ProductSeedSpec(
            "Сумка Crossbody Urban", "1.0", "bag", "Елена Жукова", True, "base"
        ),
        ProductSeedSpec(
            "Сумка Crossbody Urban", "1.1", "bag", "Елена Жукова", False, "divider"
        ),
        ProductSeedSpec(
            "Рюкзак Field Pack", "1.0", "backpack", "Антон Беляев", True, "base"
        ),
        ProductSeedSpec(
            "Рюкзак Field Pack",
            "1.1",
            "backpack",
            "Антон Беляев",
            True,
            "laptop-sleeve",
        ),
        ProductSeedSpec(
            "Рюкзак Commuter Pack", "1.0", "backpack", "Антон Беляев", True, "organizer"
        ),
        ProductSeedSpec(
            "Папка для ноутбука Office Sleeve",
            "1.0",
            "sleeve",
            "Ольга Левина",
            True,
            "base",
        ),
        ProductSeedSpec(
            "Папка для ноутбука Office Sleeve",
            "1.1",
            "sleeve",
            "Ольга Левина",
            False,
            "magnetic-closure",
        ),
        ProductSeedSpec(
            "Чехол для планшета Workshop Case",
            "1.0",
            "sleeve",
            "Ольга Левина",
            True,
            "base",
        ),
        ProductSeedSpec(
            "Ключница Clasp Key Case", "1.0", "accessory", "Дмитрий Орлов", True, "base"
        ),
        ProductSeedSpec(
            "Ключница Clasp Key Case",
            "1.1",
            "accessory",
            "Дмитрий Орлов",
            True,
            "key-ring",
        ),
        ProductSeedSpec(
            "Несессер Travel Kit", "1.0", "bag", "Елена Жукова", True, "base"
        ),
        ProductSeedSpec(
            "Несессер Travel Kit", "1.1", "bag", "Елена Жукова", True, "zip-pocket"
        ),
        ProductSeedSpec(
            "Несессер Travel Kit",
            "1.2",
            "bag",
            "Елена Жукова",
            False,
            "waterproof-lining",
        ),
        ProductSeedSpec(
            "Фартук Leather Apron Pro", "1.0", "apron", "Наталья Воронова", True, "base"
        ),
        ProductSeedSpec(
            "Фартук Leather Apron Pro",
            "1.1",
            "apron",
            "Наталья Воронова",
            True,
            "chest-pocket",
        ),
        ProductSeedSpec(
            "Кобура Tool Holster", "1.0", "holster", "Илья Сергеев", True, "base"
        ),
        ProductSeedSpec(
            "Браслет Cuff Line", "1.0", "bracelet", "Дмитрий Орлов", True, "base"
        ),
        ProductSeedSpec(
            "Браслет Cuff Line",
            "1.1",
            "bracelet",
            "Дмитрий Орлов",
            False,
            "double-snap",
        ),
        ProductSeedSpec(
            "Косметичка Mini Pouch", "1.0", "bag", "Елена Жукова", True, "base"
        ),
        ProductSeedSpec(
            "Косметичка Mini Pouch", "1.1", "bag", "Елена Жукова", True, "zip-pocket"
        ),
        ProductSeedSpec(
            "Чехол для очков Optic Case",
            "1.0",
            "accessory",
            "Ольга Левина",
            True,
            "felt-lining",
        ),
        ProductSeedSpec(
            "Визитница Desk Holder",
            "1.0",
            "cardholder",
            "Марина Волкова",
            True,
            "thumb-slot",
        ),
        ProductSeedSpec(
            "Чехол для ножа Knife Sheath",
            "1.0",
            "holster",
            "Илья Сергеев",
            True,
            "base",
        ),
        ProductSeedSpec(
            "Чехол для ножа Knife Sheath",
            "1.1",
            "holster",
            "Илья Сергеев",
            False,
            "welt",
        ),
    ]

    if len(specs) != 50:
        raise RuntimeError(f"Expected 50 products, got {len(specs)}.")

    return specs


def build_operations(category: str, variant: str) -> list[OperationSeed]:
    if category == "wallet":
        operations = [
            group(
                "Подготовка деталей",
                leaf("Разметка лекал"),
                leaf("Крой внешних деталей"),
                leaf("Крой внутренних карманов"),
            ),
            group(
                "Подготовка к сборке",
                leaf("Утончение краев"),
                leaf("Пробивка швов"),
                leaf("Покраска уреза"),
            ),
            group(
                "Сборка",
                leaf("Склейка пакета"),
                leaf("Прошивка"),
                leaf("Финишная полировка"),
            ),
        ]
        if variant == "rfid":
            append_to_group(operations, "Подготовка к сборке", "Установка RFID-экрана")
        elif variant == "hidden-pocket":
            append_to_group(operations, "Подготовка деталей", "Крой скрытого кармана")
            append_to_group(operations, "Сборка", "Сборка скрытого кармана")
        elif variant == "zip-pocket":
            append_to_group(operations, "Подготовка деталей", "Крой кармана на молнии")
            append_to_group(operations, "Сборка", "Установка молнии кармана")
        elif variant == "double-edge":
            replace_leaf(operations, "Покраска уреза", "Покраска уреза в два слоя")
        return operations

    if category == "cardholder":
        operations = [
            group(
                "Крой",
                leaf("Крой корпуса"),
                leaf("Крой карманов"),
            ),
            group(
                "Подготовка",
                leaf("Тоншение карманов"),
                leaf("Нанесение клея"),
            ),
            group(
                "Сборка",
                leaf("Сборка карманов"),
                leaf("Прошивка по периметру"),
                leaf("Обработка уреза"),
            ),
        ]
        if variant == "thumb-slot":
            append_to_group(operations, "Крой", "Вырубка окна под большой палец")
        elif variant == "pull-tab":
            append_to_group(operations, "Подготовка", "Подготовка pull-tab ленты")
            append_to_group(operations, "Сборка", "Установка pull-tab")
        elif variant == "magnet":
            append_to_group(operations, "Сборка", "Установка магнитной кнопки")
        return operations

    if category == "cover":
        operations = [
            group(
                "Подготовка деталей",
                leaf("Крой обложки"),
                leaf("Крой подкладки"),
                leaf("Крой внутренних клапанов"),
            ),
            group(
                "Сборка блока",
                leaf("Склейка слоев"),
                leaf("Формирование карманов"),
                leaf("Прошивка"),
            ),
            leaf("Финишная обработка"),
        ]
        if variant == "pen-loop":
            append_to_group(operations, "Сборка блока", "Сборка держателя для ручки")
        return operations

    if category == "belt":
        operations = [
            group(
                "Подготовка ременной полосы",
                leaf("Раскрой ременной полосы"),
                leaf("Выравнивание края"),
                leaf("Формирование кончика"),
            ),
            group(
                "Фурнитура",
                leaf("Пробивка отверстий"),
                leaf("Установка пряжки"),
                leaf("Установка шлевки"),
            ),
            group(
                "Финиш",
                leaf("Шлифовка уреза"),
                leaf("Покраска уреза"),
                leaf("Финишный воск"),
            ),
        ]
        if variant == "stitched-edge":
            append_to_group(operations, "Финиш", "Декоративная строчка по краю")
        elif variant == "double-keeper":
            append_to_group(operations, "Фурнитура", "Изготовление второй шлевки")
        elif variant == "chicago-screws":
            replace_leaf(
                operations, "Установка пряжки", "Установка пряжки на Chicago screws"
            )
        return operations

    if category == "bag":
        operations = [
            group(
                "Подготовка панелей",
                leaf("Крой основных панелей"),
                leaf("Крой подкладки"),
                leaf("Крой карманов"),
            ),
            group(
                "Подсборки",
                leaf("Сборка карманов"),
                leaf("Вшивание молнии"),
                leaf("Подготовка ручек или ремня"),
            ),
            group(
                "Основная сборка",
                leaf("Сборка корпуса"),
                leaf("Установка фурнитуры"),
                leaf("Финальная отделка"),
            ),
        ]
        if variant == "zip-pocket":
            append_to_group(
                operations, "Подсборки", "Сборка внутреннего кармана на молнии"
            )
        elif variant == "magnetic-clasp":
            append_to_group(operations, "Основная сборка", "Установка магнитного замка")
        elif variant == "bag-feet":
            append_to_group(operations, "Основная сборка", "Установка ножек дна")
        elif variant == "divider":
            append_to_group(operations, "Подсборки", "Сборка внутренней перегородки")
        elif variant == "waterproof-lining":
            replace_leaf(operations, "Крой подкладки", "Крой влагостойкой подкладки")
        return operations

    if category == "backpack":
        operations = [
            group(
                "Подготовка деталей",
                leaf("Крой корпуса"),
                leaf("Крой лямок"),
                leaf("Крой усилителей"),
            ),
            group(
                "Подсборки",
                leaf("Сборка лямок"),
                leaf("Сборка карманов"),
                leaf("Установка молний"),
            ),
            group(
                "Сборка рюкзака",
                leaf("Сборка корпуса"),
                leaf("Установка фурнитуры"),
                leaf("Контроль качества"),
            ),
        ]
        if variant == "laptop-sleeve":
            append_to_group(
                operations, "Подсборки", "Сборка внутреннего ноутбучного кармана"
            )
        elif variant == "organizer":
            append_to_group(operations, "Подсборки", "Сборка органайзера для мелочей")
        return operations

    if category == "sleeve":
        operations = [
            group(
                "Крой",
                leaf("Крой лицевых деталей"),
                leaf("Крой подкладки"),
                leaf("Крой усилителей"),
            ),
            group(
                "Сборка",
                leaf("Склейка слоев"),
                leaf("Установка застежки"),
                leaf("Прошивка по периметру"),
            ),
            leaf("Финишная обработка"),
        ]
        if variant == "magnetic-closure":
            append_to_group(operations, "Сборка", "Установка магнитной застежки")
        return operations

    if category == "apron":
        operations = [
            group(
                "Подготовка основы",
                leaf("Крой основного полотна"),
                leaf("Разметка карманов"),
                leaf("Пробивка креплений"),
            ),
            group(
                "Подсборки",
                leaf("Сборка карманов"),
                leaf("Подготовка ремней"),
            ),
            group(
                "Финальная сборка",
                leaf("Установка фурнитуры"),
                leaf("Крепление ремней"),
                leaf("Финишная обработка"),
            ),
        ]
        if variant == "chest-pocket":
            append_to_group(operations, "Подсборки", "Сборка нагрудного кармана")
        return operations

    if category == "holster":
        operations = [
            group(
                "Подготовка шаблона",
                leaf("Крой корпуса"),
                leaf("Крой клапана"),
                leaf("Крой крепежных элементов"),
            ),
            group(
                "Формовка",
                leaf("Увлажнение кожи"),
                leaf("Формование по шаблону"),
                leaf("Сушка"),
            ),
            group(
                "Сборка",
                leaf("Прошивка"),
                leaf("Установка кнопки или люверсов"),
                leaf("Финишная обработка"),
            ),
        ]
        if variant == "welt":
            append_to_group(operations, "Подготовка шаблона", "Крой и установка ранта")
        return operations

    if category == "bracelet":
        operations = [
            group(
                "Крой",
                leaf("Крой браслетной полосы"),
                leaf("Формирование краев"),
            ),
            group(
                "Подготовка",
                leaf("Пробивка отверстий"),
                leaf("Окрашивание уреза"),
            ),
            group(
                "Сборка",
                leaf("Установка кнопок"),
                leaf("Полировка"),
            ),
        ]
        if variant == "double-snap":
            replace_leaf(operations, "Установка кнопок", "Установка двойной кнопки")
        return operations

    if category == "accessory":
        operations = [
            group(
                "Подготовка деталей",
                leaf("Крой корпуса"),
                leaf("Крой внутренних элементов"),
            ),
            group(
                "Сборка",
                leaf("Склейка"),
                leaf("Прошивка"),
                leaf("Обработка уреза"),
            ),
            leaf("Контроль качества"),
        ]
        if variant == "key-ring":
            append_to_group(operations, "Сборка", "Установка кольца для ключей")
        elif variant == "felt-lining":
            replace_leaf(
                operations,
                "Крой внутренних элементов",
                "Крой и вклейка фетровой подкладки",
            )
        return operations

    raise ValueError(f"Unknown product category: {category}")


def group(name: str, *children: OperationSeed) -> OperationSeed:
    return {"name": name, "children": list(children)}


def leaf(name: str) -> OperationSeed:
    return {"name": name, "children": []}


def append_to_group(
    operations: list[OperationSeed],
    group_name: str,
    operation_name: str,
) -> None:
    for operation in operations:
        if operation["name"] == group_name:
            operation["children"].append(leaf(operation_name))
            return

    raise ValueError(f"Group '{group_name}' not found.")


def replace_leaf(
    operations: list[OperationSeed],
    existing_name: str,
    new_name: str,
) -> None:
    for operation in operations:
        children = operation["children"]
        for index, child in enumerate(children):
            if child["name"] == existing_name:
                children[index] = leaf(new_name)
                return

    raise ValueError(f"Operation '{existing_name}' not found.")


def build_operation_tree(
    payload: OperationSeed,
    sort_order: int,
    product: Product,
    operation_catalog_entries: dict[str, OperationCatalogEntry],
) -> Operation:
    name = str(payload["name"])
    catalog_entry = operation_catalog_entries[name]
    operation = Operation(
        operation_catalog_entry_id=catalog_entry.id,
        name=catalog_entry.name,
        sort_order=sort_order,
        product=product,
    )

    children = payload["children"]
    for child_index, child in enumerate(children):
        operation.children.append(
            build_operation_tree(
                payload=child,
                sort_order=child_index,
                product=product,
                operation_catalog_entries=operation_catalog_entries,
            )
        )

    return operation


if __name__ == "__main__":
    main()

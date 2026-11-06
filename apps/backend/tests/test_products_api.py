from fastapi.testclient import TestClient


def create_author_user(client: TestClient, name: str = "Марина Волкова") -> dict:
    phone_suffix = sum(ord(char) for char in name) % 10_000
    response = client.post(
        "/api/users",
        json={
            "name": name,
            "phone": f"+7999111{phone_suffix:04d}",
            "roles": ["constructor"],
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def ensure_operation_catalog_entries(
    client: TestClient,
    names: list[str],
) -> None:
    for name in names:
        response = client.post("/api/operation-catalog", json={"name": name})
        assert response.status_code in {201, 422}


def create_stage_test_product(client: TestClient, name: str) -> dict:
    author_user = create_author_user(client, f"Автор {name}")
    adjacent_response = client.post(
        "/api/operation-catalog",
        json={"name": f"Смежная {name}", "operation_kind": "adjacent"},
    )
    assert adjacent_response.status_code == 201
    regular_response = client.post(
        "/api/operation-catalog",
        json={"name": f"Обычная {name}", "operation_kind": "regular"},
    )
    assert regular_response.status_code == 201

    response = client.post(
        "/api/products",
        json={
            "name": name,
            "version": "1.0",
            "author_user_id": author_user["id"],
            "operations": [
                {
                    "operation_catalog_entry_id": adjacent_response.json()["id"],
                    "name": adjacent_response.json()["name"],
                    "children": [],
                },
                {
                    "operation_catalog_entry_id": regular_response.json()["id"],
                    "name": regular_response.json()["name"],
                    "children": [],
                },
            ],
        },
    )
    assert response.status_code == 201
    return dict(response.json())


def test_create_and_get_product(client: TestClient) -> None:
    """
    Проверяем создание и чтение изделия:
    - сохранить многострочный комментарий
    - вернуть комментарий в карточке изделия
    """
    author_user = create_author_user(client)
    ensure_operation_catalog_entries(
        client,
        ["Фасад", "Подклад", "Пошив"],
    )
    payload = {
        "name": "Кошелек Daily Fold",
        "version": "1.0",
        "comment": "Блок операций 1: подготовка\nБлок операций 2: пошив",
        "author_user_id": author_user["id"],
        "material_cost_cents": 125000,
        "operations": [
            {
                "name": "Подготовка",
                "children": [
                    {
                        "name": "Фасад",
                        "price_cents": 5000,
                        "standard_time_seconds": 95,
                        "children": [],
                    },
                    {"name": "Подклад", "children": []},
                ],
            },
            {
                "name": "Пошив",
                "price_cents": 25000,
                "standard_time_seconds": 630,
                "children": [],
            },
        ],
    }

    create_response = client.post("/api/products", json=payload)

    assert create_response.status_code == 201
    created_product = create_response.json()
    assert created_product["name"] == payload["name"]
    assert created_product["version"] == payload["version"]
    assert created_product["comment"] == payload["comment"]
    assert created_product["author"] == author_user["name"]
    assert created_product["material_cost_cents"] == 125000
    assert len(created_product["operations"]) == 2
    assert created_product["operations"][0]["operation_catalog_entry_id"] is None
    assert created_product["operations"][0]["name"] == "Подготовка"
    assert created_product["operations"][0]["price_cents"] is None
    assert created_product["operations"][0]["standard_time_seconds"] is None
    assert isinstance(
        created_product["operations"][0]["children"][0][
            "operation_catalog_entry_id"
        ],
        int,
    )
    assert created_product["operations"][0]["children"][0]["name"] == "Фасад"
    assert created_product["operations"][0]["children"][0]["price_cents"] == 5000
    assert (
        created_product["operations"][0]["children"][0]["standard_time_seconds"]
        == 95
    )
    assert (
        created_product["operations"][0]["children"][0][
            "statistical_time_seconds"
        ]
        is None
    )
    assert (
        created_product["operations"][0]["children"][0][
            "statistical_completed_orders_count"
        ]
        == 0
    )
    assert (
        created_product["operations"][0]["children"][0][
            "statistical_items_count"
        ]
        == 0
    )
    assert created_product["operations"][0]["children"][1]["price_cents"] is None
    assert created_product["operations"][1]["standard_time_seconds"] == 630

    product_id = created_product["id"]

    get_response = client.get(f"/api/products/{product_id}")

    assert get_response.status_code == 200
    fetched_product = get_response.json()
    assert fetched_product == created_product


def test_product_operations_default_to_first_production_stage(
    client: TestClient,
) -> None:
    """
    Проверяем исходную схему этапов изделия:
    - создать изделие без явного расположения операций
    - разместить все операции на первом этапе
    - вернуть типы операций для редактора
    """
    product = create_stage_test_product(client, "Сумка Stage Defaults")

    assert product["stage_count"] == 1
    assert [operation["stage_start"] for operation in product["operations"]] == [
        1,
        1,
    ]
    assert [operation["stage_end"] for operation in product["operations"]] == [
        1,
        1,
    ]
    assert [operation["operation_kind"] for operation in product["operations"]] == [
        "adjacent",
        "regular",
    ]


def test_update_product_production_stages(client: TestClient) -> None:
    """
    Проверяем сохранение технологических этапов:
    - растянуть смежную операцию на несколько этапов
    - переместить обычную операцию на один этап
    - вернуть новую схему в карточке и списке изделий
    """
    product = create_stage_test_product(client, "Сумка Stage Update")
    adjacent_operation, regular_operation = product["operations"]

    response = client.patch(
        f"/api/products/{product['id']}/stages",
        json={
            "stage_count": 3,
            "operations": [
                {
                    "operation_id": adjacent_operation["id"],
                    "stage_start": 1,
                    "stage_end": 2,
                },
                {
                    "operation_id": regular_operation["id"],
                    "stage_start": 3,
                    "stage_end": 3,
                },
            ],
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["stage_count"] == 3
    assert updated["operations"][0]["stage_start"] == 1
    assert updated["operations"][0]["stage_end"] == 2
    assert updated["operations"][1]["stage_start"] == 3
    assert updated["operations"][1]["stage_end"] == 3

    list_response = client.get("/api/products")
    assert list_response.status_code == 200
    listed_product = next(
        item for item in list_response.json() if item["id"] == product["id"]
    )
    assert listed_product["stage_count"] == 3


def test_update_product_stages_rejects_regular_operation_span(
    client: TestClient,
) -> None:
    """
    Проверяем ограничение диапазона обычной операции:
    - передать обычную операцию сразу на два этапа
    - отклонить всю схему без частичного сохранения
    """
    product = create_stage_test_product(client, "Сумка Regular Span Guard")
    adjacent_operation, regular_operation = product["operations"]

    response = client.patch(
        f"/api/products/{product['id']}/stages",
        json={
            "stage_count": 2,
            "operations": [
                {
                    "operation_id": adjacent_operation["id"],
                    "stage_start": 1,
                    "stage_end": 1,
                },
                {
                    "operation_id": regular_operation["id"],
                    "stage_start": 1,
                    "stage_end": 2,
                },
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Несмежная операция может находиться только на одном этапе."
    )
    fetched = client.get(f"/api/products/{product['id']}").json()
    assert fetched["stage_count"] == 1
    assert all(operation["stage_end"] == 1 for operation in fetched["operations"])


def test_update_product_stages_requires_every_leaf_operation(
    client: TestClient,
) -> None:
    """
    Проверяем полноту схемы этапов:
    - пропустить одну конечную операцию
    - отклонить неполную схему
    """
    product = create_stage_test_product(client, "Сумка Stage Coverage")

    response = client.patch(
        f"/api/products/{product['id']}/stages",
        json={
            "stage_count": 2,
            "operations": [
                {
                    "operation_id": product["operations"][0]["id"],
                    "stage_start": 1,
                    "stage_end": 2,
                },
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Схема этапов должна содержать все конечные операции изделия "
        "и не должна содержать группы."
    )


def test_update_product_stages_allows_product_used_by_order(
    client: TestClient,
) -> None:
    """
    Проверяем изменение схемы изделия в заказе:
    - создать заказ с текущей версией изделия
    - сохранить новую схему этапов этой версии
    - запросить фоновый пересчёт планирования
    """
    product = create_stage_test_product(client, "Сумка Used Stage Guard")
    order_response = client.post(
        "/api/orders",
        json={
            "product_id": product["id"],
            "quantity": 1,
            "assignments": [
                {
                    "operation_id": operation["id"],
                    "worker_user_id": None,
                }
                for operation in product["operations"]
            ],
        },
    )
    assert order_response.status_code == 201
    revision_before = client.get("/api/planning/status").json()["input_revision"]

    response = client.patch(
        f"/api/products/{product['id']}/stages",
        json={
            "stage_count": 2,
            "operations": [
                {
                    "operation_id": product["operations"][0]["id"],
                    "stage_start": 1,
                    "stage_end": 2,
                },
                {
                    "operation_id": product["operations"][1]["id"],
                    "stage_start": 2,
                    "stage_end": 2,
                },
            ],
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["stage_count"] == 2
    assert updated["operations"][0]["stage_start"] == 1
    assert updated["operations"][0]["stage_end"] == 2
    assert updated["operations"][1]["stage_start"] == 2
    status_payload = client.get("/api/planning/status").json()
    assert status_payload["input_revision"] == revision_before + 1
    assert status_payload["calculation_status"] == "pending"


def test_copy_product_preserves_stages_and_inactive_source_operations(
    client: TestClient,
) -> None:
    """
    Проверяем копирование версионной схемы изделия:
    - сохранить диапазоны технологических этапов
    - разрешить операцию, деактивированную после создания исходного изделия
    - не разрешить ту же операцию без ссылки на исходное изделие
    """
    product = create_stage_test_product(client, "Сумка Stage Copy")
    adjacent_operation, regular_operation = product["operations"]
    stages_response = client.patch(
        f"/api/products/{product['id']}/stages",
        json={
            "stage_count": 2,
            "operations": [
                {
                    "operation_id": adjacent_operation["id"],
                    "stage_start": 1,
                    "stage_end": 2,
                },
                {
                    "operation_id": regular_operation["id"],
                    "stage_start": 2,
                    "stage_end": 2,
                },
            ],
        },
    )
    assert stages_response.status_code == 200
    deactivate_response = client.patch(
        "/api/operation-catalog/"
        f"{adjacent_operation['operation_catalog_entry_id']}/status",
        json={"is_active": False},
    )
    assert deactivate_response.status_code == 200

    copy_payload = {
        "name": product["name"],
        "version": "2.0",
        "stage_count": 2,
        "operations": [
            {
                "operation_catalog_entry_id": (
                    adjacent_operation["operation_catalog_entry_id"]
                ),
                "name": adjacent_operation["name"],
                "stage_start": 1,
                "stage_end": 2,
                "children": [],
            },
            {
                "operation_catalog_entry_id": (
                    regular_operation["operation_catalog_entry_id"]
                ),
                "name": regular_operation["name"],
                "stage_start": 2,
                "stage_end": 2,
                "children": [],
            },
        ],
    }
    rejected_response = client.post("/api/products", json=copy_payload)
    assert rejected_response.status_code == 422

    copy_payload["source_product_id"] = product["id"]
    copy_response = client.post("/api/products", json=copy_payload)

    assert copy_response.status_code == 201
    copied_product = copy_response.json()
    assert copied_product["stage_count"] == 2
    assert copied_product["operations"][0]["stage_start"] == 1
    assert copied_product["operations"][0]["stage_end"] == 2
    assert copied_product["operations"][1]["stage_start"] == 2
    assert copied_product["operations"][1]["stage_end"] == 2


def test_operation_kind_change_rejects_spanning_product_operation(
    client: TestClient,
) -> None:
    """
    Проверяем сохранение инварианта смежной операции:
    - растянуть смежную операцию на несколько этапов
    - запретить замену её типа на обычный
    - сохранить исходный тип операции
    """
    product = create_stage_test_product(client, "Сумка Kind Stage Guard")
    adjacent_operation, regular_operation = product["operations"]
    stages_response = client.patch(
        f"/api/products/{product['id']}/stages",
        json={
            "stage_count": 2,
            "operations": [
                {
                    "operation_id": adjacent_operation["id"],
                    "stage_start": 1,
                    "stage_end": 2,
                },
                {
                    "operation_id": regular_operation["id"],
                    "stage_start": 1,
                    "stage_end": 1,
                },
            ],
        },
    )
    assert stages_response.status_code == 200

    response = client.patch(
        "/api/operation-catalog/"
        f"{adjacent_operation['operation_catalog_entry_id']}/kind",
        json={"operation_kind": "regular"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Нельзя изменить тип: операция растянута на несколько "
        "технологических этапов изделия."
    )
    catalog_response = client.get(
        "/api/operation-catalog?include_inactive=true&search=Kind%20Stage%20Guard"
    )
    assert catalog_response.status_code == 200
    adjacent_entry = next(
        entry
        for entry in catalog_response.json()["items"]
        if entry["id"] == adjacent_operation["operation_catalog_entry_id"]
    )
    assert adjacent_entry["operation_kind"] == "adjacent"


def test_update_product_costs(client: TestClient) -> None:
    """
    Проверяем редактирование стоимости и комментария изделия:
    - обновить оба доступных поля карточки
    - сохранить неизменными цены операций
    """
    author_user = create_author_user(client)
    ensure_operation_catalog_entries(client, ["Фасад", "Пошив"])
    create_response = client.post(
        "/api/products",
        json={
            "name": "Портмоне Price Line",
            "version": "1.0",
            "author_user_id": author_user["id"],
            "operations": [
                {
                    "name": "Подготовка",
                    "children": [
                        {"name": "Фасад", "price_cents": 7000, "children": []},
                    ],
                },
                {"name": "Пошив", "price_cents": 25000, "children": []},
            ],
        },
    )
    assert create_response.status_code == 201
    product = create_response.json()

    patch_response = client.patch(
        f"/api/products/{product['id']}/costs",
        json={
            "material_cost_cents": 99000,
            "comment": "Блок операций 1: крой и подготовка",
            "operations": [],
        },
    )

    assert patch_response.status_code == 200
    updated_product = patch_response.json()
    assert updated_product["material_cost_cents"] == 99000
    assert updated_product["comment"] == "Блок операций 1: крой и подготовка"
    assert updated_product["operations"][0]["price_cents"] is None
    assert updated_product["operations"][0]["children"][0]["price_cents"] == 7000
    assert updated_product["operations"][1]["price_cents"] == 25000

    get_response = client.get(f"/api/products/{product['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["material_cost_cents"] == 99000
    assert get_response.json()["comment"] == "Блок операций 1: крой и подготовка"


def test_create_product_rejects_comment_over_limit(client: TestClient) -> None:
    """
    Проверяем ограничение длины комментария:
    - передать 1001 символ
    - получить ошибку валидации
    """
    author_user = create_author_user(client)
    ensure_operation_catalog_entries(client, ["Крой"])

    response = client.post(
        "/api/products",
        json={
            "name": "Ремень Comment Guard",
            "version": "1.0",
            "comment": "А" * 1001,
            "author_user_id": author_user["id"],
            "operations": [{"name": "Крой", "children": []}],
        },
    )

    assert response.status_code == 422


def test_create_product_rejects_group_operation_price(client: TestClient) -> None:
    author_user = create_author_user(client)

    create_response = client.post(
        "/api/products",
        json={
            "name": "Клатч Group Price Guard",
            "version": "1.0",
            "author_user_id": author_user["id"],
            "operations": [
                {
                    "name": "Крой",
                    "price_cents": 10000,
                    "children": [
                        {"name": "Фасад", "price_cents": 5000, "children": []},
                    ],
                },
            ],
        },
    )

    assert create_response.status_code == 422
    assert create_response.json()["detail"] == "Operation groups cannot have prices."


def test_create_product_rejects_group_operation_standard_time(
    client: TestClient,
) -> None:
    author_user = create_author_user(client)

    create_response = client.post(
        "/api/products",
        json={
            "name": "Клатч Group Standard Time Guard",
            "version": "1.0",
            "author_user_id": author_user["id"],
            "operations": [
                {
                    "name": "Крой",
                    "standard_time_seconds": 120,
                    "children": [
                        {"name": "Фасад", "children": []},
                    ],
                },
            ],
        },
    )

    assert create_response.status_code == 422
    assert (
        create_response.json()["detail"]
        == "Operation groups cannot have standard times."
    )


def test_create_product_rejects_group_operation_catalog_reference(
    client: TestClient,
) -> None:
    author_user = create_author_user(client)
    group_catalog_response = client.post(
        "/api/operation-catalog",
        json={"name": "Крой"},
    )
    assert group_catalog_response.status_code == 201
    ensure_operation_catalog_entries(client, ["Фасад"])

    create_response = client.post(
        "/api/products",
        json={
            "name": "Клатч Group Catalog Guard",
            "version": "1.0",
            "author_user_id": author_user["id"],
            "operations": [
                {
                    "operation_catalog_entry_id": group_catalog_response.json()["id"],
                    "name": "Подготовка",
                    "children": [
                        {"name": "Фасад", "price_cents": 5000, "children": []},
                    ],
                },
            ],
        },
    )

    assert create_response.status_code == 422
    assert (
        create_response.json()["detail"]
        == "Operation groups must not reference the operation catalog."
    )


def test_update_product_costs_rejects_operation_price_change(
    client: TestClient,
) -> None:
    author_user = create_author_user(client)
    ensure_operation_catalog_entries(client, ["Крой", "Пошив"])
    create_response = client.post(
        "/api/products",
        json={
            "name": "Клатч Cost Guard",
            "version": "1.0",
            "author_user_id": author_user["id"],
            "operations": [
                {"name": "Крой", "price_cents": 10000, "children": []},
                {"name": "Пошив", "children": []},
            ],
        },
    )
    assert create_response.status_code == 201
    product = create_response.json()

    patch_response = client.patch(
        f"/api/products/{product['id']}/costs",
        json={
            "material_cost_cents": 50000,
            "operations": [
                {
                    "id": product["operations"][0]["id"],
                    "price_cents": 11000,
                    "children": [],
                },
            ],
        },
    )

    assert patch_response.status_code == 422
    assert (
        patch_response.json()["detail"]
        == "Operation prices cannot be changed after product creation."
    )


def test_update_product_costs_allows_operation_standard_time_change_and_removal(
    client: TestClient,
) -> None:
    """
    Проверяем редактирование ручной нормы существующего изделия:
    - не удалять норму при отсутствии поля в запросе
    - разрешить изменить и явно удалить ручную норму
    - запрашивать новый расчёт после каждого фактического изменения
    """
    author_user = create_author_user(client)
    ensure_operation_catalog_entries(client, ["Крой"])
    create_response = client.post(
        "/api/products",
        json={
            "name": "Клатч Standard Time Guard",
            "version": "1.0",
            "author_user_id": author_user["id"],
            "operations": [
                {
                    "name": "Крой",
                    "price_cents": 10000,
                    "standard_time_seconds": 90,
                    "children": [],
                },
            ],
        },
    )
    assert create_response.status_code == 201
    product = create_response.json()
    operation_id = product["operations"][0]["id"]
    revision_before = client.get("/api/planning/status").json()["input_revision"]

    unchanged_response = client.patch(
        f"/api/products/{product['id']}/costs",
        json={
            "material_cost_cents": 50000,
            "operations": [
                {
                    "id": operation_id,
                    "price_cents": 10000,
                    "children": [],
                },
            ],
        },
    )
    assert unchanged_response.status_code == 200
    assert unchanged_response.json()["operations"][0]["standard_time_seconds"] == 90
    assert (
        client.get("/api/planning/status").json()["input_revision"]
        == revision_before
    )

    patch_response = client.patch(
        f"/api/products/{product['id']}/costs",
        json={
            "material_cost_cents": 50000,
            "operations": [
                {
                    "id": operation_id,
                    "price_cents": 10000,
                    "standard_time_seconds": 120,
                    "children": [],
                },
            ],
        },
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["operations"][0]["standard_time_seconds"] == 120
    changed_status = client.get("/api/planning/status").json()
    assert changed_status["input_revision"] == revision_before + 1
    assert changed_status["calculation_status"] == "pending"

    delete_response = client.patch(
        f"/api/products/{product['id']}/costs",
        json={
            "material_cost_cents": 50000,
            "operations": [
                {
                    "id": operation_id,
                    "price_cents": 10000,
                    "standard_time_seconds": None,
                    "children": [],
                },
            ],
        },
    )

    assert delete_response.status_code == 200
    assert (
        delete_response.json()["operations"][0]["standard_time_seconds"] is None
    )
    deleted_status = client.get("/api/planning/status").json()
    assert deleted_status["input_revision"] == revision_before + 2
    assert deleted_status["calculation_status"] == "pending"


def test_list_products_returns_operations_count(client: TestClient) -> None:
    author_user = create_author_user(client)
    ensure_operation_catalog_entries(
        client,
        ["Подготовка деталей", "Пошив корпуса"],
    )
    create_response = client.post(
        "/api/products",
        json={
            "name": "Сумка Saddle Mini",
            "version": "2.0",
            "author_user_id": author_user["id"],
            "operations": [
                {"name": "Подготовка деталей", "children": []},
                {
                    "name": "Сборка",
                    "children": [
                        {"name": "Пошив корпуса", "children": []},
                    ],
                },
            ],
        },
    )
    assert create_response.status_code == 201

    list_response = client.get("/api/products")

    assert list_response.status_code == 200
    products = list_response.json()
    assert len(products) == 1
    assert products[0]["name"] == "Сумка Saddle Mini"
    assert products[0]["author"] == author_user["name"]
    assert products[0]["operations_count"] == 3


def test_create_product_rejects_duplicate_sibling_operations(
    client: TestClient,
) -> None:
    author_user = create_author_user(client)
    ensure_operation_catalog_entries(client, ["Крой"])
    response = client.post(
        "/api/products",
        json={
            "name": "Ремень Craft Line",
            "version": "1.2",
            "author_user_id": author_user["id"],
            "operations": [
                {"name": "Крой", "children": []},
                {"name": "крой", "children": []},
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Operations must be unique within a product."


def test_create_product_rejects_duplicate_name_and_version(client: TestClient) -> None:
    author_user = create_author_user(client)
    ensure_operation_catalog_entries(client, ["Крой"])
    payload = {
        "name": "Кошелек Daily Fold",
        "version": "1.0",
        "author_user_id": author_user["id"],
        "operations": [{"name": "Крой", "children": []}],
    }

    first_response = client.post("/api/products", json=payload)
    assert first_response.status_code == 201

    second_response = client.post("/api/products", json=payload)

    assert second_response.status_code == 422
    assert (
        second_response.json()["detail"]
        == "Product with this name and version already exists."
    )


def test_create_product_rejects_empty_operation_name(client: TestClient) -> None:
    author_user = create_author_user(client)
    response = client.post(
        "/api/products",
        json={
            "name": "Рюкзак Field Pack",
            "version": "0.9",
            "author_user_id": author_user["id"],
            "operations": [
                {"name": " ", "children": []},
            ],
        },
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"][0]["msg"]
        == "Value error, Operation name must not be empty."
    )


def test_create_product_rejects_operation_outside_catalog(
    client: TestClient,
) -> None:
    author_user = create_author_user(client)
    ensure_operation_catalog_entries(client, ["Крой"])

    response = client.post(
        "/api/products",
        json={
            "name": "Рюкзак Catalog Guard",
            "version": "1.0",
            "author_user_id": author_user["id"],
            "operations": [
                {"name": "Крой", "children": []},
                {"name": "Прошивка", "children": []},
            ],
        },
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Operations must be selected from the operation catalog."
    )


def test_delete_product_removes_it(client: TestClient) -> None:
    author_user = create_author_user(client)
    ensure_operation_catalog_entries(client, ["Сборка"])
    create_response = client.post(
        "/api/products",
        json={
            "name": "Портмоне Classic",
            "version": "1.1",
            "author_user_id": author_user["id"],
            "operations": [{"name": "Сборка", "children": []}],
        },
    )
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/products/{product_id}")

    assert delete_response.status_code == 204

    get_response = client.get(f"/api/products/{product_id}")

    assert get_response.status_code == 404
    assert get_response.json()["detail"] == f"Product {product_id} not found."


def test_delete_product_rejects_version_used_by_order(client: TestClient) -> None:
    """
    Проверяем защиту используемой версии изделия:
    - создать заказ по версии изделия
    - запретить физическое удаление изделия и связанных заказов
    - сохранить возможность деактивации вместо удаления
    """
    product = create_stage_test_product(client, "Сумка Delete Guard")
    create_order_response = client.post(
        "/api/orders",
        json={
            "product_id": product["id"],
            "leather_type_id": None,
            "quantity": 1,
            "estimated_minutes": 0,
            "assignments": [
                {
                    "operation_id": operation["id"],
                    "worker_user_id": None,
                }
                for operation in product["operations"]
            ],
        },
    )
    assert create_order_response.status_code == 201

    delete_response = client.delete(f"/api/products/{product['id']}")

    assert delete_response.status_code == 409
    assert delete_response.json()["detail"] == (
        "Нельзя удалить изделие, которое уже используется в заказах. "
        "Изделие можно деактивировать."
    )
    assert client.get(f"/api/products/{product['id']}").status_code == 200
    status_response = client.patch(
        f"/api/products/{product['id']}/status",
        json={"is_active": False},
    )
    assert status_response.status_code == 200
    assert status_response.json()["is_active"] is False


def test_update_product_status(client: TestClient) -> None:
    author_user = create_author_user(client)
    ensure_operation_catalog_entries(client, ["Сборка"])
    create_response = client.post(
        "/api/products",
        json={
            "name": "Портфель Office Line",
            "version": "1.0",
            "author_user_id": author_user["id"],
            "operations": [{"name": "Сборка", "children": []}],
        },
    )
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/products/{product_id}/status",
        json={"is_active": False},
    )

    assert patch_response.status_code == 200
    updated_product = patch_response.json()
    assert updated_product["is_active"] is False

    list_response = client.get("/api/products")
    assert list_response.status_code == 200
    assert list_response.json()[0]["is_active"] is False


def test_get_unknown_product_returns_404(client: TestClient) -> None:
    response = client.get("/api/products/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Product 999 not found."


def test_create_product_without_author_uses_default_author(client: TestClient) -> None:
    ensure_operation_catalog_entries(client, ["Крой"])
    response = client.post(
        "/api/products",
        json={
            "name": "Обложка Heritage",
            "version": "1.0",
            "operations": [{"name": "Крой", "children": []}],
        },
    )

    assert response.status_code == 201
    assert response.json()["author"]

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.work_order import WorkOrder
from app.models.work_shift import WorkShift
from app.schemas.timer import TimerSwitchPayload, TimerType
from app.services.timer_service import TIMER_TYPE_TO_CODE, TimerService


def create_author_user(client: TestClient, name: str = "Марина Волкова") -> dict:
    phone_suffix = sum(ord(char) for char in name) % 10_000
    response = client.post(
        "/api/users",
        json={
            "name": name,
            "phone": f"+7999222{phone_suffix:04d}",
            "roles": ["constructor"],
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_worker_user(client: TestClient, name: str = "Ирина Соколова") -> dict:
    phone_suffix = (sum(ord(char) for char in name) + 5000) % 10_000
    response = client.post(
        "/api/users",
        json={
            "name": name,
            "phone": f"+7999333{phone_suffix:04d}",
            "roles": ["worker"],
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_brigadier_user(
    client: TestClient,
    name: str = "Бригадир Производства",
) -> dict:
    phone_suffix = (sum(ord(char) for char in name) + 6000) % 10_000
    response = client.post(
        "/api/users",
        json={
            "name": name,
            "phone": f"+7999555{phone_suffix:04d}",
            "roles": ["brigadier"],
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_quality_control_user(
    client: TestClient,
    name: str = "ОТК Контролер",
) -> dict:
    phone_suffix = (sum(ord(char) for char in name) + 7000) % 10_000
    response = client.post(
        "/api/users",
        json={
            "name": name,
            "phone": f"+7999444{phone_suffix:04d}",
            "roles": ["quality_control"],
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_leather_type(client: TestClient, name: str = "Краст") -> dict:
    response = client.post("/api/leather-types", json={"name": name})
    assert response.status_code == 201
    return response.json()


def ensure_operation_catalog_entries(
    client: TestClient,
    names: list[str],
) -> None:
    for name in names:
        response = client.post("/api/operation-catalog", json={"name": name})
        assert response.status_code in {201, 422}


def create_product_with_leaf_operations(
    client: TestClient,
    author_user_id: int,
    name: str = "Сумка City Tote",
    version: str = "1.0",
) -> dict:
    ensure_operation_catalog_entries(client, ["Фронт", "Спинка", "Пошив"])
    response = client.post(
        "/api/products",
        json={
            "name": name,
            "version": version,
            "author_user_id": author_user_id,
            "operations": [
                {
                    "name": "Подготовка",
                    "children": [
                        {
                            "name": "Фронт",
                            "standard_time_seconds": 90,
                            "children": [],
                        },
                        {
                            "name": "Спинка",
                            "standard_time_seconds": 120,
                            "children": [],
                        },
                    ],
                },
                {
                    "name": "Пошив",
                    "standard_time_seconds": 300,
                    "children": [],
                },
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def collect_leaf_operation_ids(product: dict) -> list[int]:
    leaf_ids: list[int] = []

    def walk(nodes: list[dict]) -> None:
        for node in nodes:
            if node["children"]:
                walk(node["children"])
            else:
                leaf_ids.append(node["id"])

    walk(product["operations"])
    return leaf_ids


def move_order_to_in_work(client: TestClient, order_id: int) -> dict:
    cutting_response = client.patch(
        f"/api/orders/{order_id}/production-stage",
        json={"production_stage": "cutting"},
    )
    assert cutting_response.status_code == 200
    in_work_response = client.patch(
        f"/api/orders/{order_id}/production-stage",
        json={"production_stage": "in_work"},
    )
    assert in_work_response.status_code == 200
    return dict(in_work_response.json())


def test_create_order_and_get_it(client: TestClient) -> None:
    """
    Проверяем создание заказа с итоговым временем в секундах:
    - создать заказ с изделием, материалом и назначениями
    - вернуть нулевое итоговое время через секундный контракт API
    - изменить плановую дату администратором и бригадиром
    """
    author = create_author_user(client)
    worker = create_worker_user(client)
    brigadier = create_brigadier_user(client)
    leather_type = create_leather_type(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0101",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "leather_type_id": leather_type["id"],
            "quantity": 12,
            "estimated_minutes": 210,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )

    assert create_response.status_code == 201
    created_order = create_response.json()
    assert created_order["order_number"] == "FC-0101"
    assert created_order["quantity"] == 12
    assert created_order["planned_completion_date"] == "2026-09-30"
    assert created_order["product_name"] == product["name"]
    assert created_order["leather_type_id"] == leather_type["id"]
    assert created_order["leather_type_name"] == leather_type["name"]
    assert created_order["estimated_minutes"] == 210
    assert created_order["total_spent_seconds"] == 0
    assert created_order["cutting_spent_seconds"] == 0
    assert created_order["quantity_change_allowed"] is False
    assert "total_spent_minutes" not in created_order
    assert created_order["production_stage"] == "created"
    assert created_order["cutting_started_at"] is None
    assert created_order["taken_at"] is None
    assert created_order["quality_control_at"] is None
    assert created_order["defect_quantity"] == 0
    assert created_order["completed_at"] is None
    assert created_order["deleted_at"] is None
    assert len(created_order["assignments"]) == 3
    assert {
        assignment["operation_kind"] for assignment in created_order["assignments"]
    } == {"regular"}

    get_response = client.get(f"/api/orders/{created_order['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["order_number"] == "FC-0101"
    assert get_response.json()["leather_type_name"] == leather_type["name"]

    delete_response = client.patch(
        f"/api/orders/{created_order['id']}/deleted-status",
        json={"is_deleted": True},
    )
    assert delete_response.status_code == 200

    admin_planned_date_response = client.patch(
        f"/api/orders/{created_order['id']}/planned-completion-date",
        json={"planned_completion_date": "2026-10-05"},
    )
    assert admin_planned_date_response.status_code == 200
    assert (
        admin_planned_date_response.json()["planned_completion_date"]
        == "2026-10-05"
    )

    setup_response = client.post(
        "/api/auth/setup-password",
        json={
            "phone": brigadier["phone"],
            "new_password": "password123",
        },
    )
    assert setup_response.status_code == 200

    planned_date_response = client.patch(
        f"/api/orders/{created_order['id']}/planned-completion-date",
        json={"planned_completion_date": "2026-10-06"},
    )
    assert planned_date_response.status_code == 200
    assert planned_date_response.json()["planned_completion_date"] == "2026-10-06"
    assert planned_date_response.json()["deleted_at"] is not None


def test_cutting_stage_filter_keeps_all_planned_assignments(
    client: TestClient,
) -> None:
    """
    Проверяем список заказов на стадии кроя:
    - найти заказ по части номера и наименования
    - показать количество всех запланированных исполнителей
    - открыть обычные операции исполнителю только после передачи в работу
    """
    author = create_author_user(client, name="Автор кроя")
    worker = create_worker_user(client, name="Исполнитель кроя")
    product = create_product_with_leaf_operations(
        client,
        author["id"],
        name="Сумка для кроя",
    )
    leaf_ids = collect_leaf_operation_ids(product)
    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-CUT-100",
            "product_id": product["id"],
            "quantity": 5,
            "assignments": [
                {"operation_id": operation_id, "worker_user_id": worker["id"]}
                for operation_id in leaf_ids
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    cutting_response = client.patch(
        f"/api/orders/{order_id}/production-stage",
        json={"production_stage": "cutting"},
    )
    assert cutting_response.status_code == 200

    number_search_response = client.get("/api/orders?status=cutting&search=cut-1")
    assert number_search_response.status_code == 200
    assert number_search_response.json()["total"] == 1
    cutting_order = number_search_response.json()["items"][0]
    assert cutting_order["production_stage"] == "cutting"
    assert cutting_order["assignments_count"] == len(leaf_ids)
    assert cutting_order["cutting_started_at"] is None
    assert cutting_order["cutting_spent_seconds"] == 0

    name_search_response = client.get("/api/orders?status=cutting&search=для кроя")
    assert name_search_response.status_code == 200
    assert name_search_response.json()["total"] == 1
    setup_response = client.post(
        "/api/auth/setup-password",
        json={
            "phone": worker["phone"],
            "new_password": "password123",
        },
    )
    assert setup_response.status_code == 200
    worker_cutting_response = client.get(
        "/api/orders/worker-assignments?status=in_work"
    )
    assert worker_cutting_response.status_code == 200
    assert worker_cutting_response.json() == []

    in_work_response = client.patch(
        f"/api/orders/{order_id}/production-stage",
        json={"production_stage": "in_work"},
    )
    assert in_work_response.status_code == 200
    worker_in_work_response = client.get(
        "/api/orders/worker-assignments?status=in_work"
    )
    assert worker_in_work_response.status_code == 200
    assert len(worker_in_work_response.json()[0]["assignments"]) == len(leaf_ids)


def test_adjacent_assignment_is_visible_during_cutting_and_in_work(
    client: TestClient,
) -> None:
    """
    Проверяем видимость смежной операции исполнителю:
    - скрыть назначение в созданных и ОТК
    - показать назначение в крое и в работе, включая переход по QR
    - вернуть тип операции в детальном контракте заказа
    """
    author = create_author_user(client, name="Автор смежной операции")
    worker = create_worker_user(client, name="Исполнитель смежной операции")
    product = create_product_with_leaf_operations(
        client,
        author["id"],
        name="Изделие со смежной операцией",
    )
    operation_ids = collect_leaf_operation_ids(product)
    operation_id = operation_ids[0]
    catalog_response = client.get("/api/operation-catalog?search=Фронт")
    assert catalog_response.status_code == 200
    catalog_entry_id = catalog_response.json()["items"][0]["id"]
    kind_response = client.patch(
        f"/api/operation-catalog/{catalog_entry_id}/kind",
        json={"operation_kind": "adjacent"},
    )
    assert kind_response.status_code == 200

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-ADJ-100",
            "product_id": product["id"],
            "quantity": 3,
            "assignments": [
                {
                    "operation_id": current_operation_id,
                    "worker_user_id": (
                        worker["id"] if current_operation_id == operation_id else None
                    ),
                }
                for current_operation_id in operation_ids
            ],
        },
    )
    assert create_response.status_code == 201
    created_order = create_response.json()
    order_id = created_order["id"]
    adjacent_assignment = next(
        assignment
        for assignment in created_order["assignments"]
        if assignment["operation_id"] == operation_id
    )
    assert adjacent_assignment["operation_kind"] == "adjacent"

    setup_response = client.post(
        "/api/auth/setup-password",
        json={
            "phone": worker["phone"],
            "new_password": "password123",
        },
    )
    assert setup_response.status_code == 200

    created_response = client.get("/api/orders/worker-assignments")
    assert created_response.status_code == 200
    assert created_response.json() == []

    cutting_response = client.patch(
        f"/api/orders/{order_id}/production-stage",
        json={"production_stage": "cutting"},
    )
    assert cutting_response.status_code == 200
    cutting_assignments_response = client.get("/api/orders/worker-assignments")
    assert cutting_assignments_response.status_code == 200
    assert [
        assignment["operation_name"]
        for assignment in cutting_assignments_response.json()[0]["assignments"]
    ] == ["Фронт"]
    cutting_qr_response = client.get(
        f"/api/orders/worker-assignments/qr-target?legacy_order_id={order_id}"
    )
    assert cutting_qr_response.status_code == 200
    assert cutting_qr_response.json()["orders"][0]["assignments"][0][
        "operation_name"
    ] == "Фронт"

    in_work_response = client.patch(
        f"/api/orders/{order_id}/production-stage",
        json={"production_stage": "in_work"},
    )
    assert in_work_response.status_code == 200
    in_work_assignments_response = client.get("/api/orders/worker-assignments")
    assert in_work_assignments_response.status_code == 200
    assert in_work_assignments_response.json()[0]["assignments"][0][
        "operation_name"
    ] == "Фронт"
    in_work_qr_response = client.get(
        f"/api/orders/worker-assignments/qr-target?legacy_order_id={order_id}"
    )
    assert in_work_qr_response.status_code == 200
    assert in_work_qr_response.json()["orders"][0]["assignments"][0][
        "operation_name"
    ] == "Фронт"

    quality_response = client.patch(
        f"/api/orders/{order_id}/quality-control-status",
        json={"is_in_quality_control": True},
    )
    assert quality_response.status_code == 200
    quality_assignments_response = client.get("/api/orders/worker-assignments")
    assert quality_assignments_response.status_code == 200
    assert quality_assignments_response.json() == []
    quality_qr_response = client.get(
        f"/api/orders/worker-assignments/qr-target?legacy_order_id={order_id}"
    )
    assert quality_qr_response.status_code == 200
    assert quality_qr_response.json()["orders"] == []


def test_order_number_search_returns_all_current_stages(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем общий поиск заказа по номеру:
    - подготовить совпадающие заказы во всех стадиях, включая удалённый
    - найти их по частичному номеру и вернуть фактическую стадию
    - не искать совпадения по наименованию изделия
    """
    author = create_author_user(client)
    worker = create_worker_user(client, name="Галина Зайцева")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)
    assignments = [
        {"operation_id": operation_id, "worker_user_id": worker["id"]}
        for operation_id in leaf_ids
    ]
    order_numbers = [
        "SEARCH-100-CREATED",
        "SEARCH-100-CUTTING",
        "SEARCH-100-IN-WORK",
        "SEARCH-100-QUALITY",
        "SEARCH-100-COMPLETED",
        "SEARCH-100-DELETED",
    ]
    order_ids: dict[str, int] = {}
    for order_number in [*order_numbers, "UNRELATED-ORDER"]:
        response = client.post(
            "/api/orders",
            json={
                "order_number": order_number,
                "planned_completion_date": "2026-09-30",
                "product_id": product["id"],
                "quantity": 2,
                "assignments": assignments,
            },
        )
        assert response.status_code == 201
        order_ids[order_number] = response.json()["id"]

    session = db_session()
    try:
        cutting_order = session.get(WorkOrder, order_ids["SEARCH-100-CUTTING"])
        in_work_order = session.get(WorkOrder, order_ids["SEARCH-100-IN-WORK"])
        quality_order = session.get(WorkOrder, order_ids["SEARCH-100-QUALITY"])
        completed_order = session.get(WorkOrder, order_ids["SEARCH-100-COMPLETED"])
        deleted_order = session.get(WorkOrder, order_ids["SEARCH-100-DELETED"])
        assert cutting_order is not None
        assert in_work_order is not None
        assert quality_order is not None
        assert completed_order is not None
        assert deleted_order is not None
        cutting_order.production_stage = "cutting"
        in_work_order.production_stage = "in_work"
        quality_order.production_stage = "in_work"
        quality_order.quality_control_at = 1_000
        completed_order.production_stage = "in_work"
        completed_order.quality_control_at = 1_000
        completed_order.completed_at = 2_000
        deleted_order.deleted_at = 3_000
        session.commit()
    finally:
        session.close()

    response = client.get(
        "/api/orders/order-number-search",
        params={"search": "search-100"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["order_number"] for item in payload] == sorted(order_numbers)
    assert {item["order_number"]: item["stage"] for item in payload} == {
        "SEARCH-100-CREATED": "created",
        "SEARCH-100-CUTTING": "cutting",
        "SEARCH-100-IN-WORK": "in_work",
        "SEARCH-100-QUALITY": "quality_control",
        "SEARCH-100-COMPLETED": "completed",
        "SEARCH-100-DELETED": "deleted",
    }

    name_response = client.get(
        "/api/orders/order-number-search",
        params={"search": "City Tote"},
    )
    assert name_response.status_code == 200
    assert name_response.json() == []


def test_order_detail_uses_current_product_comment(client: TestClient) -> None:
    """
    Проверяем актуальный комментарий изделия в заказе:
    - создать заказ с исходным комментарием изделия
    - изменить комментарий после создания заказа
    - вернуть новый комментарий при повторном чтении заказа
    """
    author = create_author_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)
    initial_comment = "Блок операций 1: подготовка деталей"
    updated_comment = "Блок операций 1: крой\nБлок операций 2: пошив"

    comment_response = client.patch(
        f"/api/products/{product['id']}/costs",
        json={
            "material_cost_cents": product["material_cost_cents"],
            "comment": initial_comment,
            "operations": [],
        },
    )
    assert comment_response.status_code == 200

    create_response = client.post(
        "/api/orders",
        json={
            "product_id": product["id"],
            "quantity": 1,
            "assignments": [
                {"operation_id": operation_id, "worker_user_id": None}
                for operation_id in leaf_ids
            ],
        },
    )

    assert create_response.status_code == 201
    created_order = create_response.json()
    assert created_order["product_comment"] == initial_comment

    update_response = client.patch(
        f"/api/products/{product['id']}/costs",
        json={
            "material_cost_cents": product["material_cost_cents"],
            "comment": updated_comment,
            "operations": [],
        },
    )
    assert update_response.status_code == 200

    get_response = client.get(f"/api/orders/{created_order['id']}")

    assert get_response.status_code == 200
    assert get_response.json()["product_comment"] == updated_comment


def test_create_orders_assigns_sequential_numbers_when_number_omitted(
    client: TestClient,
) -> None:
    """
    Проверяем автоматическую нумерацию новых заказов:
    - отправить два заказа без номера
    - получить последовательные номера начиная с 10000
    """
    author = create_author_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)
    payload = {
        "product_id": product["id"],
        "quantity": 1,
        "assignments": [
            {"operation_id": operation_id, "worker_user_id": None}
            for operation_id in leaf_ids
        ],
    }

    first_response = client.post("/api/orders", json=payload)
    second_response = client.post("/api/orders", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["order_number"] == "10000"
    assert second_response.json()["order_number"] == "10001"


def test_create_order_skips_existing_numeric_number(client: TestClient) -> None:
    """
    Проверяем пропуск уже занятого цифрового номера:
    - создать существующий заказ с номером 10000
    - автоматически назначить следующему заказу номер 10001
    """
    author = create_author_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)
    payload = {
        "product_id": product["id"],
        "quantity": 1,
        "assignments": [
            {"operation_id": operation_id, "worker_user_id": None}
            for operation_id in leaf_ids
        ],
    }

    existing_response = client.post(
        "/api/orders",
        json={"order_number": "10000", **payload},
    )
    automatic_response = client.post("/api/orders", json=payload)

    assert existing_response.status_code == 201
    assert automatic_response.status_code == 201
    assert automatic_response.json()["order_number"] == "10001"


def test_create_order_allows_empty_operation_workers(client: TestClient) -> None:
    author = create_author_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0110",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 4,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": None},
                {"operation_id": leaf_ids[1], "worker_user_id": None},
                {"operation_id": leaf_ids[2], "worker_user_id": None},
            ],
        },
    )

    assert create_response.status_code == 201
    payload = create_response.json()
    assert len(payload["assignments"]) == 3
    assert all(
        assignment["worker_user_id"] is None for assignment in payload["assignments"]
    )
    assert all(
        assignment["worker_user_name"] is None for assignment in payload["assignments"]
    )


def test_create_order_allows_missing_planned_completion_date(
    client: TestClient,
) -> None:
    author = create_author_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0111",
            "product_id": product["id"],
            "quantity": 4,
            "assignments": [
                {"operation_id": operation_id, "worker_user_id": None}
                for operation_id in leaf_ids
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["planned_completion_date"] is None


def test_list_orders_returns_assignments_count(client: TestClient) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0102",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 5,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201

    default_list_response = client.get("/api/orders")
    assert default_list_response.status_code == 200
    assert default_list_response.json()["total"] == 0

    list_response = client.get("/api/orders?status=created")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 20
    assert payload["pages"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["assignments_count"] == 3
    assert payload["items"][0]["taken_at"] is None
    assert payload["items"][0]["completed_at"] is None
    assert payload["items"][0]["deleted_at"] is None


def test_get_order_time_breakdown_returns_operation_worker_totals(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    author = create_author_user(client)
    first_worker = create_worker_user(client, "Ирина Соколова")
    second_worker = create_worker_user(client, "Петр Орлов")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0140",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 5,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": second_worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    session = db_session()
    try:
        first_shift = WorkShift(
            user_id=first_worker["id"],
            started_at=1_000,
            ended_at=301_000,
            business_date="2026-06-01",
            created_at=1_000,
        )
        second_shift = WorkShift(
            user_id=second_worker["id"],
            started_at=1_000,
            ended_at=181_000,
            business_date="2026-06-01",
            created_at=1_000,
        )
        session.add_all([first_shift, second_shift])
        session.flush()
        session.add_all(
            [
                TimerSession(
                    shift_id=first_shift.id,
                    user_id=first_worker["id"],
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=order_id,
                    operation_id=leaf_ids[0],
                    started_at=1_000,
                    ended_at=121_000,
                    created_at=1_000,
                ),
                TimerSession(
                    shift_id=first_shift.id,
                    user_id=first_worker["id"],
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=order_id,
                    operation_id=leaf_ids[0],
                    started_at=121_000,
                    ended_at=151_000,
                    created_at=121_000,
                ),
                TimerSession(
                    shift_id=second_shift.id,
                    user_id=second_worker["id"],
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=order_id,
                    operation_id=leaf_ids[0],
                    started_at=121_000,
                    ended_at=171_000,
                    created_at=121_000,
                ),
                TimerSession(
                    shift_id=second_shift.id,
                    user_id=second_worker["id"],
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=order_id,
                    operation_id=leaf_ids[2],
                    started_at=1_000,
                    ended_at=61_000,
                    created_at=1_000,
                ),
                TimerSession(
                    shift_id=second_shift.id,
                    user_id=second_worker["id"],
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.PREPARATION],
                    order_id=None,
                    operation_id=None,
                    started_at=61_000,
                    ended_at=121_000,
                    created_at=61_000,
                ),
                TimerSession(
                    shift_id=first_shift.id,
                    user_id=first_worker["id"],
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=order_id,
                    operation_id=leaf_ids[1],
                    started_at=151_000,
                    ended_at=None,
                    created_at=151_000,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = client.get(f"/api/orders/{order_id}/time-breakdown")

    assert response.status_code == 200
    payload = response.json()
    assert payload["order_id"] == order_id
    assert payload["total_standard_time_seconds"] == 510
    assert payload["total_elapsed_ms"] == 260_000
    rows = {
        (item["operation_id"], item["worker_user_id"]): item
        for item in payload["items"]
    }
    assert rows[(leaf_ids[0], first_worker["id"])]["operation_name"] == "Фронт"
    assert (
        rows[(leaf_ids[0], first_worker["id"])]["worker_user_name"]
        == first_worker["name"]
    )
    assert rows[(leaf_ids[0], first_worker["id"])]["elapsed_ms"] == 150_000
    assert rows[(leaf_ids[0], first_worker["id"])]["standard_time_seconds"] == 90
    assert rows[(leaf_ids[0], first_worker["id"])]["average_elapsed_ms"] == 40_000
    assert rows[(leaf_ids[0], second_worker["id"])]["elapsed_ms"] == 50_000
    assert rows[(leaf_ids[0], second_worker["id"])]["average_elapsed_ms"] == 40_000
    assert rows[(leaf_ids[2], second_worker["id"])]["elapsed_ms"] == 60_000
    assert rows[(leaf_ids[2], second_worker["id"])]["standard_time_seconds"] == 300
    assert rows[(leaf_ids[2], second_worker["id"])]["average_elapsed_ms"] == 12_000
    assert (leaf_ids[1], first_worker["id"]) not in rows


def test_worker_assignments_returns_current_worker_in_work_orders(
    client: TestClient,
) -> None:
    """
    Проверяем список текущих назначений исполнителя:
    - перевести часть заказов в работу и ОТК
    - вернуть только доступные заказы текущего пользователя
    """
    current_session = client.get("/api/auth/me").json()
    worker = client.get(f"/api/users/{current_session['user_id']}").json()
    update_response = client.put(
        f"/api/users/{worker['id']}",
        json={
            "name": worker["name"],
            "phone": worker["phone"],
            "roles": ["admin", "worker"],
            "is_active": True,
            "author_user_id": worker["author_user_id"],
        },
    )
    assert update_response.status_code == 200

    other_worker = create_worker_user(client, "Ольга Исполнитель")
    product = create_product_with_leaf_operations(client, worker["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    def create_order(
        order_number: str,
        first_operation_worker_id: int,
        *,
        is_taken: bool,
        is_quality_control: bool = False,
    ) -> dict:
        response = client.post(
            "/api/orders",
            json={
                "order_number": order_number,
                "planned_completion_date": "2026-09-30",
                "product_id": product["id"],
                "quantity": 1,
                "assignments": [
                    {
                        "operation_id": leaf_ids[0],
                        "worker_user_id": first_operation_worker_id,
                    },
                    {
                        "operation_id": leaf_ids[1],
                        "worker_user_id": other_worker["id"],
                    },
                    {"operation_id": leaf_ids[2], "worker_user_id": None},
                ],
            },
        )
        assert response.status_code == 201
        order = response.json()

        if is_taken:
            move_order_to_in_work(client, order["id"])

        if is_quality_control:
            quality_control_response = client.patch(
                f"/api/orders/{order['id']}/quality-control-status",
                json={"is_in_quality_control": True},
            )
            assert quality_control_response.status_code == 200

        return order

    create_order("FC-WA-1", worker["id"], is_taken=True)
    create_order("FC-WA-2", worker["id"], is_taken=False)
    create_order("FC-WA-3", other_worker["id"], is_taken=True)
    create_order("FC-WA-4", worker["id"], is_taken=True, is_quality_control=True)

    response = client.get("/api/orders/worker-assignments")

    assert response.status_code == 200
    payload = response.json()
    assert [order["order_number"] for order in payload] == ["FC-WA-1"]
    assert payload[0]["assignments"] == [
        {
            "id": payload[0]["assignments"][0]["id"],
            "operation_id": leaf_ids[0],
            "operation_name": "Фронт",
                "operation_kind": "regular",
            "worker_user_id": worker["id"],
            "worker_user_name": worker["name"],
            "worker_status": "in_work",
            "worker_hidden_at": None,
            "worker_completed_at": None,
        },
    ]


def test_worker_assignment_status_filters_by_current_worker(
    client: TestClient,
) -> None:
    """
    Проверяем персональные статусы назначений:
    - скрыть и завершить отдельные операции исполнителя
    - разнести назначения по соответствующим фильтрам
    """
    current_session = client.get("/api/auth/me").json()
    worker = client.get(f"/api/users/{current_session['user_id']}").json()
    update_response = client.put(
        f"/api/users/{worker['id']}",
        json={
            "name": worker["name"],
            "phone": worker["phone"],
            "roles": ["admin", "worker"],
            "is_active": True,
            "author_user_id": worker["author_user_id"],
        },
    )
    assert update_response.status_code == 200

    product = create_product_with_leaf_operations(client, worker["id"])
    leaf_ids = collect_leaf_operation_ids(product)
    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-WA-STATUS",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 1,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]
    move_order_to_in_work(client, order_id)

    active_response = client.get("/api/orders/worker-assignments?status=in_work")
    assert active_response.status_code == 200
    active_assignments = active_response.json()[0]["assignments"]
    first_assignment_id = active_assignments[0]["id"]
    second_assignment_id = active_assignments[1]["id"]

    hidden_response = client.patch(
        f"/api/orders/worker-assignments/{first_assignment_id}/status",
        json={"status": "hidden"},
    )
    assert hidden_response.status_code == 200
    assert hidden_response.json()["assignments"][0]["worker_status"] == "hidden"

    completed_response = client.patch(
        f"/api/orders/worker-assignments/{second_assignment_id}/status",
        json={"status": "completed"},
    )
    assert completed_response.status_code == 200
    assert completed_response.json()["assignments"][1]["worker_status"] == "completed"

    active_after_response = client.get("/api/orders/worker-assignments")
    assert active_after_response.status_code == 200
    assert [
        assignment["operation_id"]
        for assignment in active_after_response.json()[0]["assignments"]
    ] == [leaf_ids[2]]

    hidden_list_response = client.get("/api/orders/worker-assignments?status=hidden")
    assert hidden_list_response.status_code == 200
    hidden_payload = hidden_list_response.json()
    assert hidden_payload[0]["assignments"][0]["operation_id"] == leaf_ids[0]
    assert hidden_payload[0]["assignments"][0]["worker_status"] == "hidden"

    completed_list_response = client.get(
        "/api/orders/worker-assignments?status=completed"
    )
    assert completed_list_response.status_code == 200
    completed_payload = completed_list_response.json()
    assert completed_payload[0]["assignments"][0]["operation_id"] == leaf_ids[1]
    assert completed_payload[0]["assignments"][0]["worker_status"] == "completed"

    restore_response = client.patch(
        f"/api/orders/worker-assignments/{first_assignment_id}/status",
        json={"status": "in_work"},
    )
    assert restore_response.status_code == 200

    restored_active_response = client.get("/api/orders/worker-assignments")
    assert restored_active_response.status_code == 200
    assert {
        assignment["operation_id"]
        for assignment in restored_active_response.json()[0]["assignments"]
    } == {leaf_ids[0], leaf_ids[2]}


def test_list_orders_filters_sorts_and_paginates(client: TestClient) -> None:
    """
    Проверяем фильтрацию, сортировку и пагинацию заказов:
    - создать заказы на разных стадиях
    - вернуть ожидаемый порядок и состав страницы
    """
    author = create_author_user(client)
    worker = create_worker_user(client)
    quality_control_user = create_quality_control_user(client, "ОТК Сортировка")

    def create_order(
        order_number: str,
        product_name: str,
        *,
        version: str = "1.0",
    ) -> dict:
        product = create_product_with_leaf_operations(
            client,
            author["id"],
            name=product_name,
            version=version,
        )
        leaf_ids = collect_leaf_operation_ids(product)

        response = client.post(
            "/api/orders",
            json={
                "order_number": order_number,
                "planned_completion_date": "2026-09-30",
                "product_id": product["id"],
                "quantity": 1,
                "assignments": [
                    {"operation_id": operation_id, "worker_user_id": worker["id"]}
                    for operation_id in leaf_ids
                ],
            },
        )
        assert response.status_code == 201
        return response.json()

    create_order("FC-0302", "Beta Pack", version="2.0")
    create_order("FC-0301", "Alpha Bag", version="1.0")
    create_order("FC-0304", "Сумка Марс", version="3.0")
    completed_order = create_order("FC-0303", "Gamma Case", version="4.0")
    move_order_to_in_work(client, completed_order["id"])
    quality_control_response = client.patch(
        f"/api/orders/{completed_order['id']}/quality-control-status",
        json={"is_in_quality_control": True},
    )
    assert quality_control_response.status_code == 200

    setup_response = client.post(
        "/api/auth/setup-password",
        json={
            "phone": quality_control_user["phone"],
            "new_password": "password123",
        },
    )
    assert setup_response.status_code == 200

    completed_response = client.patch(
        f"/api/orders/{completed_order['id']}/quality-control-acceptance",
        json={"defect_quantity": 0},
    )
    assert completed_response.status_code == 200

    first_page_response = client.get(
        "/api/orders?status=created&sort_by=name&sort_direction=asc&page=1&page_size=1"
    )
    assert first_page_response.status_code == 200
    first_page = first_page_response.json()
    assert first_page["total"] == 3
    assert first_page["pages"] == 3
    assert len(first_page["items"]) == 1
    assert first_page["items"][0]["order_number"] == "FC-0301"

    second_page_response = client.get(
        "/api/orders?status=created&sort_by=name&sort_direction=asc&page=2&page_size=1"
    )
    assert second_page_response.status_code == 200
    second_page = second_page_response.json()
    assert second_page["items"][0]["order_number"] == "FC-0302"

    search_response = client.get("/api/orders?status=created&search=fc-0302")
    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["total"] == 1
    assert search_payload["items"][0]["product_name"] == "Beta Pack"

    cyrillic_search_response = client.get("/api/orders?status=created&search=сУм")
    assert cyrillic_search_response.status_code == 200
    cyrillic_search_payload = cyrillic_search_response.json()
    assert cyrillic_search_payload["total"] == 1
    assert cyrillic_search_payload["items"][0]["order_number"] == "FC-0304"

    hidden_completed_response = client.get("/api/orders?status=created&search=0303")
    assert hidden_completed_response.status_code == 200
    assert hidden_completed_response.json()["total"] == 0

    visible_completed_response = client.get(
        "/api/orders?status=completed&search=0303&sort_by=completed&sort_direction=desc"
    )
    assert visible_completed_response.status_code == 200
    visible_completed_payload = visible_completed_response.json()
    assert visible_completed_payload["total"] == 1
    assert visible_completed_payload["items"][0]["order_number"] == "FC-0303"
    assert visible_completed_payload["items"][0]["completed_at"] is not None

    order_number_response = client.get(
        "/api/orders?status=created&sort_by=order_number&sort_direction=desc"
    )
    assert order_number_response.status_code == 200
    assert order_number_response.json()["items"][0]["order_number"] == "FC-0304"

    for sort_by in [
        "completed",
        "created",
        "defect",
        "name",
        "order_number",
        "planned_completion",
        "quality_control",
        "taken",
    ]:
        response = client.get(f"/api/orders?status=created&sort_by={sort_by}")
        assert response.status_code == 200


def test_create_order_rejects_duplicate_number(client: TestClient) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)
    payload = {
        "order_number": "FC-0103",
        "planned_completion_date": "2026-09-30",
        "product_id": product["id"],
        "quantity": 3,
        "assignments": [
            {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
            {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
            {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
        ],
    }

    first_response = client.post("/api/orders", json=payload)
    assert first_response.status_code == 201

    second_response = client.post("/api/orders", json=payload)
    assert second_response.status_code == 422
    assert second_response.json()["detail"] == "Order with this number already exists."


def test_create_order_rejects_inactive_product(client: TestClient) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    patch_response = client.patch(
        f"/api/products/{product['id']}/status",
        json={"is_active": False},
    )
    assert patch_response.status_code == 200

    response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0104",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 1,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Only active products can be taken into work."


def test_create_order_rejects_inactive_leather_type(client: TestClient) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leather_type = create_leather_type(client, name="Нубук")
    leaf_ids = collect_leaf_operation_ids(product)

    patch_response = client.patch(
        f"/api/leather-types/{leather_type['id']}/status",
        json={"is_active": False},
    )
    assert patch_response.status_code == 200

    response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0108",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "leather_type_id": leather_type["id"],
            "quantity": 1,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Only active leather types can be selected."


def test_create_order_rejects_non_worker_assignment(client: TestClient) -> None:
    author = create_author_user(client)
    non_worker = create_author_user(client, name="Ольга Белова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0105",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 2,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": non_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": non_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": non_worker["id"]},
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Assigned user must be an active worker."


def test_update_order_assignments_changes_worker(client: TestClient) -> None:
    """
    Проверяем изменение исполнителей заказа:
    - заменить исполнителя всех операций
    - сохранить количество, оценку и нулевое итоговое время в секундах
    """
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="Наталья Лебедева")
    second_worker = create_worker_user(client, name="Елена Громова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0106",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 7,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": first_worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 7,
            "estimated_minutes": 480,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": second_worker["id"]},
            ],
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["quantity"] == 7
    assert payload["estimated_minutes"] == 480
    assert payload["total_spent_seconds"] == 0
    assert all(
        assignment["worker_user_name"] == second_worker["name"]
        for assignment in payload["assignments"]
    )


def test_order_allows_multiple_workers_for_one_operation(
    client: TestClient,
) -> None:
    """
    Проверяем множественное назначение на одну операцию:
    - назначить двух разных исполнителей на одну операцию
    - вернуть оба назначения без удвоения общего норматива заказа
    """
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="Лариса Котова")
    second_worker = create_worker_user(client, name="Нина Миронова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0106-1",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 7,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[0], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": first_worker["id"]},
            ],
        },
    )

    assert create_response.status_code == 201
    payload = create_response.json()
    first_operation_worker_ids = {
        assignment["worker_user_id"]
        for assignment in payload["assignments"]
        if assignment["operation_id"] == leaf_ids[0]
    }
    assert first_operation_worker_ids == {first_worker["id"], second_worker["id"]}

    breakdown_response = client.get(
        f"/api/orders/{payload['id']}/time-breakdown"
    )
    assert breakdown_response.status_code == 200
    assert breakdown_response.json()["total_standard_time_seconds"] == 510


def test_order_rejects_duplicate_worker_for_one_operation(
    client: TestClient,
) -> None:
    """
    Проверяем уникальность исполнителя внутри операции:
    - передать одного исполнителя дважды для одной операции
    - отклонить создание заказа с повторным назначением
    """
    author = create_author_user(client)
    worker = create_worker_user(client, name="Вера Фомина")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0106-2",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 7,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "A worker can be assigned to an operation only once."
    )


def test_update_order_adds_and_removes_additional_worker(
    client: TestClient,
) -> None:
    """
    Проверяем редактирование нескольких исполнителей операции:
    - добавить второго исполнителя к существующему назначению
    - удалить первого исполнителя и сохранить остальные операции
    """
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="Тамара Белова")
    second_worker = create_worker_user(client, name="Юлия Демина")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)
    base_assignments = [
        {"operation_id": operation_id, "worker_user_id": first_worker["id"]}
        for operation_id in leaf_ids
    ]

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0106-4",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 7,
            "assignments": base_assignments,
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    add_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 7,
            "estimated_minutes": 480,
            "assignments": [
                base_assignments[0],
                {"operation_id": leaf_ids[0], "worker_user_id": second_worker["id"]},
                *base_assignments[1:],
            ],
        },
    )
    assert add_response.status_code == 200
    assert {
        assignment["worker_user_id"]
        for assignment in add_response.json()["assignments"]
        if assignment["operation_id"] == leaf_ids[0]
    } == {first_worker["id"], second_worker["id"]}

    remove_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 7,
            "estimated_minutes": 480,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": second_worker["id"]},
                *base_assignments[1:],
            ],
        },
    )
    assert remove_response.status_code == 200
    assert [
        assignment["worker_user_id"]
        for assignment in remove_response.json()["assignments"]
        if assignment["operation_id"] == leaf_ids[0]
    ] == [second_worker["id"]]


def test_update_order_rejects_removing_worker_with_active_timer(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем защиту активного таймера при изменении назначений:
    - запустить таймер одного из исполнителей общей операции
    - отклонить удаление только этого исполнителя из заказа
    """
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="Ирина Костина")
    second_worker = create_worker_user(client, name="Ольга Лукина")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0106-3",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 7,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[0], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": first_worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]
    move_order_to_in_work(client, order_id)

    session = db_session()
    try:
        shift = WorkShift(
            user_id=second_worker["id"],
            started_at=1_000,
            ended_at=None,
            business_date="2026-10-25",
            created_at=1_000,
        )
        session.add(shift)
        session.flush()
        session.add(
            TimerSession(
                shift_id=shift.id,
                user_id=second_worker["id"],
                timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                order_id=order_id,
                operation_id=leaf_ids[0],
                started_at=1_000,
                ended_at=None,
                created_at=1_000,
            )
        )
        session.commit()
    finally:
        session.close()

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 7,
            "estimated_minutes": 480,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": first_worker["id"]},
            ],
        },
    )

    assert update_response.status_code == 422
    assert update_response.json()["detail"] == (
        "Нельзя удалить исполнителя из операции: сначала остановить его "
        "запущенный таймер."
    )


def test_update_order_allows_empty_operation_workers(client: TestClient) -> None:
    """
    Проверяем очистку исполнителей операций:
    - передать пустых исполнителей для всех назначений
    - сохранить оценку и нулевое итоговое время в секундах
    """
    author = create_author_user(client)
    worker = create_worker_user(client, name="Алла Орлова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0111",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 5,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 5,
            "estimated_minutes": 300,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": None},
                {"operation_id": leaf_ids[1], "worker_user_id": None},
                {"operation_id": leaf_ids[2], "worker_user_id": None},
            ],
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["estimated_minutes"] == 300
    assert payload["total_spent_seconds"] == 0
    assert all(
        assignment["worker_user_id"] is None for assignment in payload["assignments"]
    )
    assert all(
        assignment["worker_user_name"] is None for assignment in payload["assignments"]
    )


def test_update_order_rejects_quantity_change_outside_cutting(
    client: TestClient,
) -> None:
    """
    Проверяем неизменяемость количества до стадии кроя:
    - попытаться изменить количество созданного заказа
    - потребовать сначала перевести заказ в крой
    """
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="Полина Кузнецова")
    second_worker = create_worker_user(client, name="Мария Тихонова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0113",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 7,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": first_worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 8,
            "estimated_minutes": 480,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": second_worker["id"]},
            ],
        },
    )

    assert update_response.status_code == 422
    assert update_response.json()["detail"] == (
        "Order quantity can only be changed during cutting stage."
    )


def test_update_order_allows_leather_type_change_without_spent_time(
    client: TestClient,
) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client, name="Людмила Фролова")
    product = create_product_with_leaf_operations(client, author["id"])
    first_leather_type = create_leather_type(client, name="Шорно-седельная")
    second_leather_type = create_leather_type(client, name="Спилок")
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0114",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "leather_type_id": first_leather_type["id"],
            "quantity": 3,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "leather_type_id": second_leather_type["id"],
            "quantity": 3,
            "estimated_minutes": 180,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["leather_type_id"] == second_leather_type["id"]
    assert payload["leather_type_name"] == second_leather_type["name"]


def test_update_order_allows_assignment_change_after_taken_before_quality_control(
    client: TestClient,
) -> None:
    """
    Проверяем изменение исполнителей заказа в работе:
    - перевести заказ в работу без учтенного времени
    - сохранить новые назначения до передачи в ОТК
    """
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="Олеся Сафонова")
    second_worker = create_worker_user(client, name="Евгения Третьякова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0117",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 3,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": first_worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    taken_payload = move_order_to_in_work(client, order_id)
    assert taken_payload["has_spent_time"] is False

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 3,
            "estimated_minutes": 180,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": second_worker["id"]},
            ],
        },
    )

    assert update_response.status_code == 200
    assert all(
        assignment["worker_user_name"] == second_worker["name"]
        for assignment in update_response.json()["assignments"]
    )


def test_update_order_rejects_assignment_change_in_quality_control(
    client: TestClient,
) -> None:
    """
    Проверяем неизменяемость назначений на стадии ОТК:
    - передать заказ из работы в ОТК
    - отклонить замену исполнителей
    """
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="София Беляева")
    second_worker = create_worker_user(client, name="Алина Крылова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0119",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 3,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": first_worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    move_order_to_in_work(client, order_id)

    quality_control_response = client.patch(
        f"/api/orders/{order_id}/quality-control-status",
        json={"is_in_quality_control": True},
    )
    assert quality_control_response.status_code == 200

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 3,
            "estimated_minutes": 180,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": second_worker["id"]},
            ],
        },
    )

    assert update_response.status_code == 422
    assert (
        update_response.json()["detail"]
        == "Order assignments cannot be changed after quality control stage."
    )


def test_update_order_rejects_quantity_change_after_taken_without_spent_time(
    client: TestClient,
) -> None:
    """
    Проверяем неизменяемость количества заказа в работе:
    - взять заказ без учтенного времени в работу
    - отклонить изменение количества через форму назначений
    """
    author = create_author_user(client)
    worker = create_worker_user(client, name="Валерия Иванова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0118",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 3,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    move_order_to_in_work(client, order_id)

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 4,
            "estimated_minutes": 240,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )

    assert update_response.status_code == 422
    assert update_response.json()["detail"] == (
        "Order quantity can only be changed during cutting stage."
    )


def test_update_order_quantity_during_cutting_with_active_timer(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем изменение количества во время кроя:
    - сохранить запрет до и после стадии кроя
    - запустить таймер операции кроя
    - изменить количество от имени администратора и бригадира
    """
    author = create_author_user(client, name="Автор изменения количества")
    worker = create_worker_user(client, name="Закройщик количества")
    brigadier = create_brigadier_user(client, name="Бригадир количества")
    product = create_product_with_leaf_operations(
        client,
        author["id"],
        name="Изделие с изменяемым количеством",
    )
    leaf_ids = collect_leaf_operation_ids(product)
    catalog_response = client.get("/api/operation-catalog?search=Фронт")
    assert catalog_response.status_code == 200
    catalog_entry_id = catalog_response.json()["items"][0]["id"]
    kind_response = client.patch(
        f"/api/operation-catalog/{catalog_entry_id}/kind",
        json={"operation_kind": "cutting"},
    )
    assert kind_response.status_code == 200

    assignments = [
        {
            "operation_id": operation_id,
            "worker_user_id": worker["id"] if operation_id == leaf_ids[0] else None,
        }
        for operation_id in leaf_ids
    ]
    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-CUT-QTY",
            "product_id": product["id"],
            "quantity": 3,
            "assignments": assignments,
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    created_update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 4,
            "estimated_minutes": 240,
            "assignments": assignments,
        },
    )
    assert created_update_response.status_code == 422
    assert created_update_response.json()["detail"] == (
        "Order quantity can only be changed during cutting stage."
    )

    cutting_response = client.patch(
        f"/api/orders/{order_id}/production-stage",
        json={"production_stage": "cutting"},
    )
    assert cutting_response.status_code == 200
    assert cutting_response.json()["quantity_change_allowed"] is True

    timer_session_id: int
    session = db_session()
    try:
        shift = WorkShift(
            user_id=worker["id"],
            started_at=1_000,
            ended_at=None,
            business_date="2026-10-28",
            created_at=1_000,
        )
        session.add(shift)
        session.flush()
        timer_session = TimerSession(
            shift_id=shift.id,
            user_id=worker["id"],
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            order_id=order_id,
            operation_id=leaf_ids[0],
            started_at=1_000,
            ended_at=None,
            created_at=1_000,
        )
        session.add(timer_session)
        session.flush()
        timer_session_id = timer_session.id
        session.commit()
    finally:
        session.close()

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 4,
            "estimated_minutes": 240,
            "assignments": assignments,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["quantity"] == 4

    setup_response = client.post(
        "/api/auth/setup-password",
        json={
            "phone": brigadier["phone"],
            "new_password": "password123",
        },
    )
    assert setup_response.status_code == 200

    brigadier_update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 5,
            "estimated_minutes": 300,
            "assignments": assignments,
        },
    )
    assert brigadier_update_response.status_code == 200
    assert brigadier_update_response.json()["quantity"] == 5

    session = db_session()
    try:
        stored_timer_session = session.scalars(
            select(TimerSession).where(TimerSession.id == timer_session_id)
        ).one()
        stored_timer_session.ended_at = 2_000
        session.commit()
    finally:
        session.close()

    in_work_response = client.patch(
        f"/api/orders/{order_id}/production-stage",
        json={"production_stage": "in_work"},
    )
    assert in_work_response.status_code == 200

    forbidden_update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 6,
            "estimated_minutes": 360,
            "assignments": assignments,
        },
    )
    assert forbidden_update_response.status_code == 422
    assert forbidden_update_response.json()["detail"] == (
        "Order quantity can only be changed during cutting stage."
    )


@pytest.mark.parametrize("worker_state", ["inactive", "deleted"])
def test_update_order_quantity_preserves_existing_unavailable_worker(
    client: TestClient,
    worker_state: str,
) -> None:
    """
    Проверяем изменение количества с недоступным назначенным исполнителем:
    - деактивировать или удалить исполнителя после создания заказа
    - сохранить количество без изменения существующего назначения
    - отклонить новое назначение того же пользователя на другую операцию
    """
    author = create_author_user(
        client,
        name=f"Автор назначения {worker_state}",
    )
    worker = create_worker_user(
        client,
        name=f"Исполнитель назначения {worker_state}",
    )
    product = create_product_with_leaf_operations(
        client,
        author["id"],
        name=f"Изделие назначения {worker_state}",
    )
    leaf_ids = collect_leaf_operation_ids(product)
    assignments = [
        {
            "operation_id": operation_id,
            "worker_user_id": worker["id"] if operation_id == leaf_ids[0] else None,
        }
        for operation_id in leaf_ids
    ]
    create_response = client.post(
        "/api/orders",
        json={
            "order_number": f"FC-QTY-{worker_state.upper()}",
            "product_id": product["id"],
            "quantity": 3,
            "assignments": assignments,
        },
    )
    if create_response.status_code != 201:
        pytest.fail(f"Не удалось создать заказ: {create_response.text}")
    order_id = create_response.json()["id"]
    cutting_response = client.patch(
        f"/api/orders/{order_id}/production-stage",
        json={"production_stage": "cutting"},
    )
    if cutting_response.status_code != 200:
        pytest.fail(f"Не удалось перевести заказ в крой: {cutting_response.text}")

    if worker_state == "inactive":
        state_response = client.patch(
            f"/api/users/{worker['id']}/status",
            json={"is_active": False},
        )
        expected_state_status = 200
    else:
        state_response = client.delete(f"/api/users/{worker['id']}")
        expected_state_status = 204
    if state_response.status_code != expected_state_status:
        pytest.fail(f"Не удалось изменить состояние исполнителя: {state_response.text}")

    quantity_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 4,
            "estimated_minutes": 240,
            "assignments": assignments,
        },
    )
    if quantity_response.status_code != 200:
        pytest.fail(f"Не удалось изменить количество: {quantity_response.text}")
    updated_order = quantity_response.json()
    if updated_order["quantity"] != 4:
        pytest.fail("Backend не сохранил новое количество изделий")
    if not any(
        assignment["operation_id"] == leaf_ids[0]
        and assignment["worker_user_id"] == worker["id"]
        for assignment in updated_order["assignments"]
    ):
        pytest.fail("Существующее назначение недоступного исполнителя было удалено")

    new_assignment_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 4,
            "estimated_minutes": 240,
            "assignments": [
                *assignments[:2],
                {
                    "operation_id": leaf_ids[2],
                    "worker_user_id": worker["id"],
                },
            ],
        },
    )
    if new_assignment_response.status_code != 422:
        pytest.fail("Backend разрешил новое назначение недоступного исполнителя")


def test_update_order_rejects_quantity_change_after_sewing_and_return_to_cutting(
    client: TestClient,
    db_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Проверяем запрет изменения количества после начала пошива:
    - учесть завершенную обычную операцию на стадии пошива
    - вернуть заказ в крой
    - отклонить изменение количества
    """
    author = create_author_user(client, name="Автор запрета после пошива")
    worker = create_worker_user(client, name="Швея запрета количества")
    product = create_product_with_leaf_operations(
        client,
        author["id"],
        name="Изделие после начала пошива",
    )
    leaf_ids = collect_leaf_operation_ids(product)
    assignments = [
        {
            "operation_id": operation_id,
            "worker_user_id": worker["id"] if operation_id == leaf_ids[0] else None,
        }
        for operation_id in leaf_ids
    ]
    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-SEWING-QTY",
            "product_id": product["id"],
            "quantity": 3,
            "assignments": assignments,
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]
    move_order_to_in_work(client, order_id)

    session = db_session()
    try:
        timer_service = TimerService(session)
        timestamps = iter(
            [
                1_000,
                1_000,
                2_000,
                2_000,
                62_000,
                62_000,
                62_000,
            ]
        )
        monkeypatch.setattr(timer_service, "_now_ts", lambda: next(timestamps))
        timer_service.start_day(worker["id"])
        timer_service.switch_timer(
            worker["id"],
            TimerSwitchPayload(
                timer_type=TimerType.OPERATION,
                order_id=order_id,
                operation_id=leaf_ids[0],
            ),
        )
        timer_service.switch_timer(
            worker["id"],
            TimerSwitchPayload(timer_type=TimerType.BREAK),
        )
    finally:
        session.close()

    return_to_cutting_response = client.patch(
        f"/api/orders/{order_id}/production-stage",
        json={"production_stage": "cutting"},
    )
    assert return_to_cutting_response.status_code == 200
    assert return_to_cutting_response.json()["quantity_change_allowed"] is False

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 4,
            "estimated_minutes": 240,
            "assignments": assignments,
        },
    )

    assert update_response.status_code == 422
    assert update_response.json()["detail"] == (
        "Order quantity cannot be changed after sewing has started."
    )


def test_update_order_rejects_changes_after_spent_time(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем блокировку атрибутов после учета времени:
    - записать завершенную рабочую сессию заказа
    - отклонить изменение материала и назначений при прежнем количестве
    """
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="Анна Лапина")
    second_worker = create_worker_user(client, name="Татьяна Рыбакова")
    product = create_product_with_leaf_operations(client, author["id"])
    leather_type = create_leather_type(client, name="Велюр")
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0116",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 3,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": first_worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    session = db_session()
    try:
        shift = WorkShift(
            user_id=first_worker["id"],
            started_at=1_000,
            ended_at=2_000,
            business_date="2026-06-01",
            created_at=1_000,
        )
        session.add(shift)
        session.flush()
        session.add(
            TimerSession(
                shift_id=shift.id,
                user_id=first_worker["id"],
                timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                order_id=order_id,
                operation_id=leaf_ids[0],
                started_at=1_000,
                ended_at=2_000,
                created_at=1_000,
            )
        )
        session.commit()
    finally:
        session.close()

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "leather_type_id": leather_type["id"],
            "quantity": 3,
            "estimated_minutes": 240,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": second_worker["id"]},
            ],
        },
    )

    assert update_response.status_code == 422
    assert (
        update_response.json()["detail"]
        == "Order cannot be changed after time has been spent."
    )


def test_update_order_rejects_completed_order_assignments(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="Кира Матвеева")
    second_worker = create_worker_user(client, name="Оксана Баранова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0115",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 6,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": first_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": first_worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    session = db_session()
    try:
        order = session.get(WorkOrder, order_id)
        assert order is not None
        order.taken_at = 1_000
        order.quality_control_at = 2_000
        order.completed_at = 3_000
        session.commit()
    finally:
        session.close()

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "quantity": 6,
            "estimated_minutes": 360,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": second_worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": second_worker["id"]},
            ],
        },
    )

    assert update_response.status_code == 422
    assert (
        update_response.json()["detail"]
        == "Completed order assignments cannot be changed."
    )


def test_update_order_allows_existing_inactive_leather_type(client: TestClient) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client, name="Вера Павлова")
    product = create_product_with_leaf_operations(client, author["id"])
    leather_type = create_leather_type(client, name="Шевро")
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0109",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "leather_type_id": leather_type["id"],
            "quantity": 2,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/leather-types/{leather_type['id']}/status",
        json={"is_active": False},
    )
    assert patch_response.status_code == 200

    update_response = client.put(
        f"/api/orders/{order_id}/assignments",
        json={
            "leather_type_id": leather_type["id"],
            "quantity": 2,
            "estimated_minutes": 120,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["quantity"] == 2
    assert payload["leather_type_id"] == leather_type["id"]


def test_update_order_status_marks_completed_and_returns_to_work(
    client: TestClient,
) -> None:
    """
    Проверяем допустимые переходы вокруг стадии ОТК:
    - запретить прямое завершение заказа
    - передать заказ в ОТК и вернуть в работу
    """
    author = create_author_user(client)
    worker = create_worker_user(client, name="Светлана Морозова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0107",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 4,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    created_completion_response = client.patch(
        f"/api/orders/{order_id}/status",
        json={"is_completed": True},
    )
    assert created_completion_response.status_code == 422
    assert (
        created_completion_response.json()["detail"]
        == "Use quality control acceptance to complete order."
    )

    taken_payload = move_order_to_in_work(client, order_id)
    assert taken_payload["taken_at"] is None
    assert taken_payload["completed_at"] is None

    completed_response = client.patch(
        f"/api/orders/{order_id}/status",
        json={"is_completed": True},
    )
    assert completed_response.status_code == 422
    assert (
        completed_response.json()["detail"]
        == "Use quality control acceptance to complete order."
    )

    quality_control_response = client.patch(
        f"/api/orders/{order_id}/quality-control-status",
        json={"is_in_quality_control": True},
    )
    assert quality_control_response.status_code == 200
    assert quality_control_response.json()["quality_control_at"] is not None
    assert quality_control_response.json()["completed_at"] is None

    returned_response = client.patch(
        f"/api/orders/{order_id}/quality-control-status",
        json={"is_in_quality_control": False},
    )
    assert returned_response.status_code == 200
    assert returned_response.json()["completed_at"] is None
    assert returned_response.json()["quality_control_at"] is None
    assert returned_response.json()["taken_at"] == taken_payload["taken_at"]


def test_quality_control_lifecycle_and_permissions(client: TestClient) -> None:
    """
    Проверяем жизненный цикл и права ОТК:
    - передать заказ в ОТК
    - разрешить приемку только пользователю с нужной ролью
    """
    author = create_author_user(client)
    worker = create_worker_user(client, name="Екатерина Селезнева")
    quality_control_user = create_quality_control_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0114",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 4,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    move_order_to_in_work(client, order_id)

    quality_control_response = client.patch(
        f"/api/orders/{order_id}/quality-control-status",
        json={"is_in_quality_control": True},
    )
    assert quality_control_response.status_code == 200
    quality_control_payload = quality_control_response.json()
    assert quality_control_payload["quality_control_at"] is not None
    assert quality_control_payload["completed_at"] is None
    assert quality_control_payload["defect_quantity"] == 0

    in_work_response = client.get("/api/orders?status=in_work&search=0114")
    assert in_work_response.status_code == 200
    assert in_work_response.json()["total"] == 0

    quality_control_list_response = client.get(
        "/api/orders?status=quality_control&search=0114"
    )
    assert quality_control_list_response.status_code == 200
    assert quality_control_list_response.json()["total"] == 1

    forbidden_accept_response = client.patch(
        f"/api/orders/{order_id}/quality-control-acceptance",
        json={"defect_quantity": 1},
    )
    assert forbidden_accept_response.status_code == 403

    setup_response = client.post(
        "/api/auth/setup-password",
        json={
            "phone": quality_control_user["phone"],
            "new_password": "password123",
        },
    )
    assert setup_response.status_code == 200

    invalid_accept_response = client.patch(
        f"/api/orders/{order_id}/quality-control-acceptance",
        json={"defect_quantity": 5},
    )
    assert invalid_accept_response.status_code == 422
    assert (
        invalid_accept_response.json()["detail"]
        == "Defect quantity cannot exceed order quantity."
    )

    accept_response = client.patch(
        f"/api/orders/{order_id}/quality-control-acceptance",
        json={"defect_quantity": 1},
    )
    assert accept_response.status_code == 200
    accepted_payload = accept_response.json()
    assert accepted_payload["completed_at"] is not None
    assert (
        accepted_payload["quality_control_at"]
        == quality_control_payload["quality_control_at"]
    )
    assert accepted_payload["defect_quantity"] == 1

    completed_response = client.get("/api/orders?status=completed&search=0114")
    assert completed_response.status_code == 200
    assert completed_response.json()["total"] == 1

    returned_response = client.patch(
        f"/api/orders/{order_id}/status",
        json={"is_completed": False},
    )
    assert returned_response.status_code == 200
    assert returned_response.json()["completed_at"] is None
    assert (
        returned_response.json()["quality_control_at"]
        == quality_control_payload["quality_control_at"]
    )

    return_to_work_response = client.patch(
        f"/api/orders/{order_id}/quality-control-status",
        json={"is_in_quality_control": False},
    )
    assert return_to_work_response.status_code == 200
    assert return_to_work_response.json()["quality_control_at"] is None
    assert return_to_work_response.json()["defect_quantity"] == 0


def test_quality_control_acceptance_uses_current_user_roles(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем актуальность роли при приемке ОТК:
    - удалить роль у текущего пользователя после входа
    - отклонить приемку заказа без действующего права
    """
    author = create_author_user(client)
    worker = create_worker_user(client, name="Наталья Федорова")
    quality_control_user = create_quality_control_user(client, name="ОТК Без Роли")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0115",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 4,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    move_order_to_in_work(client, order_id)

    quality_control_response = client.patch(
        f"/api/orders/{order_id}/quality-control-status",
        json={"is_in_quality_control": True},
    )
    assert quality_control_response.status_code == 200

    setup_response = client.post(
        "/api/auth/setup-password",
        json={
            "phone": quality_control_user["phone"],
            "new_password": "password123",
        },
    )
    assert setup_response.status_code == 200
    assert "quality_control" in setup_response.json()["user_roles"]

    session = db_session()
    try:
        user = session.get(User, quality_control_user["id"])
        assert user is not None
        user.roles = ["worker"]
        session.commit()
    finally:
        session.close()

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["user_roles"] == ["worker"]

    accept_response = client.patch(
        f"/api/orders/{order_id}/quality-control-acceptance",
        json={"defect_quantity": 1},
    )
    assert accept_response.status_code == 403


def test_order_lifecycle_filters_and_soft_delete(client: TestClient) -> None:
    """
    Проверяем фильтры стадий и мягкое удаление:
    - перевести заказ из созданных в работу
    - удалить и восстановить заказ без потери производственной стадии
    """
    author = create_author_user(client)
    worker = create_worker_user(client, name="Оксана Крылова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0112",
            "planned_completion_date": "2026-09-30",
            "product_id": product["id"],
            "quantity": 6,
            "assignments": [
                {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
            ],
        },
    )
    assert create_response.status_code == 201
    order_id = create_response.json()["id"]
    assert create_response.json()["taken_at"] is None
    assert create_response.json()["deleted_at"] is None

    created_response = client.get("/api/orders?status=created&search=0112")
    assert created_response.status_code == 200
    assert created_response.json()["total"] == 1

    in_work_response = client.get("/api/orders?status=in_work&search=0112")
    assert in_work_response.status_code == 200
    assert in_work_response.json()["total"] == 0

    take_payload = move_order_to_in_work(client, order_id)
    assert take_payload["taken_at"] is None

    created_after_take_response = client.get("/api/orders?status=created&search=0112")
    assert created_after_take_response.status_code == 200
    assert created_after_take_response.json()["total"] == 0

    in_work_after_take_response = client.get("/api/orders?status=in_work&search=0112")
    assert in_work_after_take_response.status_code == 200
    assert in_work_after_take_response.json()["total"] == 1

    delete_response = client.patch(
        f"/api/orders/{order_id}/deleted-status",
        json={"is_deleted": True},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_at"] is not None

    in_work_after_delete_response = client.get("/api/orders?status=in_work&search=0112")
    assert in_work_after_delete_response.status_code == 200
    assert in_work_after_delete_response.json()["total"] == 0

    deleted_response = client.get("/api/orders?status=deleted&search=0112")
    assert deleted_response.status_code == 200
    assert deleted_response.json()["total"] == 1

    restore_response = client.patch(
        f"/api/orders/{order_id}/deleted-status",
        json={"is_deleted": False},
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["deleted_at"] is None
    assert restore_response.json()["taken_at"] == take_payload["taken_at"]

    restored_in_work_response = client.get("/api/orders?status=in_work&search=0112")
    assert restored_in_work_response.status_code == 200
    assert restored_in_work_response.json()["total"] == 1

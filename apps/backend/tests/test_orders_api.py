from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.work_order import WorkOrder
from app.models.work_shift import WorkShift
from app.schemas.timer import TimerType
from app.services.timer_service import TIMER_TYPE_TO_CODE


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


def create_product_with_leaf_operations(
    client: TestClient,
    author_user_id: int,
    name: str = "Сумка City Tote",
    version: str = "1.0",
) -> dict:
    response = client.post(
        "/api/products",
        json={
            "name": name,
            "version": version,
            "author_user_id": author_user_id,
            "operations": [
                {
                    "name": "Крой",
                    "children": [
                        {"name": "Фронт", "children": []},
                        {"name": "Спинка", "children": []},
                    ],
                },
                {"name": "Пошив", "children": []},
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


def test_create_order_and_get_it(client: TestClient) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client)
    leather_type = create_leather_type(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0101",
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
    assert created_order["product_name"] == product["name"]
    assert created_order["leather_type_id"] == leather_type["id"]
    assert created_order["leather_type_name"] == leather_type["name"]
    assert created_order["estimated_minutes"] == 210
    assert created_order["total_spent_minutes"] == 0
    assert created_order["taken_at"] is None
    assert created_order["quality_control_at"] is None
    assert created_order["defect_quantity"] == 0
    assert created_order["completed_at"] is None
    assert created_order["deleted_at"] is None
    assert len(created_order["assignments"]) == 3

    get_response = client.get(f"/api/orders/{created_order['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["order_number"] == "FC-0101"
    assert get_response.json()["leather_type_name"] == leather_type["name"]


def test_create_order_allows_empty_operation_workers(client: TestClient) -> None:
    author = create_author_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0110",
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
        assignment["worker_user_id"] is None
        for assignment in payload["assignments"]
    )
    assert all(
        assignment["worker_user_name"] is None
        for assignment in payload["assignments"]
    )


def test_list_orders_returns_assignments_count(client: TestClient) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0102",
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
    assert payload["total_elapsed_ms"] == 210_000
    rows = {
        (item["operation_id"], item["worker_user_id"]): item
        for item in payload["items"]
    }
    assert rows[(leaf_ids[0], first_worker["id"])]["operation_name"] == "Фронт"
    assert rows[(leaf_ids[0], first_worker["id"])]["worker_user_name"] == first_worker[
        "name"
    ]
    assert rows[(leaf_ids[0], first_worker["id"])]["elapsed_ms"] == 150_000
    assert rows[(leaf_ids[2], second_worker["id"])]["elapsed_ms"] == 60_000
    assert (leaf_ids[1], first_worker["id"]) not in rows


def test_worker_assignments_returns_current_worker_in_work_orders(
    client: TestClient,
) -> None:
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
            taken_response = client.patch(
                f"/api/orders/{order['id']}/taken-status",
                json={"is_taken": True},
            )
            assert taken_response.status_code == 200

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
            "worker_user_id": worker["id"],
            "worker_user_name": worker["name"],
        },
    ]


def test_list_orders_filters_sorts_and_paginates(client: TestClient) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client)
    quality_control_user = create_quality_control_user(client, "ОТК Сортировка")

    def create_order(order_number: str, product_name: str) -> dict:
        product = create_product_with_leaf_operations(
            client,
            author["id"],
            name=product_name,
        )
        leaf_ids = collect_leaf_operation_ids(product)

        response = client.post(
            "/api/orders",
            json={
                "order_number": order_number,
                "product_id": product["id"],
                "quantity": 1,
                "assignments": [
                    {"operation_id": leaf_ids[0], "worker_user_id": worker["id"]},
                    {"operation_id": leaf_ids[1], "worker_user_id": worker["id"]},
                    {"operation_id": leaf_ids[2], "worker_user_id": worker["id"]},
                ],
            },
        )
        assert response.status_code == 201
        return response.json()

    create_order("FC-0302", "Beta Pack")
    create_order("FC-0301", "Alpha Bag")
    create_order("FC-0304", "Сумка Марс")
    completed_order = create_order("FC-0303", "Gamma Case")
    taken_response = client.patch(
        f"/api/orders/{completed_order['id']}/taken-status",
        json={"is_taken": True},
    )
    assert taken_response.status_code == 200
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
        "/api/orders?status=created&sort_by=name&sort_direction=asc"
        "&page=1&page_size=1"
    )
    assert first_page_response.status_code == 200
    first_page = first_page_response.json()
    assert first_page["total"] == 3
    assert first_page["pages"] == 3
    assert len(first_page["items"]) == 1
    assert first_page["items"][0]["order_number"] == "FC-0301"

    second_page_response = client.get(
        "/api/orders?status=created&sort_by=name&sort_direction=asc"
        "&page=2&page_size=1"
    )
    assert second_page_response.status_code == 200
    second_page = second_page_response.json()
    assert second_page["items"][0]["order_number"] == "FC-0302"

    search_response = client.get("/api/orders?status=created&search=fc-0302")
    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["total"] == 1
    assert search_payload["items"][0]["product_name"] == "Beta Pack"

    cyrillic_search_response = client.get(
        "/api/orders?status=created&search=сУм"
    )
    assert cyrillic_search_response.status_code == 200
    cyrillic_search_payload = cyrillic_search_response.json()
    assert cyrillic_search_payload["total"] == 1
    assert cyrillic_search_payload["items"][0]["order_number"] == "FC-0304"

    hidden_completed_response = client.get(
        "/api/orders?status=created&search=0303"
    )
    assert hidden_completed_response.status_code == 200
    assert hidden_completed_response.json()["total"] == 0

    visible_completed_response = client.get(
        "/api/orders?status=completed&search=0303&sort_by=completed"
        "&sort_direction=desc"
    )
    assert visible_completed_response.status_code == 200
    visible_completed_payload = visible_completed_response.json()
    assert visible_completed_payload["total"] == 1
    assert visible_completed_payload["items"][0]["order_number"] == "FC-0303"
    assert visible_completed_payload["items"][0]["completed_at"] is not None


def test_create_order_rejects_duplicate_number(client: TestClient) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)
    payload = {
        "order_number": "FC-0103",
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
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="Наталья Лебедева")
    second_worker = create_worker_user(client, name="Елена Громова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0106",
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
    assert payload["total_spent_minutes"] == 0
    assert all(
        assignment["worker_user_name"] == second_worker["name"]
        for assignment in payload["assignments"]
    )


def test_update_order_allows_empty_operation_workers(client: TestClient) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client, name="Алла Орлова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0111",
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
    assert payload["total_spent_minutes"] == 0
    assert all(
        assignment["worker_user_id"] is None
        for assignment in payload["assignments"]
    )
    assert all(
        assignment["worker_user_name"] is None
        for assignment in payload["assignments"]
    )


def test_update_order_allows_quantity_change_without_spent_time(
    client: TestClient,
) -> None:
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="Полина Кузнецова")
    second_worker = create_worker_user(client, name="Мария Тихонова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0113",
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

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["quantity"] == 8
    assert payload["estimated_minutes"] == 480


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
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="Олеся Сафонова")
    second_worker = create_worker_user(client, name="Евгения Третьякова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0117",
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

    taken_response = client.patch(
        f"/api/orders/{order_id}/taken-status",
        json={"is_taken": True},
    )
    assert taken_response.status_code == 200
    assert taken_response.json()["has_spent_time"] is False

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
    author = create_author_user(client)
    first_worker = create_worker_user(client, name="София Беляева")
    second_worker = create_worker_user(client, name="Алина Крылова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0119",
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

    taken_response = client.patch(
        f"/api/orders/{order_id}/taken-status",
        json={"is_taken": True},
    )
    assert taken_response.status_code == 200

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


def test_update_order_allows_quantity_change_after_taken_without_spent_time(
    client: TestClient,
) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client, name="Валерия Иванова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0118",
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

    taken_response = client.patch(
        f"/api/orders/{order_id}/taken-status",
        json={"is_taken": True},
    )
    assert taken_response.status_code == 200

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

    assert update_response.status_code == 200
    assert update_response.json()["quantity"] == 4


def test_update_order_rejects_changes_after_spent_time(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
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
            "quantity": 4,
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
    author = create_author_user(client)
    worker = create_worker_user(client, name="Светлана Морозова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0107",
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

    taken_response = client.patch(
        f"/api/orders/{order_id}/taken-status",
        json={"is_taken": True},
    )
    assert taken_response.status_code == 200
    assert taken_response.json()["taken_at"] is not None
    assert taken_response.json()["completed_at"] is None

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
    assert returned_response.json()["taken_at"] == taken_response.json()["taken_at"]


def test_quality_control_lifecycle_and_permissions(client: TestClient) -> None:
    author = create_author_user(client)
    worker = create_worker_user(client, name="Екатерина Селезнева")
    quality_control_user = create_quality_control_user(client)
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0114",
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

    taken_response = client.patch(
        f"/api/orders/{order_id}/taken-status",
        json={"is_taken": True},
    )
    assert taken_response.status_code == 200

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
    author = create_author_user(client)
    worker = create_worker_user(client, name="Наталья Федорова")
    quality_control_user = create_quality_control_user(client, name="ОТК Без Роли")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0115",
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

    taken_response = client.patch(
        f"/api/orders/{order_id}/taken-status",
        json={"is_taken": True},
    )
    assert taken_response.status_code == 200

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
    author = create_author_user(client)
    worker = create_worker_user(client, name="Оксана Крылова")
    product = create_product_with_leaf_operations(client, author["id"])
    leaf_ids = collect_leaf_operation_ids(product)

    create_response = client.post(
        "/api/orders",
        json={
            "order_number": "FC-0112",
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

    take_response = client.patch(
        f"/api/orders/{order_id}/taken-status",
        json={"is_taken": True},
    )
    assert take_response.status_code == 200
    assert take_response.json()["taken_at"] is not None

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

    in_work_after_delete_response = client.get(
        "/api/orders?status=in_work&search=0112"
    )
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
    assert restore_response.json()["taken_at"] == take_response.json()["taken_at"]

    restored_in_work_response = client.get("/api/orders?status=in_work&search=0112")
    assert restored_in_work_response.status_code == 200
    assert restored_in_work_response.json()["total"] == 1

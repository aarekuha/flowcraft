from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZipFile

# ruff: noqa: I001

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.work_order import WorkOrder
from app.models.work_shift import WorkShift
from app.models.leather_type import LeatherType
from app.models.work_order import WorkOrderAssignment
from app.schemas.timer import TimerType
from app.services.timer_service import TIMER_TYPE_TO_CODE


def _timestamp(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour, tzinfo=UTC).timestamp() * 1000)


def _create_product(session: Session, name: str = "Сумка City") -> Product:
    admin = session.query(User).filter(User.phone == "+79990000001").one()
    product = Product(
        name=name,
        version="1.0",
        author=admin.name,
        author_user_id=admin.id,
        is_active=True,
        created_at=1,
    )
    session.add(product)
    session.flush()
    return product


def _grant_reports_permission(db_session: sessionmaker[Session]) -> None:
    session = db_session()
    try:
        admin = session.query(User).filter(User.phone == "+79990000001").one()
        admin.roles = [*admin.roles, "reports"]
        session.commit()
    finally:
        session.close()


def test_report_filter_options_include_inactive_and_deleted_entries(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    denied_response = client.get("/api/reports/filter-options")
    assert denied_response.status_code == 403

    _grant_reports_permission(db_session)
    session = db_session()
    try:
        admin = session.query(User).filter(User.phone == "+79990000001").one()
        deleted_worker = User(
            name="Архивный мастер",
            phone="+79990000010",
            password_hash=None,
            roles=["brigadier"],
            is_active=False,
            created_at=1,
            updated_at=2,
            deleted_at=2,
            author_user_id=admin.id,
        )
        inactive_operation = OperationCatalogEntry(
            name="Архивная операция",
            is_active=False,
            created_at=1,
            updated_at=2,
        )
        session.add_all([deleted_worker, inactive_operation])
        session.flush()
        product = _create_product(session, "Архивное изделие")
        operation = Operation(
            product_id=product.id,
            parent_id=None,
            operation_catalog_entry_id=inactive_operation.id,
            name=inactive_operation.name,
        )
        order = WorkOrder(
            order_number="FC-ARCHIVE",
            product_id=product.id,
            quantity=1,
            created_at=1,
            updated_at=1,
        )
        session.add_all([operation, order])
        session.flush()
        session.add(
            WorkOrderAssignment(
                work_order_id=order.id,
                operation_id=operation.id,
                worker_user_id=deleted_worker.id,
            )
        )
        deleted_worker_id = deleted_worker.id
        inactive_operation_id = inactive_operation.id
        session.commit()
    finally:
        session.close()

    response = client.get("/api/reports/filter-options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workers"] == [
        {
            "id": deleted_worker_id,
            "name": "Архивный мастер",
            "is_active": False,
            "is_deleted": True,
        }
    ]
    assert payload["operations"] == [
        {
            "id": inactive_operation_id,
            "name": "Архивная операция",
            "is_active": False,
        }
    ]


def test_product_quantity_report_uses_only_completed_orders(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    denied_response = client.get(
        "/api/reports/products?date_from=2026-06-01&date_to=2026-07-31"
    )
    assert denied_response.status_code == 403

    _grant_reports_permission(db_session)
    session = db_session()
    try:
        product = _create_product(session)
        session.add_all(
            [
                WorkOrder(
                    order_number="FC-1001",
                    product_id=product.id,
                    quantity=4,
                    created_at=1,
                    updated_at=1,
                    completed_at=_timestamp(2026, 6, 2),
                ),
                WorkOrder(
                    order_number="FC-1002",
                    product_id=product.id,
                    quantity=6,
                    created_at=1,
                    updated_at=1,
                    completed_at=_timestamp(2026, 7, 3),
                ),
                WorkOrder(
                    order_number="FC-1003",
                    product_id=product.id,
                    quantity=20,
                    created_at=1,
                    updated_at=1,
                ),
                WorkOrder(
                    order_number="FC-1004",
                    product_id=product.id,
                    quantity=30,
                    created_at=1,
                    updated_at=1,
                    completed_at=_timestamp(2026, 6, 4),
                    deleted_at=_timestamp(2026, 6, 5),
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = client.get(
        "/api/reports/products?date_from=2026-06-01&date_to=2026-07-31"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["months"] == ["2026-06", "2026-07"]
    assert payload["items"][0]["month_quantities"] == [4, 6]
    assert payload["items"][0]["total_quantity"] == 10
    assert payload["total_quantity"] == 10

    export_response = client.get(
        "/api/reports/products/export.xlsx?date_from=2026-06-01&date_to=2026-07-31"
    )
    assert export_response.status_code == 200
    with ZipFile(BytesIO(export_response.content)) as workbook:
        assert "xl/worksheets/sheet1.xml" in workbook.namelist()
        assert "xl/worksheets/sheet2.xml" in workbook.namelist()


def test_product_time_report_calculates_weighted_average_per_item(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    _grant_reports_permission(db_session)
    session = db_session()
    try:
        product = _create_product(session)
        catalog_entry = OperationCatalogEntry(
            name="Пошив",
            is_active=True,
            created_at=1,
            updated_at=1,
        )
        worker = User(
            name="Ирина Соколова",
            phone="+79990000002",
            password_hash=None,
            roles=["worker"],
            is_active=True,
            created_at=1,
            updated_at=1,
            deleted_at=None,
            author_user_id=product.author_user_id,
        )
        session.add_all([catalog_entry, worker])
        session.flush()
        operation = Operation(
            product_id=product.id,
            parent_id=None,
            operation_catalog_entry_id=catalog_entry.id,
            name="Пошив",
        )
        first_order = WorkOrder(
            order_number="FC-2001",
            product_id=product.id,
            quantity=2,
            created_at=1,
            updated_at=1,
        )
        second_order = WorkOrder(
            order_number="FC-2002",
            product_id=product.id,
            quantity=3,
            created_at=1,
            updated_at=1,
        )
        session.add_all([operation, first_order, second_order])
        session.flush()
        first_shift = WorkShift(
            user_id=worker.id,
            started_at=1,
            ended_at=700_000,
            business_date="2026-06-01",
            created_at=1,
        )
        second_shift = WorkShift(
            user_id=worker.id,
            started_at=1,
            ended_at=200_000,
            business_date="2026-06-02",
            created_at=1,
        )
        session.add_all([first_shift, second_shift])
        session.flush()
        session.add_all(
            [
                TimerSession(
                    shift_id=first_shift.id,
                    user_id=worker.id,
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=first_order.id,
                    operation_id=operation.id,
                    started_at=0,
                    ended_at=200_000,
                    created_at=0,
                ),
                TimerSession(
                    shift_id=first_shift.id,
                    user_id=worker.id,
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=second_order.id,
                    operation_id=operation.id,
                    started_at=300_000,
                    ended_at=600_000,
                    created_at=300_000,
                ),
                TimerSession(
                    shift_id=second_shift.id,
                    user_id=worker.id,
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=first_order.id,
                    operation_id=operation.id,
                    started_at=0,
                    ended_at=120_000,
                    created_at=0,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = client.get(
        "/api/reports/product-time?date_from=2026-06-01&date_to=2026-06-02"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == ["2026-06-01", "2026-06-02"]
    product = payload["products"][0]
    assert product["daily_average_ms"] == [100_000, 60_000]
    assert product["average_ms"] == 124_000
    assert product["total_elapsed_ms"] == 620_000
    assert product["rows"][0]["daily_average_ms"] == [100_000, 60_000]
    assert product["rows"][0]["share_of_product_time"] == 1

    export_response = client.get(
        "/api/reports/product-time/export.xlsx?date_from=2026-06-01&date_to=2026-06-02"
    )
    assert export_response.status_code == 200
    with ZipFile(BytesIO(export_response.content)) as workbook:
        styles = workbook.read("xl/styles.xml").decode()
        assert 'formatCode="[h]:mm:ss"' in styles


def test_order_batch_report_groups_timers_and_keeps_zero_time_assignments(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    _grant_reports_permission(db_session)
    session = db_session()
    try:
        product = _create_product(session, "Рюкзак Nord")
        leather_type = LeatherType(
            name="Черная кожа",
            is_active=True,
            created_at=1,
            updated_at=1,
        )
        sewing_entry = OperationCatalogEntry(
            name="Пошив",
            is_active=True,
            created_at=1,
            updated_at=1,
        )
        packing_entry = OperationCatalogEntry(
            name="Упаковка",
            is_active=True,
            created_at=1,
            updated_at=1,
        )
        worker = User(
            name="Анна Мастер",
            phone="+79990000003",
            password_hash=None,
            roles=["worker"],
            is_active=True,
            created_at=1,
            updated_at=1,
            deleted_at=None,
            author_user_id=product.author_user_id,
        )
        session.add_all([leather_type, sewing_entry, packing_entry, worker])
        session.flush()
        sewing = Operation(
            product_id=product.id,
            parent_id=None,
            operation_catalog_entry_id=sewing_entry.id,
            name="Пошив",
            sort_order=1,
        )
        packing = Operation(
            product_id=product.id,
            parent_id=None,
            operation_catalog_entry_id=packing_entry.id,
            name="Упаковка",
            sort_order=2,
        )
        session.add_all([sewing, packing])
        session.flush()
        worker_id = worker.id
        packing_entry_id = packing_entry.id
        order = WorkOrder(
            order_number="9383",
            product_id=product.id,
            leather_type_id=leather_type.id,
            quantity=3,
            defect_quantity=1,
            created_at=1,
            updated_at=1,
            completed_at=_timestamp(2026, 8, 10),
        )
        session.add(order)
        session.flush()
        session.add_all(
            [
                WorkOrderAssignment(
                    work_order_id=order.id,
                    operation_id=sewing.id,
                    worker_user_id=worker.id,
                ),
                WorkOrderAssignment(
                    work_order_id=order.id,
                    operation_id=packing.id,
                    worker_user_id=worker.id,
                ),
            ]
        )
        shift = WorkShift(
            user_id=worker.id,
            started_at=1,
            ended_at=400_000,
            business_date="2026-08-09",
            created_at=1,
        )
        session.add(shift)
        session.flush()
        session.add_all(
            [
                TimerSession(
                    shift_id=shift.id,
                    user_id=worker.id,
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=order.id,
                    operation_id=sewing.id,
                    started_at=0,
                    ended_at=120_000,
                    created_at=0,
                ),
                TimerSession(
                    shift_id=shift.id,
                    user_id=worker.id,
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=order.id,
                    operation_id=sewing.id,
                    started_at=150_000,
                    ended_at=330_000,
                    created_at=150_000,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = client.get(
        "/api/reports/order-batches?date_from=2026-08-01&date_to=2026-08-31"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["pages"] == 1
    item = payload["items"][0]
    assert item["order_number"] == "9383"
    assert item["product_name"] == "Рюкзак Nord"
    assert item["leather_type_name"] == "Черная кожа"
    assert item["quantity"] == 3
    assert item["submitted_quantity"] == 2
    assert item["total_elapsed_ms"] == 300_000
    assert item["average_ms"] == 150_000
    assert [
        (detail["operation_name"], detail["elapsed_ms"], detail["average_ms"])
        for detail in item["details"]
    ] == [
        ("Пошив", 300_000, 150_000),
        ("Упаковка", 0, 0),
    ]

    filtered_response = client.get(
        "/api/reports/order-batches"
        "?date_from=2026-08-01&date_to=2026-08-31"
        f"&worker_user_id={worker_id}"
        f"&operation_catalog_entry_id={packing_entry_id}"
    )
    assert filtered_response.status_code == 200
    filtered_item = filtered_response.json()["items"][0]
    assert filtered_item["total_elapsed_ms"] == 0
    assert [detail["operation_name"] for detail in filtered_item["details"]] == [
        "Упаковка"
    ]

    export_response = client.get(
        "/api/reports/order-batches/export.xlsx?date_from=2026-08-01&date_to=2026-08-31"
    )
    assert export_response.status_code == 200
    with ZipFile(BytesIO(export_response.content)) as workbook:
        styles = workbook.read("xl/styles.xml").decode()
        sheet = workbook.read("xl/worksheets/sheet1.xml").decode()
        assert 'formatCode="[h]:mm:ss"' in styles
        assert 's="4"' in sheet

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_authenticated_session, get_session
from app.api.routes.orders import router
from app.core.database import Base
from app.models.operation import Operation
from app.models.product import Product
from app.models.work_order import WorkOrder, WorkOrderAssignment


@pytest.fixture()
def order_api() -> Iterator[tuple[TestClient, Session, FastAPI]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Product(id=1, name="Изделие", version="1", author="Admin", created_at=1)
        )
        session.flush()
        session.add(Operation(id=1, product_id=1, name="Покраска"))
        session.add(
            WorkOrder(
                id=1,
                order_number="100",
                product_id=1,
                quantity=10,
                production_stage="in_work",
                sewing_started_at=5,
                created_at=1,
                updated_at=1,
            )
        )
        session.flush()
        session.add(
            WorkOrderAssignment(work_order_id=1, operation_id=1, worker_user_id=None)
        )
        session.commit()
        app = FastAPI()
        app.include_router(router, prefix="/orders")
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[get_authenticated_session] = lambda: SimpleNamespace(
            user_roles=["admin"]
        )
        with TestClient(app) as client:
            yield client, session, app
    engine.dispose()


@pytest.mark.parametrize("role", ["admin", "brigadier", "quality_control"])
def test_completed_order_cannot_be_reopened(
    order_api: tuple[TestClient, Session, FastAPI],
    role: str,
) -> None:
    """
    Проверяем запрет снятия завершения для всех ролей:
    - выполнить заказ с сохранёнными датами и браком
    - отклонить прямой возврат в ОТК и обход через возврат в работу
    - сохранить дату выполнения, дату ОТК и количество брака
    """
    client, session, app = order_api
    app.dependency_overrides[get_authenticated_session] = lambda: SimpleNamespace(
        user_roles=[role]
    )
    order = session.get(WorkOrder, 1)
    assert order is not None
    order.completed_at, order.quality_control_at, order.defect_quantity = 30, 20, 2
    session.commit()
    for path, payload in [
        ("status", {"is_completed": False}),
        ("quality-control-status", {"is_in_quality_control": False}),
        ("quality-control-status", {"is_in_quality_control": True}),
    ]:
        assert client.patch(f"/orders/1/{path}", json=payload).status_code == 422
    result = client.get("/orders/1").json()
    assert (
        result["completed_at"],
        result["quality_control_at"],
        result["defect_quantity"],
    ) == (30, 20, 2)


@pytest.mark.parametrize(
    "role, expected", [("admin", 200), ("brigadier", 403), ("quality_control", 403)]
)
def test_return_to_cutting_requires_admin(
    order_api: tuple[TestClient, Session, FastAPI],
    role: str,
    expected: int,
) -> None:
    """
    Проверяем разрешение обратного перехода в крой:
    - отправить одинаковый запрос от администратора и других ролей
    - изменить стадию только для администратора
    """
    client, _, app = order_api
    app.dependency_overrides[get_authenticated_session] = lambda: SimpleNamespace(
        user_roles=[role]
    )
    result = client.patch(
        "/orders/1/production-stage", json={"production_stage": "cutting"}
    )
    assert result.status_code == expected
    assert client.get("/orders/1").json()["production_stage"] == (
        "cutting" if expected == 200 else "in_work"
    )


@pytest.mark.parametrize(
    "role, stage, sewing, qc, completed, expected",
    [
        ("admin", "in_work", 5, None, None, 200),
        ("brigadier", "in_work", None, None, None, 422),
        ("brigadier", "in_work", 5, None, None, 422),
        ("brigadier", "cutting", None, None, None, 200),
        ("brigadier", "cutting", 5, None, None, 422),
        ("admin", "cutting", 5, None, None, 422),
        ("admin", "in_work", 5, 20, None, 422),
        ("admin", "in_work", 5, 20, 30, 422),
    ],
)
def test_quantity_permissions_preserve_brigadier_rules(
    order_api: tuple[TestClient, Session, FastAPI],
    role: str,
    stage: str,
    sewing: int | None,
    qc: int | None,
    completed: int | None,
    expected: int,
) -> None:
    """
    Проверяем количество в зависимости от роли и стадии:
    - администратор меняет количество в работе даже после начала пошива
    - бригадир меняет количество только в крое до начала пошива
    - изменение количества в ОТК и выполненных недоступно
    """
    client, session, app = order_api
    app.dependency_overrides[get_authenticated_session] = lambda: SimpleNamespace(
        user_roles=[role]
    )
    order = session.get(WorkOrder, 1)
    assert order is not None
    order.production_stage = stage
    order.sewing_started_at = sewing
    order.quality_control_at = qc
    order.completed_at = completed
    session.commit()
    result = client.put(
        "/orders/1/assignments",
        json={
            "quantity": 12,
            "assignments": [{"operation_id": 1, "worker_user_id": None}],
        },
    )
    assert result.status_code == expected, result.text
    assert client.get("/orders/1").json()["quantity"] == (12 if expected == 200 else 10)


def test_brigadier_can_still_transfer_created_order_to_cutting(
    order_api: tuple[TestClient, Session, FastAPI],
) -> None:
    """
    Проверяем сохранение прямого перехода в крой:
    - созданный заказ передать в крой от имени бригадира
    - ограничение обратного перехода не мешает передаче
    """
    client, session, app = order_api
    app.dependency_overrides[get_authenticated_session] = lambda: SimpleNamespace(
        user_roles=["brigadier"]
    )
    order = session.get(WorkOrder, 1)
    assert order is not None
    order.production_stage = "created"
    order.sewing_started_at = None
    session.commit()
    result = client.patch(
        "/orders/1/production-stage", json={"production_stage": "cutting"}
    )
    assert result.status_code == 200
    assert result.json()["production_stage"] == "cutting"

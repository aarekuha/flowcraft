from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.timer_session_audit import TimerSessionAuditLog
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderTimeAllocation
from app.models.work_shift import WorkShift
from app.schemas.timer import TimerType
from app.services.timer_service import TIMER_TYPE_TO_CODE


def _timestamp(day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(2026, 10, day, hour, minute, tzinfo=UTC).timestamp() * 1000)


def _seed_work_time_graph(
    db_session: sessionmaker[Session],
) -> tuple[int, int, int, int, int]:
    session = db_session()
    try:
        admin = session.scalars(select(User).where(User.phone == "+79990000001")).one()
        worker = User(
            name="Исполнитель времени",
            phone="+79990000201",
            password_hash=hash_password("password123"),
            roles=["worker"],
            is_active=True,
            created_at=1,
            updated_at=1,
            deleted_at=None,
            author_user_id=admin.id,
        )
        product = Product(
            name="Тестовое изделие",
            version="1.0",
            author=admin.name,
            author_user_id=admin.id,
            is_active=True,
            created_at=1,
        )
        regular_entry = OperationCatalogEntry(
            name="Пошив",
            operation_kind="regular",
            is_active=True,
            created_at=1,
            updated_at=1,
        )
        cutting_entry = OperationCatalogEntry(
            name="Крой",
            operation_kind="cutting",
            is_active=True,
            created_at=1,
            updated_at=1,
        )
        session.add_all([worker, product, regular_entry, cutting_entry])
        session.flush()
        regular_operation = Operation(
            product_id=product.id,
            operation_catalog_entry_id=regular_entry.id,
            name=regular_entry.name,
            sort_order=1,
        )
        cutting_operation = Operation(
            product_id=product.id,
            operation_catalog_entry_id=cutting_entry.id,
            name=cutting_entry.name,
            sort_order=2,
        )
        session.add_all([regular_operation, cutting_operation])
        session.flush()
        order = WorkOrder(
            order_number="FC-TIME-1",
            product_id=product.id,
            quantity=4,
            estimated_minutes=0,
            total_spent_seconds=0,
            cutting_spent_seconds=0,
            production_stage="in_work",
            created_at=1,
            updated_at=1,
            cutting_started_at=1,
            taken_at=1,
            defect_quantity=0,
        )
        shift = WorkShift(
            user_id=worker.id,
            started_at=_timestamp(20, 8),
            ended_at=_timestamp(20, 18),
            business_date="2026-10-20",
            created_at=_timestamp(20, 8),
        )
        session.add_all([order, shift])
        session.commit()
        return (
            worker.id,
            order.id,
            regular_operation.id,
            cutting_operation.id,
            shift.id,
        )
    finally:
        session.close()


def test_admin_creates_updates_and_deletes_operation_time(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем полный цикл ручной правки времени:
    - создать интервал обычной операции и заменить её перенесённым кроем
    - пересчитать начало кроя, логически удалить запись и сохранить аудит
    """
    worker_id, order_id, regular_id, cutting_id, _shift_id = _seed_work_time_graph(
        db_session
    )

    create_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 10),
            "ended_at": _timestamp(20, 11),
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["editable"] is True

    list_response = client.get(
        "/api/admin/work-time/sessions",
        params={
            "worker_user_id": worker_id,
            "from_ts": _timestamp(20, 8),
            "to_ts": _timestamp(20, 18),
        },
    )
    operations_response = client.get(
        f"/api/admin/work-time/orders/{order_id}/operations"
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]
    assert [item["name"] for item in operations_response.json()] == ["Крой", "Пошив"]

    session = db_session()
    try:
        order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        assert order.total_spent_seconds == 3600
        assert order.cutting_spent_seconds == 0
        assert order.taken_at == _timestamp(20, 10)
        assert order.cutting_started_at is None
        assert order.sewing_started_at == _timestamp(20, 10)
    finally:
        session.close()

    update_response = client.patch(
        f"/api/admin/work-time/sessions/{created['id']}",
        json={
            "operation_id": cutting_id,
            "started_at": _timestamp(20, 9, 30),
            "ended_at": _timestamp(20, 11, 30),
            "expected_updated_at": created["updated_at"],
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()

    session = db_session()
    try:
        order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        assert order.total_spent_seconds == 7200
        assert order.cutting_spent_seconds == 7200
        assert order.taken_at == _timestamp(20, 9, 30)
        assert order.cutting_started_at == _timestamp(20, 9, 30)
    finally:
        session.close()

    delete_response = client.delete(
        f"/api/admin/work-time/sessions/{created['id']}",
        params={"expected_updated_at": updated["updated_at"]},
    )
    assert delete_response.status_code == 204

    breakdown_response = client.get(f"/api/orders/{order_id}/time-breakdown")
    assert breakdown_response.status_code == 200
    assert breakdown_response.json()["total_elapsed_ms"] == 0

    session = db_session()
    try:
        order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        timer_session = session.scalars(
            select(TimerSession).where(TimerSession.id == created["id"])
        ).one()
        actions = session.scalars(
            select(TimerSessionAuditLog.action)
            .where(TimerSessionAuditLog.timer_session_id == created["id"])
            .order_by(TimerSessionAuditLog.id.asc())
        ).all()
        assert order.total_spent_seconds == 0
        assert order.cutting_spent_seconds == 0
        assert order.taken_at is None
        assert order.cutting_started_at is None
        assert order.sewing_started_at == _timestamp(20, 10)
        assert timer_session.deleted_at is not None
        assert actions == ["create", "update", "delete"]
    finally:
        session.close()


def test_admin_recalculates_order_start_times_after_deleting_earliest_operation(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем пересчёт начала заказа и кроя по оставшимся операциям:
    - добавить два непересекающихся интервала кроя одного заказа
    - удалить самый ранний интервал
    - установить начало следующей операции как новое время заказа и кроя
    """
    worker_id, order_id, _regular_id, cutting_id, _shift_id = _seed_work_time_graph(
        db_session
    )
    first_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": order_id,
            "operation_id": cutting_id,
            "started_at": _timestamp(20, 9),
            "ended_at": _timestamp(20, 10),
        },
    )
    second_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": order_id,
            "operation_id": cutting_id,
            "started_at": _timestamp(20, 11),
            "ended_at": _timestamp(20, 12),
        },
    )
    assert first_response.status_code == 201
    assert second_response.status_code == 201

    session = db_session()
    try:
        order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        assert order.taken_at == _timestamp(20, 9)
        assert order.cutting_started_at == _timestamp(20, 9)
    finally:
        session.close()

    first = first_response.json()
    delete_response = client.delete(
        f"/api/admin/work-time/sessions/{first['id']}",
        params={"expected_updated_at": first["updated_at"]},
    )
    assert delete_response.status_code == 204

    session = db_session()
    try:
        order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        assert order.total_spent_seconds == 3600
        assert order.taken_at == _timestamp(20, 11)
        assert order.cutting_started_at == _timestamp(20, 11)
    finally:
        session.close()


def test_admin_fully_manages_time_for_deleted_order(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем полный доступ к времени мягко удалённого заказа:
    - найти удалённый заказ и добавить завершённую операцию
    - изменить время, заменить операцию и удалить интервал
    - заменить служебный таймер операцией удалённого заказа
    """
    worker_id, order_id, regular_id, cutting_id, shift_id = _seed_work_time_graph(
        db_session
    )
    session = db_session()
    try:
        order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        order.deleted_at = _timestamp(20, 19)
        service_interval = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.BREAK],
            order_id=None,
            operation_id=None,
            started_at=_timestamp(20, 12),
            ended_at=_timestamp(20, 13),
            created_at=_timestamp(20, 12),
            updated_at=_timestamp(20, 13),
        )
        session.add(service_interval)
        session.commit()
        service_interval_id = service_interval.id
    finally:
        session.close()

    search_response = client.get(
        "/api/admin/work-time/orders/search",
        params={"query": "FC-TIME-1"},
    )
    operations_response = client.get(
        f"/api/admin/work-time/orders/{order_id}/operations"
    )
    assert search_response.status_code == 200
    assert search_response.json() == [
        {
            "id": order_id,
            "order_number": "FC-TIME-1",
            "product_name": "Тестовое изделие",
            "product_version": "1.0",
            "is_deleted": True,
        }
    ]
    assert operations_response.status_code == 200
    assert [item["name"] for item in operations_response.json()] == ["Крой", "Пошив"]

    create_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 10),
            "ended_at": _timestamp(20, 11),
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["editable"] is True

    overlaps_response = client.get(
        "/api/admin/work-time/overlaps",
        params={
            "worker_user_id": worker_id,
            "order_id": order_id,
            "started_at": _timestamp(20, 10),
            "ended_at": _timestamp(20, 11),
            "exclude_session_id": created["id"],
        },
    )
    assert overlaps_response.status_code == 200
    assert overlaps_response.json() == []

    update_response = client.patch(
        f"/api/admin/work-time/sessions/{created['id']}",
        json={
            "operation_id": cutting_id,
            "started_at": _timestamp(20, 9, 30),
            "ended_at": _timestamp(20, 11),
            "expected_updated_at": created["updated_at"],
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["operation_id"] == cutting_id
    assert updated["started_at"] == _timestamp(20, 9, 30)

    session = db_session()
    try:
        order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        assert order.taken_at == _timestamp(20, 9, 30)
    finally:
        session.close()

    delete_response = client.delete(
        f"/api/admin/work-time/sessions/{created['id']}",
        params={"expected_updated_at": updated["updated_at"]},
    )
    assert delete_response.status_code == 204

    session = db_session()
    try:
        order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        assert order.taken_at is None
    finally:
        session.close()

    sessions_response = client.get(
        "/api/admin/work-time/sessions",
        params={
            "worker_user_id": worker_id,
            "from_ts": _timestamp(20, 8),
            "to_ts": _timestamp(20, 18),
        },
    )
    assert sessions_response.status_code == 200
    service_interval_payload = next(
        item
        for item in sessions_response.json()
        if item["id"] == service_interval_id
    )

    conversion_response = client.patch(
        f"/api/admin/work-time/sessions/{service_interval_id}",
        json={
            "order_id": order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 12),
            "ended_at": _timestamp(20, 13),
            "expected_updated_at": service_interval_payload["updated_at"],
        },
    )
    assert conversion_response.status_code == 200
    assert conversion_response.json()["timer_type"] == "operation"
    assert conversion_response.json()["order_id"] == order_id

    session = db_session()
    try:
        order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        deleted_interval = session.scalars(
            select(TimerSession).where(TimerSession.id == created["id"])
        ).one()
        converted_interval = session.scalars(
            select(TimerSession).where(TimerSession.id == service_interval_id)
        ).one()
        assert order.deleted_at is not None
        assert order.total_spent_seconds == 3600
        assert order.taken_at == _timestamp(20, 12)
        assert deleted_interval.deleted_at is not None
        assert converted_interval.order_id == order_id
        assert converted_interval.operation_id == regular_id
    finally:
        session.close()


def test_admin_blocks_same_order_overlap_and_allows_other_orders(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем коллизии операций исполнителя:
    - запретить пересечение времени одного заказа
    - вернуть предупреждение и разрешить пересечение разных заказов
    - разрешить соседние интервалы без предупреждения
    """
    worker_id, order_id, regular_id, _cutting_id, shift_id = _seed_work_time_graph(
        db_session
    )
    session = db_session()
    try:
        source_order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        other_order = WorkOrder(
            order_number="FC-TIME-2",
            product_id=source_order.product_id,
            quantity=2,
            estimated_minutes=0,
            total_spent_seconds=0,
            cutting_spent_seconds=0,
            production_stage="in_work",
            created_at=1,
            updated_at=1,
            cutting_started_at=1,
            taken_at=1,
            defect_quantity=0,
        )
        existing_operation = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            order_id=order_id,
            operation_id=regular_id,
            started_at=_timestamp(20, 9),
            ended_at=_timestamp(20, 10),
            created_at=_timestamp(20, 9),
            updated_at=_timestamp(20, 10),
        )
        service_timer = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.BREAK],
            order_id=None,
            operation_id=None,
            started_at=_timestamp(20, 9),
            ended_at=_timestamp(20, 10),
            created_at=_timestamp(20, 9),
            updated_at=_timestamp(20, 10),
        )
        session.add_all(
            [
                other_order,
                existing_operation,
                service_timer,
            ]
        )
        session.commit()
        other_order_id = other_order.id
        existing_operation_id = existing_operation.id
    finally:
        session.close()

    collision_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 9, 59),
            "ended_at": _timestamp(20, 11),
        },
    )
    assert collision_response.status_code == 409
    assert collision_response.json()["detail"] == {
        "code": "same_order_time_overlap",
        "message": "В заказе уже есть пересекающийся интервал.",
        "collision": {
            "session_id": existing_operation_id,
            "label": "Пошив",
            "started_at": _timestamp(20, 9),
            "ended_at": _timestamp(20, 10),
        },
    }

    overlap_response = client.get(
        "/api/admin/work-time/overlaps",
        params={
            "worker_user_id": worker_id,
            "order_id": other_order_id,
            "started_at": _timestamp(20, 9, 30),
            "ended_at": _timestamp(20, 10, 30),
        },
    )
    assert overlap_response.status_code == 200
    assert overlap_response.json() == [
        {
            "order_id": order_id,
            "order_number": "FC-TIME-1",
        }
    ]

    other_order_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": other_order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 9, 30),
            "ended_at": _timestamp(20, 10, 30),
        },
    )
    assert other_order_response.status_code == 201

    adjacent_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 10),
            "ended_at": _timestamp(20, 11),
        },
    )
    assert adjacent_response.status_code == 201

    adjacent_overlap_response = client.get(
        "/api/admin/work-time/overlaps",
        params={
            "worker_user_id": worker_id,
            "order_id": order_id,
            "started_at": _timestamp(20, 10, 30),
            "ended_at": _timestamp(20, 11),
            "exclude_session_id": adjacent_response.json()["id"],
        },
    )
    assert adjacent_overlap_response.status_code == 200
    assert adjacent_overlap_response.json() == []


def test_admin_ignores_zero_time_allocations_in_overlap_checks(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем коллизии для нулевого распределения времени:
    - связать завершённую операцию со вторым заказом без выделенных секунд
    - вернуть через API только положительное распределение исходного заказа
    - не показывать предупреждение и разрешить пересекающуюся операцию второго заказа
    """
    worker_id, source_order_id, regular_id, _cutting_id, shift_id = (
        _seed_work_time_graph(db_session)
    )
    session = db_session()
    try:
        source_order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == source_order_id)
        ).one()
        zero_time_order = WorkOrder(
            order_number="FC-TIME-ZERO",
            product_id=source_order.product_id,
            quantity=1,
            estimated_minutes=0,
            total_spent_seconds=0,
            cutting_spent_seconds=0,
            production_stage="in_work",
            created_at=1,
            updated_at=1,
            cutting_started_at=1,
            taken_at=None,
            defect_quantity=0,
        )
        timer_session = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            order_id=source_order_id,
            operation_id=regular_id,
            started_at=_timestamp(20, 9),
            ended_at=_timestamp(20, 10),
            created_at=_timestamp(20, 9),
            updated_at=_timestamp(20, 10),
        )
        session.add_all([zero_time_order, timer_session])
        session.flush()
        session.add_all(
            [
                WorkOrderTimeAllocation(
                    timer_session_id=timer_session.id,
                    work_order_id=source_order_id,
                    allocated_seconds=3600,
                    created_at=1,
                    updated_at=1,
                ),
                WorkOrderTimeAllocation(
                    timer_session_id=timer_session.id,
                    work_order_id=zero_time_order.id,
                    allocated_seconds=0,
                    created_at=1,
                    updated_at=1,
                ),
            ]
        )
        session.commit()
        zero_time_order_id = zero_time_order.id
        timer_session_id = timer_session.id
    finally:
        session.close()

    overlap_response = client.get(
        "/api/admin/work-time/overlaps",
        params={
            "worker_user_id": worker_id,
            "order_id": source_order_id,
            "started_at": _timestamp(20, 9, 30),
            "ended_at": _timestamp(20, 9, 45),
        },
    )
    sessions_response = client.get(
        "/api/admin/work-time/sessions",
        params={
            "worker_user_id": worker_id,
            "from_ts": _timestamp(20, 8),
            "to_ts": _timestamp(20, 18),
        },
    )
    create_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": zero_time_order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 9, 30),
            "ended_at": _timestamp(20, 9, 45),
        },
    )

    assert overlap_response.status_code == 200
    assert overlap_response.json() == []
    assert sessions_response.status_code == 200
    allocated_session = next(
        item for item in sessions_response.json() if item["id"] == timer_session_id
    )
    assert allocated_session["allocations"] == [
        {
            "order_id": source_order_id,
            "order_number": "FC-TIME-1",
            "allocated_seconds": 3600,
        }
    ]
    assert allocated_session["allocated_order_numbers"] == ["FC-TIME-1"]
    assert create_response.status_code == 201


def test_admin_ignores_raw_order_when_time_is_allocated_to_another_order(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем эффективный заказ распределённой сессии:
    - оставить исходный order_id при нулевом распределении его времени
    - разрешить пересечение исходного заказа и предупредить о другом заказе
    - сохранить запрет пересечения заказа с положительным распределением
    """
    worker_id, source_order_id, regular_id, _cutting_id, shift_id = (
        _seed_work_time_graph(db_session)
    )
    session = db_session()
    try:
        source_order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == source_order_id)
        ).one()
        allocated_order = WorkOrder(
            order_number="FC-TIME-ALLOCATED",
            product_id=source_order.product_id,
            quantity=3,
            estimated_minutes=0,
            total_spent_seconds=3600,
            cutting_spent_seconds=0,
            production_stage="in_work",
            created_at=1,
            updated_at=1,
            cutting_started_at=1,
            taken_at=_timestamp(20, 11),
            defect_quantity=0,
        )
        timer_session = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            order_id=source_order_id,
            operation_id=regular_id,
            started_at=_timestamp(20, 11),
            ended_at=_timestamp(20, 12),
            created_at=_timestamp(20, 11),
            updated_at=_timestamp(20, 12),
        )
        session.add_all([allocated_order, timer_session])
        session.flush()
        session.add_all(
            [
                WorkOrderTimeAllocation(
                    timer_session_id=timer_session.id,
                    work_order_id=source_order_id,
                    allocated_seconds=0,
                    created_at=1,
                    updated_at=1,
                ),
                WorkOrderTimeAllocation(
                    timer_session_id=timer_session.id,
                    work_order_id=allocated_order.id,
                    allocated_seconds=3600,
                    created_at=1,
                    updated_at=1,
                ),
            ]
        )
        session.commit()
        allocated_order_id = allocated_order.id
        timer_session_id = timer_session.id
    finally:
        session.close()

    source_breakdown_response = client.get(
        f"/api/orders/{source_order_id}/time-breakdown"
    )
    allocated_breakdown_response = client.get(
        f"/api/orders/{allocated_order_id}/time-breakdown"
    )
    overlap_response = client.get(
        "/api/admin/work-time/overlaps",
        params={
            "worker_user_id": worker_id,
            "order_id": source_order_id,
            "started_at": _timestamp(20, 11, 15),
            "ended_at": _timestamp(20, 11, 45),
        },
    )
    source_create_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": source_order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 11, 15),
            "ended_at": _timestamp(20, 11, 45),
        },
    )
    allocated_create_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": allocated_order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 11, 15),
            "ended_at": _timestamp(20, 11, 45),
        },
    )

    assert source_breakdown_response.status_code == 200
    assert source_breakdown_response.json()["items"] == []
    assert source_breakdown_response.json()["total_elapsed_ms"] == 0
    assert allocated_breakdown_response.status_code == 200
    assert allocated_breakdown_response.json()["total_elapsed_ms"] == 3_600_000
    assert overlap_response.status_code == 200
    assert overlap_response.json() == [
        {
            "order_id": allocated_order_id,
            "order_number": "FC-TIME-ALLOCATED",
        }
    ]
    assert source_create_response.status_code == 201
    assert allocated_create_response.status_code == 409
    assert allocated_create_response.json()["detail"]["collision"]["session_id"] == (
        timer_session_id
    )


def test_admin_expands_or_creates_shift_for_manual_time(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем согласование ручного времени со сменой:
    - расширить существующую смену по началу и окончанию операции
    - создать смену при добавлении времени на новую рабочую дату
    """
    worker_id, order_id, regular_id, _cutting_id, shift_id = _seed_work_time_graph(
        db_session
    )

    expanded_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 7, 30),
            "ended_at": _timestamp(20, 18, 30),
        },
    )
    assert expanded_response.status_code == 201

    update_response = client.patch(
        f"/api/admin/work-time/sessions/{expanded_response.json()['id']}",
        json={
            "operation_id": regular_id,
            "started_at": _timestamp(20, 7),
            "ended_at": _timestamp(20, 19),
            "expected_updated_at": expanded_response.json()["updated_at"],
        },
    )
    assert update_response.status_code == 200

    created_shift_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(21, 10),
            "ended_at": _timestamp(21, 11),
        },
    )
    assert created_shift_response.status_code == 201

    session = db_session()
    try:
        expanded_shift = session.scalars(
            select(WorkShift).where(WorkShift.id == shift_id)
        ).one()
        new_shift = session.scalars(
            select(WorkShift).where(
                WorkShift.id == created_shift_response.json()["shift_id"]
            )
        ).one()
        assert expanded_shift.started_at == _timestamp(20, 7)
        assert expanded_shift.ended_at == _timestamp(20, 19)
        assert new_shift.started_at == _timestamp(21, 10)
        assert new_shift.ended_at == _timestamp(21, 11)
    finally:
        session.close()


def test_admin_updates_and_deletes_completed_idle_time(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем административную правку «Брак/Ремонт»:
    - показать завершённый интервал без заказа доступным для редактирования
    - изменить время с расширением смены и логически удалить запись
    """
    worker_id, order_id, _regular_id, _cutting_id, shift_id = _seed_work_time_graph(
        db_session
    )
    session = db_session()
    try:
        idle = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.IDLE],
            order_id=None,
            operation_id=None,
            started_at=_timestamp(20, 11),
            ended_at=_timestamp(20, 12),
            created_at=_timestamp(20, 11),
            updated_at=_timestamp(20, 12),
        )
        session.add(idle)
        session.commit()
        idle_id = idle.id
    finally:
        session.close()

    list_response = client.get(
        "/api/admin/work-time/sessions",
        params={
            "worker_user_id": worker_id,
            "from_ts": _timestamp(20, 6),
            "to_ts": _timestamp(20, 18),
        },
    )
    assert list_response.status_code == 200
    listed_idle = next(item for item in list_response.json() if item["id"] == idle_id)
    assert listed_idle["timer_type"] == "idle"
    assert listed_idle["order_id"] is None
    assert listed_idle["editable"] is True

    update_response = client.patch(
        f"/api/admin/work-time/sessions/{idle_id}",
        json={
            "operation_id": None,
            "started_at": _timestamp(20, 7),
            "ended_at": _timestamp(20, 7, 30),
            "expected_updated_at": listed_idle["updated_at"],
        },
    )
    assert update_response.status_code == 200
    updated_idle = update_response.json()
    assert updated_idle["timer_type"] == "idle"
    assert updated_idle["order_id"] is None
    assert updated_idle["operation_id"] is None

    delete_response = client.delete(
        f"/api/admin/work-time/sessions/{idle_id}",
        params={"expected_updated_at": updated_idle["updated_at"]},
    )
    assert delete_response.status_code == 204

    session = db_session()
    try:
        stored_idle = session.scalars(
            select(TimerSession).where(TimerSession.id == idle_id)
        ).one()
        stored_shift = session.scalars(
            select(WorkShift).where(WorkShift.id == shift_id)
        ).one()
        stored_order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        actions = session.scalars(
            select(TimerSessionAuditLog.action)
            .where(TimerSessionAuditLog.timer_session_id == idle_id)
            .order_by(TimerSessionAuditLog.id.asc())
        ).all()
        assert stored_idle.deleted_at is not None
        assert stored_shift.started_at == _timestamp(20, 7)
        assert stored_order.taken_at == 1
        assert actions == ["update", "delete"]
    finally:
        session.close()


@pytest.mark.parametrize(
    "service_timer_type",
    [TimerType.PREPARATION, TimerType.BREAK, TimerType.IDLE],
    ids=["preparation", "break", "idle"],
)
def test_admin_replaces_service_interval_with_order_operation(
    client: TestClient,
    db_session: sessionmaker[Session],
    service_timer_type: TimerType,
) -> None:
    """
    Проверяем замену служебного интервала производственной операцией:
    - запретить замену при пересечении с операцией выбранного заказа
    - преобразовать «Подготовку», «Перерыв» и «Брак/Ремонт» для свободного интервала
    """
    worker_id, order_id, regular_id, _cutting_id, shift_id = _seed_work_time_graph(
        db_session
    )
    session = db_session()
    try:
        existing_operation = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            order_id=order_id,
            operation_id=regular_id,
            started_at=_timestamp(20, 9),
            ended_at=_timestamp(20, 10),
            created_at=_timestamp(20, 9),
            updated_at=_timestamp(20, 10),
        )
        idle = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[service_timer_type],
            order_id=None,
            operation_id=None,
            started_at=_timestamp(20, 11),
            ended_at=_timestamp(20, 12),
            created_at=_timestamp(20, 11),
            updated_at=_timestamp(20, 12),
        )
        session.add_all([existing_operation, idle])
        session.commit()
        idle_id = idle.id
    finally:
        session.close()

    list_response = client.get(
        "/api/admin/work-time/sessions",
        params={
            "worker_user_id": worker_id,
            "from_ts": _timestamp(20, 8),
            "to_ts": _timestamp(20, 18),
        },
    )
    assert list_response.status_code == 200
    listed_interval = next(
        item for item in list_response.json() if item["id"] == idle_id
    )
    assert listed_interval["timer_type"] == service_timer_type.value
    assert listed_interval["editable"] is True

    collision_response = client.patch(
        f"/api/admin/work-time/sessions/{idle_id}",
        json={
            "order_id": order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 9, 30),
            "ended_at": _timestamp(20, 10, 30),
            "expected_updated_at": listed_interval["updated_at"],
        },
    )
    assert collision_response.status_code == 409

    update_response = client.patch(
        f"/api/admin/work-time/sessions/{idle_id}",
        json={
            "order_id": order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 12),
            "ended_at": _timestamp(20, 13),
            "expected_updated_at": listed_interval["updated_at"],
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["timer_type"] == "operation"
    assert updated["order_id"] == order_id
    assert updated["operation_id"] == regular_id
    assert updated["editable"] is True

    session = db_session()
    try:
        order = session.scalars(
            select(WorkOrder).where(WorkOrder.id == order_id)
        ).one()
        timer_session = session.scalars(
            select(TimerSession).where(TimerSession.id == idle_id)
        ).one()
        assert order.total_spent_seconds == 7200
        assert timer_session.timer_type_code == TIMER_TYPE_TO_CODE[TimerType.OPERATION]
        assert timer_session.order_id == order_id
        assert timer_session.operation_id == regular_id
    finally:
        session.close()


def test_admin_rejects_active_allocated_and_stale_sessions(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем защищённые состояния записи времени:
    - запретить правку активной и распределённой операции
    - отклонить сохранение с устаревшей версией
    """
    worker_id, order_id, regular_id, _cutting_id, shift_id = _seed_work_time_graph(
        db_session
    )
    session = db_session()
    try:
        active = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            order_id=order_id,
            operation_id=regular_id,
            started_at=_timestamp(20, 17),
            ended_at=None,
            created_at=_timestamp(20, 17),
            updated_at=_timestamp(20, 17),
        )
        allocated = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            order_id=order_id,
            operation_id=regular_id,
            started_at=_timestamp(20, 12),
            ended_at=_timestamp(20, 13),
            created_at=_timestamp(20, 12),
            updated_at=_timestamp(20, 13),
        )
        stale = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            order_id=order_id,
            operation_id=regular_id,
            started_at=_timestamp(20, 14),
            ended_at=_timestamp(20, 15),
            created_at=_timestamp(20, 14),
            updated_at=_timestamp(20, 15),
        )
        session.add_all([active, allocated, stale])
        session.flush()
        session.add(
            WorkOrderTimeAllocation(
                timer_session_id=allocated.id,
                work_order_id=order_id,
                allocated_seconds=3600,
                created_at=1,
                updated_at=1,
            )
        )
        session.commit()
        active_id = active.id
        allocated_id = allocated.id
        stale_id = stale.id
    finally:
        session.close()

    payload = {
        "operation_id": regular_id,
        "started_at": _timestamp(20, 14),
        "ended_at": _timestamp(20, 15),
        "expected_updated_at": _timestamp(20, 15),
    }
    active_response = client.patch(
        f"/api/admin/work-time/sessions/{active_id}",
        json=payload,
    )
    allocated_response = client.patch(
        f"/api/admin/work-time/sessions/{allocated_id}",
        json=payload,
    )
    stale_response = client.patch(
        f"/api/admin/work-time/sessions/{stale_id}",
        json={**payload, "expected_updated_at": 1},
    )

    assert active_response.status_code == 409
    assert allocated_response.status_code == 409
    assert stale_response.status_code == 409


def test_admin_rejects_operation_without_order(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем обязательную связь производственной операции с заказом:
    - создать завершённую операцию без доступного заказа
    - вернуть явную ошибку при изменении и удалении записи
    """
    worker_id, _order_id, regular_id, _cutting_id, shift_id = (
        _seed_work_time_graph(db_session)
    )
    session = db_session()
    try:
        orphan_operation = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            order_id=None,
            operation_id=regular_id,
            started_at=_timestamp(20, 12),
            ended_at=_timestamp(20, 13),
            created_at=_timestamp(20, 12),
            updated_at=_timestamp(20, 13),
        )
        session.add(orphan_operation)
        session.commit()
        orphan_operation_id = orphan_operation.id
        expected_updated_at = orphan_operation.updated_at
    finally:
        session.close()

    update_response = client.patch(
        f"/api/admin/work-time/sessions/{orphan_operation_id}",
        json={
            "operation_id": regular_id,
            "started_at": _timestamp(20, 12),
            "ended_at": _timestamp(20, 13),
            "expected_updated_at": expected_updated_at,
        },
    )
    delete_response = client.delete(
        f"/api/admin/work-time/sessions/{orphan_operation_id}",
        params={"expected_updated_at": expected_updated_at},
    )

    assert update_response.status_code == 422
    assert update_response.json()["detail"] == "Заказ операции недоступен."
    assert delete_response.status_code == 422
    assert delete_response.json()["detail"] == "Заказ операции недоступен."


def test_admin_marks_historical_workers_that_cannot_receive_new_time(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем доступность добавления времени исполнителю:
    - разрешить добавление активному пользователю с ролью worker
    - оставить бывшего исполнителя в списке истории без права добавления
    - показать неактивного исполнителя только по отдельному фильтру
    """
    worker_id, order_id, regular_id, _cutting_id, shift_id = _seed_work_time_graph(
        db_session
    )

    active_response = client.get("/api/admin/work-time/workers")

    session = db_session()
    try:
        worker = session.scalars(select(User).where(User.id == worker_id)).one()
        admin = session.scalars(select(User).where(User.phone == "+79990000001")).one()
        historical_timer = TimerSession(
            shift_id=shift_id,
            user_id=worker_id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.BREAK],
            order_id=None,
            operation_id=None,
            started_at=_timestamp(20, 8),
            ended_at=_timestamp(20, 9),
            created_at=_timestamp(20, 8),
            updated_at=_timestamp(20, 9),
        )
        inactive_worker = User(
            name="Неактивный исполнитель",
            phone="+79990000202",
            password_hash=hash_password("password123"),
            roles=["worker"],
            is_active=False,
            created_at=1,
            updated_at=1,
            deleted_at=None,
            author_user_id=admin.id,
        )
        worker.roles = ["constructor"]
        session.add_all([historical_timer, inactive_worker])
        session.commit()
        inactive_worker_id = inactive_worker.id
    finally:
        session.close()

    historical_response = client.get("/api/admin/work-time/workers")
    all_workers_response = client.get(
        "/api/admin/work-time/workers",
        params={"include_inactive": True},
    )
    rejected_create_response = client.post(
        "/api/admin/work-time/sessions",
        json={
            "worker_user_id": worker_id,
            "order_id": order_id,
            "operation_id": regular_id,
            "started_at": _timestamp(20, 16),
            "ended_at": _timestamp(20, 17),
        },
    )

    assert active_response.status_code == 200
    active_workers = {item["id"]: item for item in active_response.json()}
    assert active_workers[worker_id]["can_add_time"] is True
    assert historical_response.status_code == 200
    historical_workers = {item["id"]: item for item in historical_response.json()}
    assert historical_workers[worker_id]["can_add_time"] is False
    assert inactive_worker_id not in historical_workers
    assert all_workers_response.status_code == 200
    all_workers = {item["id"]: item for item in all_workers_response.json()}
    assert all_workers[inactive_worker_id]["can_add_time"] is False
    assert rejected_create_response.status_code == 422


def test_non_admin_cannot_access_work_time_routes(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем серверное ограничение административной формы:
    - авторизовать пользователя только с ролью исполнителя
    - вернуть запрет доступа к списку исполнителей
    """
    worker_id, _order_id, _regular_id, _cutting_id, _shift_id = _seed_work_time_graph(
        db_session
    )
    session = db_session()
    try:
        worker = session.scalars(select(User).where(User.id == worker_id)).one()
        worker.password_hash = hash_password("worker-password")
        session.commit()
        worker_phone = worker.phone
    finally:
        session.close()

    client.post("/api/auth/logout")
    login_response = client.post(
        "/api/auth/login",
        json={"phone": worker_phone, "password": "worker-password"},
    )
    assert login_response.status_code == 200

    response = client.get("/api/admin/work-time/workers")
    assert response.status_code == 403

from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.leather_type import LeatherType
from app.models.product import Product
from app.models.work_order import WorkOrder
from app.schemas.order import WorkOrderQualityControlAccept, WorkOrderStatusUpdate
from app.schemas.planning import WorkScheduleBatchUpdate
from app.services.order_service import OrderService
from app.services.planning_service import PlanningService


def create_user(
    client: TestClient,
    *,
    name: str,
    phone: str,
    roles: list[str],
    is_active: bool = True,
) -> dict:
    response = client.post(
        "/api/users",
        json={
            "name": name,
            "phone": phone,
            "roles": roles,
            "is_active": is_active,
        },
    )
    assert response.status_code == 201
    return dict(response.json())


def create_planning_queue_orders(
    db_session: sessionmaker[Session],
) -> list[int]:
    session = db_session()
    try:
        product = Product(
            name="Изделие очереди",
            version="1.0",
            comment=None,
            author="Test Admin",
            author_user_id=1,
            material_cost_cents=None,
            stage_count=1,
            is_active=True,
            created_at=1,
        )
        leather_type = LeatherType(
            name="Кожа очереди",
            is_active=True,
            created_at=1,
            updated_at=1,
        )
        session.add_all([product, leather_type])
        session.flush()
        orders = [
            WorkOrder(
                order_number=f"QUEUE-{index}",
                product_id=product.id,
                leather_type_id=leather_type.id,
                quantity=index,
                planned_completion_date=None,
                estimated_minutes=100,
                total_spent_seconds=0,
                cutting_spent_seconds=0,
                production_stage=stage,
                created_at=index,
                updated_at=index,
                cutting_started_at=None,
                sewing_started_at=None,
                taken_at=None,
                quality_control_at=quality_control_at,
                defect_quantity=0,
                completed_at=None,
                deleted_at=deleted_at,
                planning_priority_rank=index * 1024,
                planning_excluded_at=None,
            )
            for index, stage, quality_control_at, deleted_at in [
                (1, "created", None, None),
                (2, "cutting", None, None),
                (3, "in_work", 3, None),
                (4, "in_work", None, 4),
            ]
        ]
        session.add_all(orders)
        session.commit()
        return [order.id for order in orders]
    finally:
        session.close()


def test_planning_settings_defaults_and_update(client: TestClient) -> None:
    """
    Проверяем настройки планирования:
    - создать значения по умолчанию при первом чтении
    - сохранить смещение, подготовку и горизонт
    - вернуть автора и timestamp изменения
    """
    get_response = client.get("/api/planning/settings")

    assert get_response.status_code == 200
    assert get_response.json()["display_offset_days"] == 2
    assert get_response.json()["preparation_seconds"] == 3600
    assert get_response.json()["horizon_months"] == 3

    update_response = client.patch(
        "/api/planning/settings",
        json={
            "display_offset_days": 4,
            "preparation_seconds": 7200,
            "horizon_months": 6,
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["display_offset_days"] == 4
    assert updated["preparation_seconds"] == 7200
    assert updated["horizon_months"] == 6
    assert updated["updated_by_user_id"] == 1
    assert updated["updated_at"] > 0


def test_planning_settings_reject_invalid_duration_and_horizon(
    client: TestClient,
) -> None:
    """
    Проверяем ограничения настроек планирования:
    - запретить отрицательное время подготовки
    - разрешить только согласованные горизонты расчёта
    """
    duration_response = client.patch(
        "/api/planning/settings",
        json={
            "display_offset_days": 2,
            "preparation_seconds": -1,
            "horizon_months": 3,
        },
    )
    horizon_response = client.patch(
        "/api/planning/settings",
        json={
            "display_offset_days": 2,
            "preparation_seconds": 3600,
            "horizon_months": 2,
        },
    )

    assert duration_response.status_code == 422
    assert horizon_response.status_code == 422


def test_work_schedule_batch_create_update_and_delete(client: TestClient) -> None:
    """
    Проверяем пакетное управление графиком:
    - создать несколько рабочих дней по восемь часов
    - изменить только выбранный день и сохранить пробелы
    - удалить выбранные заполненные дни
    """
    worker = create_user(
        client,
        name="Анна Графикова",
        phone="+79990000401",
        roles=["worker"],
    )
    create_response = client.put(
        "/api/planning/work-schedule",
        json={
            "user_id": worker["id"],
            "work_dates": ["2026-11-02", "2026-11-03", "2026-11-06"],
            "available_seconds": 28_800,
        },
    )
    assert create_response.status_code == 204

    update_response = client.put(
        "/api/planning/work-schedule",
        json={
            "user_id": worker["id"],
            "work_dates": ["2026-11-03"],
            "available_seconds": 43_200,
        },
    )
    assert update_response.status_code == 204

    calendar_response = client.get(
        "/api/planning/work-schedule?month=2026-11"
    )
    assert calendar_response.status_code == 200
    calendar = calendar_response.json()
    assert calendar["month"] == "2026-11"
    assert calendar["days_in_month"] == 30
    assert [item["user_name"] for item in calendar["workers"]] == [
        "Анна Графикова"
    ]
    assert calendar["workers"][0]["days"] == [
        {"work_date": "2026-11-02", "available_seconds": 28_800},
        {"work_date": "2026-11-03", "available_seconds": 43_200},
        {"work_date": "2026-11-06", "available_seconds": 28_800},
    ]

    delete_response = client.request(
        "DELETE",
        "/api/planning/work-schedule",
        json={
            "user_id": worker["id"],
            "work_dates": ["2026-11-02", "2026-11-06"],
        },
    )
    assert delete_response.status_code == 204

    remaining_response = client.get(
        "/api/planning/work-schedule?month=2026-11"
    )
    assert remaining_response.status_code == 200
    assert remaining_response.json()["workers"][0]["days"] == [
        {"work_date": "2026-11-03", "available_seconds": 43_200}
    ]


def test_work_schedule_lists_only_active_workers(client: TestClient) -> None:
    """
    Проверяем состав сотрудников календаря:
    - включить активного пользователя с ролью исполнителя
    - скрыть неисполнителя и неактивного исполнителя
    """
    create_user(
        client,
        name="Активный исполнитель",
        phone="+79990000402",
        roles=["worker"],
    )
    create_user(
        client,
        name="Только бригадир",
        phone="+79990000403",
        roles=["brigadier"],
    )
    create_user(
        client,
        name="Неактивный исполнитель",
        phone="+79990000404",
        roles=["worker"],
        is_active=False,
    )

    response = client.get("/api/planning/work-schedule?month=2026-11")

    assert response.status_code == 200
    assert [item["user_name"] for item in response.json()["workers"]] == [
        "Активный исполнитель"
    ]


def test_work_schedule_rejects_invalid_worker_and_hours(client: TestClient) -> None:
    """
    Проверяем серверную валидацию графика:
    - запретить график пользователю без роли исполнителя
    - запретить значение вне диапазона
    - разрешить дробное количество часов внутри диапазона
    """
    brigadier = create_user(
        client,
        name="Бригадир без графика",
        phone="+79990000405",
        roles=["brigadier"],
    )
    invalid_worker_response = client.put(
        "/api/planning/work-schedule",
        json={
            "user_id": brigadier["id"],
            "work_dates": ["2026-11-02"],
            "available_seconds": 28_800,
        },
    )
    too_long_response = client.put(
        "/api/planning/work-schedule",
        json={
            "user_id": 1,
            "work_dates": ["2026-11-02"],
            "available_seconds": 61_200,
        },
    )
    worker = create_user(
        client,
        name="Исполнитель с дробными часами",
        phone="+79990000408",
        roles=["worker"],
    )
    partial_hour_response = client.put(
        "/api/planning/work-schedule",
        json={
            "user_id": worker["id"],
            "work_dates": ["2026-11-02"],
            "available_seconds": 5400,
        },
    )

    assert invalid_worker_response.status_code == 422
    assert invalid_worker_response.json()["detail"] == (
        "График можно изменять только активному исполнителю."
    )
    assert too_long_response.status_code == 422
    assert partial_hour_response.status_code == 204


def test_brigadier_can_manage_schedule_but_not_settings(client: TestClient) -> None:
    """
    Проверяем права этапа планирования:
    - разрешить бригадиру читать и менять график исполнителей
    - запретить бригадиру читать настройки планирования
    """
    worker = create_user(
        client,
        name="Исполнитель бригадира",
        phone="+79990000406",
        roles=["worker"],
    )
    brigadier = create_user(
        client,
        name="Бригадир графика",
        phone="+79990000407",
        roles=["brigadier"],
    )
    setup_response = client.post(
        "/api/auth/setup-password",
        json={
            "phone": brigadier["phone"],
            "new_password": "password123",
        },
    )
    assert setup_response.status_code == 200

    calendar_response = client.get(
        "/api/planning/work-schedule?month=2026-11"
    )
    update_response = client.put(
        "/api/planning/work-schedule",
        json={
            "user_id": worker["id"],
            "work_dates": ["2026-11-02"],
            "available_seconds": 28_800,
        },
    )
    settings_response = client.get("/api/planning/settings")

    assert calendar_response.status_code == 200
    assert update_response.status_code == 204
    assert settings_response.status_code == 403


def test_work_schedule_translates_concurrent_insert_conflict(
    client: TestClient,
    db_session: sessionmaker[Session],
    monkeypatch,
) -> None:
    """
    Проверяем искусственную гонку создания одного рабочего дня:
    - имитировать нарушение уникальности при фиксации транзакции
    - вернуть управляемый конфликт вместо внутренней ошибки
    """
    worker = create_user(
        client,
        name="Исполнитель конкурентного графика",
        phone="+79990000409",
        roles=["worker"],
    )

    service_session = db_session()

    def raise_integrity_error() -> None:
        raise IntegrityError("concurrent schedule insert", {}, Exception())

    monkeypatch.setattr(service_session, "commit", raise_integrity_error)
    try:
        with pytest.raises(HTTPException) as error_info:
            PlanningService(service_session).update_work_schedule(
                WorkScheduleBatchUpdate(
                    user_id=worker["id"],
                    work_dates=[date(2026, 11, 2)],
                    available_seconds=28_800,
                ),
                updated_by_user_id=1,
            )
        assert error_info.value.status_code == 409
        assert error_info.value.detail == (
            "График уже изменён другим пользователем. Обновить календарь "
            "и повторить сохранение."
        )
    finally:
        service_session.close()


def test_planning_queue_reorders_by_position_and_neighbors(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем общую очередь приоритетов:
    - скрыть удалённый заказ
    - показать ОТК как отдельную стадию
    - вставить заказ в занятую ручную позицию со сдвигом
    - переместить заказ между указанными соседями
    """
    first_id, second_id, quality_control_id, _ = create_planning_queue_orders(
        db_session
    )

    initial_response = client.get("/api/planning/queue")

    assert initial_response.status_code == 200
    initial = initial_response.json()
    assert initial["revision"] == 0
    assert [item["order_id"] for item in initial["items"]] == [
        first_id,
        second_id,
        quality_control_id,
    ]
    assert [item["position"] for item in initial["items"]] == [1, 2, 3]
    assert initial["items"][2]["stage"] == "quality_control"

    manual_response = client.patch(
        "/api/planning/queue",
        json={
            "order_id": quality_control_id,
            "expected_revision": initial["revision"],
            "position": 2,
        },
    )

    assert manual_response.status_code == 200
    manual = manual_response.json()
    assert manual["revision"] == 1
    assert [item["order_id"] for item in manual["items"]] == [
        first_id,
        quality_control_id,
        second_id,
    ]

    neighbor_response = client.patch(
        "/api/planning/queue",
        json={
            "order_id": first_id,
            "expected_revision": manual["revision"],
            "before_order_id": second_id,
            "after_order_id": None,
        },
    )

    assert neighbor_response.status_code == 200
    assert neighbor_response.json()["revision"] == 2
    assert [item["order_id"] for item in neighbor_response.json()["items"]] == [
        quality_control_id,
        second_id,
        first_id,
    ]


def test_planning_queue_rejects_stale_revision_with_current_snapshot(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем защиту от устаревшего сохранения:
    - изменить очередь с актуальной ревизией
    - отклонить повторное изменение со старой ревизией
    - вернуть в конфликте актуальную очередь
    """
    first_id, second_id, quality_control_id, _ = create_planning_queue_orders(
        db_session
    )
    initial = client.get("/api/planning/queue").json()
    changed_response = client.patch(
        "/api/planning/queue",
        json={
            "order_id": second_id,
            "expected_revision": initial["revision"],
            "position": 1,
        },
    )
    assert changed_response.status_code == 200

    stale_response = client.patch(
        "/api/planning/queue",
        json={
            "order_id": quality_control_id,
            "expected_revision": initial["revision"],
            "position": 1,
        },
    )

    assert stale_response.status_code == 409
    detail = stale_response.json()["detail"]
    assert detail["code"] == "planning_queue_revision_conflict"
    assert detail["current"]["revision"] == 1
    assert [item["order_id"] for item in detail["current"]["items"]] == [
        second_id,
        first_id,
        quality_control_id,
    ]


def test_deleted_order_restores_with_preserved_priority(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем удаление и восстановление заказа:
    - исключить удалённый заказ из отображаемой очереди
    - не изменять его сохранённый ранг
    - вернуть заказ на прежнее место после восстановления
    """
    first_id, second_id, quality_control_id, deleted_id = (
        create_planning_queue_orders(db_session)
    )
    session = db_session()
    try:
        deleted_order = session.get(WorkOrder, deleted_id)
        assert deleted_order is not None
        stored_rank = deleted_order.planning_priority_rank
    finally:
        session.close()

    restore_response = client.patch(
        f"/api/orders/{deleted_id}/deleted-status",
        json={"is_deleted": False},
    )

    assert restore_response.status_code == 200
    queue = client.get("/api/planning/queue").json()
    assert [item["order_id"] for item in queue["items"]] == [
        first_id,
        second_id,
        quality_control_id,
        deleted_id,
    ]
    session = db_session()
    try:
        restored_order = session.get(WorkOrder, deleted_id)
        assert restored_order is not None
        assert restored_order.planning_priority_rank == stored_rank
    finally:
        session.close()


def test_first_completion_permanently_excludes_order_from_planning(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем необратимое исключение после первого завершения:
    - установить флаг при приёмке ОТК
    - не возвращать заказ в очередь после отмены завершения
    - сохранить timestamp первого завершения
    """
    _, _, quality_control_id, _ = create_planning_queue_orders(db_session)
    session = db_session()
    try:
        service = OrderService(session)
        completed = service.accept_order_quality_control(
            quality_control_id,
            WorkOrderQualityControlAccept(defect_quantity=0),
        )
        stored_order = session.get(WorkOrder, quality_control_id)
        assert stored_order is not None
        excluded_at = stored_order.planning_excluded_at
        assert completed.completed_at is not None
        assert excluded_at == completed.completed_at

        returned = service.update_order_status(
            quality_control_id,
            WorkOrderStatusUpdate(is_completed=False),
        )
        stored_order = session.get(WorkOrder, quality_control_id)
        assert stored_order is not None
        assert returned.completed_at is None
        assert stored_order.planning_excluded_at == excluded_at
    finally:
        session.close()

    queue_response = client.get("/api/planning/queue")

    assert queue_response.status_code == 200
    assert quality_control_id not in {
        item["order_id"] for item in queue_response.json()["items"]
    }

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderAssignment, WorkOrderFamily
from app.models.work_shift import WorkShift
from app.schemas.order import (
    WorkOrderDeletedStatusUpdate,
    WorkOrderMergeRequest,
    WorkOrderSplitRequest,
)
from app.schemas.timer import TimerType
from app.services.order_service import OrderService
from app.services.report_service import ReportService
from app.services.timer_service import TIMER_TYPE_TO_CODE


def _create_order_graph(
    db_session: sessionmaker[Session],
    *,
    quantity: int = 101,
    estimated_minutes: int = 101,
    elapsed_ms: int | None = None,
) -> tuple[int, int]:
    session = db_session()
    try:
        worker = User(
            name="Раскройщик",
            phone="+79990000010",
            password_hash=None,
            roles=["worker"],
            is_active=True,
            created_at=1,
            updated_at=1,
            deleted_at=None,
            author_user_id=None,
        )
        session.add(worker)
        session.flush()
        worker.author_user_id = worker.id
        product = Product(
            name="Сумка",
            version="1.0",
            author="Конструктор",
            author_user_id=worker.id,
            is_active=True,
            created_at=1,
        )
        session.add(product)
        session.flush()
        catalog_entry = OperationCatalogEntry(
            name="Крой",
            operation_kind="cutting",
            is_active=True,
            created_at=1,
            updated_at=1,
        )
        session.add(catalog_entry)
        session.flush()
        operation = Operation(
            product_id=product.id,
            parent_id=None,
            operation_catalog_entry_id=catalog_entry.id,
            name="Крой",
        )
        session.add(operation)
        session.flush()
        regular_catalog_entry = OperationCatalogEntry(
            name="Сборка",
            operation_kind="regular",
            is_active=True,
            created_at=1,
            updated_at=1,
        )
        session.add(regular_catalog_entry)
        session.flush()
        regular_operation = Operation(
            product_id=product.id,
            parent_id=None,
            operation_catalog_entry_id=regular_catalog_entry.id,
            name="Сборка",
        )
        session.add(regular_operation)
        session.flush()
        order = WorkOrder(
            order_number="10001",
            product_id=product.id,
            quantity=quantity,
            estimated_minutes=estimated_minutes,
            total_spent_seconds=0,
            production_stage="in_work",
            created_at=1,
            updated_at=1,
            taken_at=1,
        )
        order.assignments = [
            WorkOrderAssignment(
                operation_id=operation.id,
                worker_user_id=worker.id,
            ),
            WorkOrderAssignment(
                operation_id=regular_operation.id,
                worker_user_id=worker.id,
            ),
        ]
        session.add(order)
        session.flush()
        if elapsed_ms is not None:
            shift = WorkShift(
                user_id=worker.id,
                started_at=1,
                ended_at=elapsed_ms + 1,
                business_date="2026-10-25",
                created_at=1,
            )
            session.add(shift)
            session.flush()
            session.add(
                TimerSession(
                    shift_id=shift.id,
                    user_id=worker.id,
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=order.id,
                    operation_id=operation.id,
                    started_at=1,
                    ended_at=elapsed_ms + 1,
                    created_at=1,
                )
            )
        session.commit()
        return worker.id, order.id
    finally:
        session.close()


def test_split_order_creates_family_and_distributes_seconds(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем первое разделение заказа с учтенным временем кроя:
    - сохранить исходный номер у первой части и создать номер с суффиксом /2
    - разделить количество, план и секунды с остатком в исходной части
    - учитывать распределенное время в детализации и отчете без удвоения
    """
    _, order_id = _create_order_graph(db_session, elapsed_ms=101_000)
    session = db_session()
    try:
        result = OrderService(session).split_order(
            order_id,
            WorkOrderSplitRequest(source_quantity=51),
        )
        source_breakdown = OrderService(session).get_order_time_breakdown(
            result.source.id
        )
        created_breakdown = OrderService(session).get_order_time_breakdown(
            result.created.id
        )
        report = ReportService(session).get_product_time_report(
            date(2026, 10, 25),
            date(2026, 10, 25),
        )

        assert result.source.order_number == "10001"
        assert result.source.part_number == 1
        assert result.source.quantity == 51
        assert result.source.estimated_minutes == 51
        assert result.source.total_spent_seconds == 51
        assert result.created.order_number == "10001/2"
        assert result.created.part_number == 2
        assert result.created.quantity == 50
        assert result.created.estimated_minutes == 50
        assert result.created.total_spent_seconds == 50
        assert source_breakdown.total_elapsed_ms == 51_000
        assert created_breakdown.total_elapsed_ms == 50_000
        assert report.products[0].total_elapsed_ms == 101_000
    finally:
        session.close()


def test_split_family_uses_next_number_for_any_part(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем сквозную нумерацию частей семейства:
    - разделить исходный заказ на части 1 и 2
    - разделить часть 2 и создать часть 3 от базового номера
    - не переиспользовать номер удаленной части при следующем разделении
    """
    _, order_id = _create_order_graph(db_session, quantity=8, estimated_minutes=8)
    session = db_session()
    try:
        first_split = OrderService(session).split_order(
            order_id,
            WorkOrderSplitRequest(source_quantity=4),
        )
        second_split = OrderService(session).split_order(
            first_split.created.id,
            WorkOrderSplitRequest(source_quantity=2),
        )
        OrderService(session).update_order_deleted_status(
            second_split.created.id,
            WorkOrderDeletedStatusUpdate(is_deleted=True),
        )
        third_split = OrderService(session).split_order(
            second_split.source.id,
            WorkOrderSplitRequest(source_quantity=1),
        )

        assert second_split.source.order_number == "10001/2"
        assert second_split.created.order_number == "10001/3"
        assert third_split.created.order_number == "10001/4"
        family = session.scalar(select(WorkOrderFamily))
        assert family is not None
        assert family.last_part_number == 4
    finally:
        session.close()


def test_merge_last_part_collapses_family_and_preserves_legacy_qr(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем слияние последних частей семейства:
    - включить исходную часть в заказ /2 и вернуть базовый номер получателю
    - разрешить старый QR удаленной части через сохраненную ссылку
    """
    worker_id, order_id = _create_order_graph(
        db_session,
        quantity=10,
        estimated_minutes=20,
            elapsed_ms=101_000,
    )
    session = db_session()
    try:
        split_result = OrderService(session).split_order(
            order_id,
            WorkOrderSplitRequest(source_quantity=6),
        )
        merged = OrderService(session).merge_orders(
            split_result.created.id,
            WorkOrderMergeRequest(included_order_ids=[split_result.source.id]),
        )
        qr_target = OrderService(session).get_worker_orders_by_qr(
            worker_user_id=worker_id,
            order_reference=None,
            legacy_order_id=split_result.source.id,
        )

        assert merged.order_number == "10001"
        assert merged.family_id is None
        assert merged.part_number is None
        assert merged.quantity == 10
        assert merged.estimated_minutes == 20
        assert merged.total_spent_seconds == 101
        assert merged.cutting_spent_seconds == 101
        assert OrderService(session).get_order_time_breakdown(
            merged.id
        ).total_elapsed_ms == 101_000
        assert session.scalar(select(WorkOrderFamily)) is None
        assert [order.id for order in qr_target.orders] == [merged.id]
    finally:
        session.close()


def test_split_order_rejects_active_timer(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем запрет разделения с активным таймером:
    - запустить обычную операцию заказа в работе
    - вернуть понятную причину отказа без создания новой части
    """
    worker_id, order_id = _create_order_graph(db_session)
    session = db_session()
    try:
        regular_operation = session.scalar(
            select(Operation)
            .join(OperationCatalogEntry)
            .where(OperationCatalogEntry.operation_kind == "regular")
        )
        assert regular_operation is not None
        shift = WorkShift(
            user_id=worker_id,
            started_at=10,
            ended_at=None,
            business_date="2026-10-25",
            created_at=10,
        )
        session.add(shift)
        session.flush()
        session.add(
            TimerSession(
                shift_id=shift.id,
                user_id=worker_id,
                timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                order_id=order_id,
                operation_id=regular_operation.id,
                started_at=10,
                ended_at=None,
                created_at=10,
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            OrderService(session).split_order(
                order_id,
                WorkOrderSplitRequest(source_quantity=50),
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "Сначала остановить запущенные таймеры заказа."
        assert session.scalar(select(WorkOrderFamily)) is None
    finally:
        session.close()


def test_merge_orders_rejects_active_included_order_timer(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем запрет слияния с активным таймером включаемой части:
    - разделить заказ и запустить операцию исходной части
    - не включать занятую часть в доступные кандидаты и отклонить сохранение
    """
    worker_id, order_id = _create_order_graph(db_session)
    session = db_session()
    try:
        split_result = OrderService(session).split_order(
            order_id,
            WorkOrderSplitRequest(source_quantity=51),
        )
        regular_operation = session.scalar(
            select(Operation)
            .join(OperationCatalogEntry)
            .where(OperationCatalogEntry.operation_kind == "regular")
        )
        assert regular_operation is not None
        shift = WorkShift(
            user_id=worker_id,
            started_at=10,
            ended_at=None,
            business_date="2026-10-25",
            created_at=10,
        )
        session.add(shift)
        session.flush()
        session.add(
            TimerSession(
                shift_id=shift.id,
                user_id=worker_id,
                timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                order_id=split_result.source.id,
                operation_id=regular_operation.id,
                started_at=10,
                ended_at=None,
                created_at=10,
            )
        )
        session.commit()

        candidates = OrderService(session).list_merge_candidates(
            split_result.created.id,
            None,
        )
        assert candidates == []
        with pytest.raises(HTTPException) as exc_info:
            OrderService(session).merge_orders(
                split_result.created.id,
                WorkOrderMergeRequest(
                    included_order_ids=[split_result.source.id]
                ),
            )

        assert exc_info.value.status_code == 422
    finally:
        session.close()

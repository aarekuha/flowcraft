import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.work_order import (
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderAssignmentWorkerState,
)
from app.models.work_shift import WorkShift
from app.schemas.statistics import StatisticsOverviewRead
from app.schemas.timer import TimerSwitchPayload, TimerType
from app.services.statistics_service import StatisticsService
from app.services.timer_service import TIMER_TYPE_TO_CODE, TimerService


def _bootstrap_worker_graph(db_session: sessionmaker[Session]) -> tuple[int, int, int]:
    session = db_session()
    try:
        admin = User(
            name="Администратор",
            phone="+79990000001",
            password_hash=hash_password("password123"),
            roles=["admin"],
            is_active=True,
            created_at=1,
            updated_at=1,
            deleted_at=None,
            author_user_id=None,
        )
        worker = User(
            name="Исполнитель",
            phone="+79990000002",
            password_hash=None,
            roles=["worker"],
            is_active=True,
            created_at=1,
            updated_at=1,
            deleted_at=None,
            author_user_id=None,
        )
        session.add_all([admin, worker])
        session.flush()
        admin.author_user_id = admin.id
        worker.author_user_id = admin.id

        product = Product(
            name="Сумка City",
            version="1.0",
            author="Администратор",
            author_user_id=admin.id,
            is_active=True,
            created_at=1,
        )
        session.add(product)
        session.flush()

        operation_catalog_entry = OperationCatalogEntry(
            name="Пошив",
            is_active=True,
            created_at=1,
            updated_at=1,
        )
        session.add(operation_catalog_entry)
        session.flush()

        operation = Operation(
            product_id=product.id,
            parent_id=None,
            operation_catalog_entry_id=operation_catalog_entry.id,
            name="Пошив",
        )
        session.add(operation)
        session.flush()

        order = WorkOrder(
            order_number="FC-0001",
            product_id=product.id,
            quantity=10,
            total_spent_minutes=0,
            created_at=1,
            updated_at=1,
            taken_at=1,
        )
        order.assignments = [
            WorkOrderAssignment(
                operation_id=operation.id,
                worker_user_id=worker.id,
            )
        ]
        session.add(order)
        session.commit()
        return worker.id, order.id, operation.id
    finally:
        session.close()


def test_timer_service_starts_switches_and_ends_shift(
    db_session: sessionmaker[Session],
) -> None:
    worker_id, order_id, operation_id = _bootstrap_worker_graph(db_session)
    session = db_session()
    try:
        service = TimerService(session)

        start_state = service.start_day(worker_id)
        assert start_state.shift is not None
        assert start_state.active_timer is not None
        assert start_state.active_timer.timer_type == TimerType.PREPARATION

        operation_state = service.switch_timer(
            worker_id,
            TimerSwitchPayload(
                timer_type=TimerType.OPERATION,
                order_id=order_id,
                operation_id=operation_id,
            ),
        )
        assert operation_state.active_timer is not None
        assert operation_state.active_timer.timer_type == TimerType.OPERATION
        assert operation_state.active_timer.order_id == order_id
        assert operation_state.active_timer.operation_id == operation_id

        idle_state = service.switch_timer(
            worker_id,
            TimerSwitchPayload(timer_type=TimerType.IDLE),
        )
        assert idle_state.active_timer is not None
        assert idle_state.active_timer.timer_type == TimerType.IDLE
        assert any(
            item.timer_type == TimerType.OPERATION and item.order_id == order_id
            for item in idle_state.timer_totals
        )

        end_state = service.end_day(worker_id)
        assert end_state.shift is None
        assert end_state.active_timer is None
        assert end_state.timer_totals == []
    finally:
        session.close()


def test_timer_service_rejects_hidden_and_completed_assignment_timers(
    db_session: sessionmaker[Session],
) -> None:
    worker_id, order_id, operation_id = _bootstrap_worker_graph(db_session)
    session = db_session()
    try:
        timer_service = TimerService(session)
        timer_service.start_day(worker_id)

        assignment = session.scalars(
            select(WorkOrderAssignment).where(
                WorkOrderAssignment.work_order_id == order_id,
                WorkOrderAssignment.operation_id == operation_id,
                WorkOrderAssignment.worker_user_id == worker_id,
            )
        ).one()
        assignment_state = WorkOrderAssignmentWorkerState(
            assignment_id=assignment.id,
            worker_user_id=worker_id,
            hidden_at=2_000,
            completed_at=None,
            created_at=2_000,
            updated_at=2_000,
        )
        session.add(assignment_state)
        session.flush()

        with pytest.raises(HTTPException) as hidden_error:
            timer_service.switch_timer(
                worker_id,
                TimerSwitchPayload(
                    timer_type=TimerType.OPERATION,
                    order_id=order_id,
                    operation_id=operation_id,
                ),
            )
        assert hidden_error.value.status_code == 422
        assert hidden_error.value.detail == (
            "Операция скрыта или отмечена выполненной."
        )

        assignment_state.hidden_at = None
        assignment_state.completed_at = 3_000
        assignment_state.updated_at = 3_000
        session.flush()

        with pytest.raises(HTTPException) as completed_error:
            timer_service.switch_timer(
                worker_id,
                TimerSwitchPayload(
                    timer_type=TimerType.OPERATION,
                    order_id=order_id,
                    operation_id=operation_id,
                ),
            )
        assert completed_error.value.status_code == 422
        assert completed_error.value.detail == (
            "Операция скрыта или отмечена выполненной."
        )
    finally:
        session.close()


def test_timer_service_refreshes_work_order_total_from_operation_sessions(
    db_session: sessionmaker[Session],
) -> None:
    worker_id, order_id, operation_id = _bootstrap_worker_graph(db_session)
    session = db_session()
    try:
        shift = WorkShift(
            user_id=worker_id,
            started_at=1_000,
            ended_at=181_000,
            business_date="2026-06-01",
            created_at=1_000,
        )
        session.add(shift)
        session.flush()
        session.add_all(
            [
                TimerSession(
                    shift_id=shift.id,
                    user_id=worker_id,
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    order_id=order_id,
                    operation_id=operation_id,
                    started_at=1_000,
                    ended_at=121_000,
                    created_at=1_000,
                ),
                TimerSession(
                    shift_id=shift.id,
                    user_id=worker_id,
                    timer_type_code=TIMER_TYPE_TO_CODE[TimerType.PREPARATION],
                    order_id=None,
                    operation_id=None,
                    started_at=121_000,
                    ended_at=181_000,
                    created_at=121_000,
                ),
            ]
        )
        session.flush()

        TimerService(session)._refresh_work_order_totals({order_id})

        order = session.get(WorkOrder, order_id)
        assert order is not None
        assert order.total_spent_minutes == 2
    finally:
        session.close()


def test_timer_service_flushes_closed_operation_before_refreshing_order_total(
    db_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker_id, order_id, operation_id = _bootstrap_worker_graph(db_session)
    timestamps = iter([1_000, 2_000, 3_000, 4_000, 64_000, 65_000, 66_000])
    session = db_session()
    try:
        timer_service = TimerService(session)
        monkeypatch.setattr(timer_service, "_now_ts", lambda: next(timestamps))

        timer_service.start_day(worker_id)
        timer_service.switch_timer(
            worker_id,
            TimerSwitchPayload(
                timer_type=TimerType.OPERATION,
                order_id=order_id,
                operation_id=operation_id,
            ),
        )
        timer_service.switch_timer(
            worker_id,
            TimerSwitchPayload(timer_type=TimerType.BREAK),
        )

        order = session.get(WorkOrder, order_id)
        assert order is not None
        assert order.total_spent_minutes == 1
    finally:
        session.close()


def test_statistics_service_returns_overview(
    db_session: sessionmaker[Session],
) -> None:
    worker_id, order_id, operation_id = _bootstrap_worker_graph(db_session)
    session = db_session()
    try:
        timer_service = TimerService(session)
        timer_service.start_day(worker_id)
        timer_service.switch_timer(
            worker_id,
            TimerSwitchPayload(
                timer_type=TimerType.OPERATION,
                order_id=order_id,
                operation_id=operation_id,
            ),
        )
        timer_service.switch_timer(
            worker_id,
            TimerSwitchPayload(timer_type=TimerType.BREAK),
        )
        timer_service.end_day(worker_id)

        overview = StatisticsService(session).get_overview(14)
        assert isinstance(overview, StatisticsOverviewRead)
        assert overview.days == 14
        assert overview.kpis.total_tracked_ms >= 0
        assert len(overview.daily_breakdown) >= 1
        assert len(overview.workers) >= 1
        assert overview.workers[0].user_name == "Исполнитель"
    finally:
        session.close()

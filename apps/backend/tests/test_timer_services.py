from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.models.operation import Operation
from app.models.product import Product
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderAssignment
from app.schemas.statistics import StatisticsOverviewRead
from app.schemas.timer import TimerSwitchPayload, TimerType
from app.services.statistics_service import StatisticsService
from app.services.timer_service import TimerService


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

        operation = Operation(
            product_id=product.id,
            parent_id=None,
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
        timer_service.switch_timer(worker_id, TimerSwitchPayload(timer_type=TimerType.BREAK))
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

from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.domain.production_planning import ProductionPlanningCalculator
from app.models.operation import Operation
from app.models.planning import OperationTimeEstimate
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.work_order import WorkOrder
from app.models.work_shift import WorkShift
from app.services.operation_time_estimate_service import (
    ALGORITHM_VERSION,
    OperationTimeEstimateService,
)
from app.services.production_planner_service import PlanningSnapshotBuilder


def test_estimate_uses_item_average_from_last_thirty_days(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем статистическую оценку норматива:
    - исключить изделия старше тридцати суток от последнего завершения
    - учитывать каждое изделие в среднем времени
    - объединить пересечения и исключить удалённое время
    """
    session = db_session()
    try:
        operation, worker = _create_product_operation_and_worker(session)
        samples = [
            (5, 4),
            (10, 4),
            (100, 100),
            (200, 1),
            (300, 1),
            (400, 1),
            (500, 1),
        ]
        for index, (seconds_per_item, quantity) in enumerate(samples, start=1):
            order = _create_order(
                session,
                product_id=operation.product_id,
                order_number=f"STAT-{index}",
                quantity=quantity,
                completed_at=(
                    index
                    if index <= 2
                    else 40 * 24 * 60 * 60 * 1000 + index
                ),
            )
            start = index * 20_000_000
            _add_operation_timer(
                session,
                worker_id=worker.id,
                order_id=order.id,
                operation_id=operation.id,
                started_at=start,
                duration_seconds=seconds_per_item * quantity,
            )
            if index == 3:
                _add_operation_timer(
                    session,
                    worker_id=worker.id,
                    order_id=order.id,
                    operation_id=operation.id,
                    started_at=start + 200_000,
                    duration_seconds=200,
                )
                _add_operation_timer(
                    session,
                    worker_id=worker.id,
                    order_id=order.id,
                    operation_id=operation.id,
                    started_at=start,
                    duration_seconds=4000,
                    deleted_at=start + 5_000_000,
                )
        session.commit()

        service = OperationTimeEstimateService(session)
        recalculated = service.recalculate_dirty(20_000)

        estimate = session.get(OperationTimeEstimate, operation.id)
        assert recalculated == 1
        assert estimate is not None
        assert estimate.seconds_per_item == 110
        assert estimate.completed_orders_count == 5
        assert estimate.items_count == 104
        assert estimate.calculated_at == 20_000
        assert estimate.algorithm_version == ALGORITHM_VERSION
        assert estimate.dirty_at is None
    finally:
        session.close()


def test_snapshot_prefers_manual_time_and_falls_back_to_statistics(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем выбор источника норматива:
    - использовать ручной норматив при наличии статистики
    - использовать статистическую оценку после удаления ручного норматива
    """
    session = db_session()
    try:
        operation, _ = _create_product_operation_and_worker(session)
        operation.standard_time_seconds = 150
        estimate = session.get(OperationTimeEstimate, operation.id)
        assert estimate is not None
        estimate.seconds_per_item = 200
        estimate.completed_orders_count = 5
        estimate.items_count = 20
        estimate.calculated_at = 20_000
        estimate.dirty_at = None
        order = _create_order(
            session,
            product_id=operation.product_id,
            order_number="OPEN-1",
            quantity=3,
            completed_at=None,
        )
        session.commit()

        manual_task = _find_task(
            PlanningSnapshotBuilder(session).build(
                datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
            ),
            order.id,
            operation.id,
        )
        assert manual_task.workload_seconds == 450
        assert manual_task.standard_time_seconds == 150
        assert manual_task.standard_time_source == "manual"

        operation.standard_time_seconds = None
        session.commit()
        statistical_task = _find_task(
            PlanningSnapshotBuilder(session).build(
                datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
            ),
            order.id,
            operation.id,
        )
        assert statistical_task.workload_seconds == 600
        assert statistical_task.standard_time_seconds == 200
        assert statistical_task.standard_time_source == "statistical"
    finally:
        session.close()


def test_five_items_create_statistical_standard_from_single_order(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем минимальный объём статистики:
    - принять пять изделий из одного завершённого заказа
    - использовать рассчитанное среднее в планировании
    """
    session = db_session()
    try:
        operation, worker = _create_product_operation_and_worker(session)
        completed_order = _create_order(
            session,
            product_id=operation.product_id,
            order_number="ENOUGH-1",
            quantity=5,
            completed_at=10_000,
        )
        _add_operation_timer(
            session,
            worker_id=worker.id,
            order_id=completed_order.id,
            operation_id=operation.id,
            started_at=3_000_000,
            duration_seconds=500,
        )
        open_order = _create_order(
            session,
            product_id=operation.product_id,
            order_number="OPEN-2",
            quantity=2,
            completed_at=None,
        )
        session.commit()

        OperationTimeEstimateService(session).recalculate_dirty(20_000)
        planning_input = PlanningSnapshotBuilder(session).build(
            datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
        )
        task = _find_task(planning_input, open_order.id, operation.id)
        output = ProductionPlanningCalculator().calculate(planning_input)

        estimate = session.get(OperationTimeEstimate, operation.id)
        assert estimate is not None
        assert estimate.seconds_per_item == 100
        assert estimate.completed_orders_count == 1
        assert estimate.items_count == 5
        assert task.workload_seconds == 200
        assert task.standard_time_seconds == 100
        assert task.standard_time_source == "statistical"
        assert output.operations[0].issue_codes != ("insufficient_statistics",)
    finally:
        session.close()


def test_last_five_items_supplement_sparse_thirty_day_window(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем резервную выборку последних изделий:
    - накопить два изделия за последние тридцать суток
    - дополнить выборку тремя изделиями из более старого заказа
    - рассчитать среднее ровно по пяти изделиям
    """
    session = db_session()
    try:
        operation, worker = _create_product_operation_and_worker(session)
        old_order = _create_order(
            session,
            product_id=operation.product_id,
            order_number="OLD-1",
            quantity=10,
            completed_at=1,
        )
        _add_operation_timer(
            session,
            worker_id=worker.id,
            order_id=old_order.id,
            operation_id=operation.id,
            started_at=1_000_000,
            duration_seconds=1000,
        )
        recent_order = _create_order(
            session,
            product_id=operation.product_id,
            order_number="RECENT-1",
            quantity=2,
            completed_at=40 * 24 * 60 * 60 * 1000,
        )
        _add_operation_timer(
            session,
            worker_id=worker.id,
            order_id=recent_order.id,
            operation_id=operation.id,
            started_at=40 * 24 * 60 * 60 * 1000,
            duration_seconds=400,
        )
        session.commit()

        OperationTimeEstimateService(session).recalculate_dirty(20_000)

        estimate = session.get(OperationTimeEstimate, operation.id)
        assert estimate is not None
        assert estimate.seconds_per_item == 140
        assert estimate.completed_orders_count == 2
        assert estimate.items_count == 5
    finally:
        session.close()


def test_fewer_than_five_items_do_not_create_statistical_standard(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем недостаточный объём статистики:
    - накопить четыре изделия независимо от количества заказов
    - вернуть отдельную причину отсутствия прогноза
    """
    session = db_session()
    try:
        operation, worker = _create_product_operation_and_worker(session)
        completed_order = _create_order(
            session,
            product_id=operation.product_id,
            order_number="SMALL-1",
            quantity=4,
            completed_at=10_000,
        )
        _add_operation_timer(
            session,
            worker_id=worker.id,
            order_id=completed_order.id,
            operation_id=operation.id,
            started_at=3_000_000,
            duration_seconds=400,
        )
        open_order = _create_order(
            session,
            product_id=operation.product_id,
            order_number="OPEN-3",
            quantity=1,
            completed_at=None,
        )
        session.commit()

        OperationTimeEstimateService(session).recalculate_dirty(20_000)
        planning_input = PlanningSnapshotBuilder(session).build(
            datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
        )
        task = _find_task(planning_input, open_order.id, operation.id)
        output = ProductionPlanningCalculator().calculate(planning_input)

        estimate = session.get(OperationTimeEstimate, operation.id)
        assert estimate is not None
        assert estimate.seconds_per_item is None
        assert estimate.completed_orders_count == 1
        assert estimate.items_count == 4
        assert task.workload_seconds is None
        assert task.missing_time_issue == "insufficient_statistics"
        assert output.operations[0].issue_codes == ("insufficient_statistics",)
    finally:
        session.close()


def test_recalculation_keeps_new_dirty_marker(
    db_session: sessionmaker[Session],
    monkeypatch,
) -> None:
    """
    Проверяем защиту фонового пересчёта от параллельного изменения:
    - изменить маркер после фиксации входного состояния
    - не публиковать оценку для устаревшего маркера
    - оставить операцию в очереди следующего пересчёта
    """
    session = db_session()
    try:
        operation, _ = _create_product_operation_and_worker(session)
        session.commit()
        service = OperationTimeEstimateService(session)

        def load_samples_and_mark_dirty(_operation_ids):
            service.mark_operations_dirty({operation.id}, dirty_at=1)
            session.flush()
            return {}

        monkeypatch.setattr(service, "_load_samples", load_samples_and_mark_dirty)

        assert service.recalculate_dirty(20_000) == 1
        estimate = session.get(OperationTimeEstimate, operation.id)
        assert estimate is not None
        assert estimate.dirty_at == 2
        assert estimate.calculated_at is None
    finally:
        session.close()


def test_recalculation_refreshes_previous_algorithm_version(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем переход на новую версию статистического алгоритма:
    - оставить сохранённую оценку без маркера изменений
    - указать предыдущую версию алгоритма
    - пересчитать оценку при ближайшем фоновом цикле
    """
    session = db_session()
    try:
        operation, worker = _create_product_operation_and_worker(session)
        for index in range(1, 6):
            order = _create_order(
                session,
                product_id=operation.product_id,
                order_number=f"VERSION-{index}",
                quantity=4,
                completed_at=10_000 + index,
            )
            _add_operation_timer(
                session,
                worker_id=worker.id,
                order_id=order.id,
                operation_id=operation.id,
                started_at=index * 3_000_000,
                duration_seconds=800,
            )
        estimate = session.get(OperationTimeEstimate, operation.id)
        assert estimate is not None
        estimate.seconds_per_item = 999
        estimate.completed_orders_count = 99
        estimate.items_count = 999
        estimate.algorithm_version = "weighted-median-v1"
        estimate.dirty_at = None
        session.commit()

        service = OperationTimeEstimateService(session)
        recalculated = service.recalculate_dirty(20_000)

        session.refresh(estimate)
        assert recalculated == 1
        assert estimate.seconds_per_item == 200
        assert estimate.completed_orders_count == 5
        assert estimate.items_count == 20
        assert estimate.algorithm_version == ALGORITHM_VERSION
        assert estimate.dirty_at is None
        assert service.has_outdated_estimates() is False
    finally:
        session.close()


def _create_product_operation_and_worker(
    session: Session,
) -> tuple[Operation, User]:
    worker = User(
        name="Исполнитель статистики",
        phone="+79990000999",
        password_hash=None,
        roles=["worker"],
        is_active=True,
        created_at=1,
        updated_at=1,
        deleted_at=None,
        author_user_id=None,
    )
    product = Product(
        name="Изделие статистики",
        version="1.0",
        comment=None,
        author="Исполнитель статистики",
        author_user_id=None,
        material_cost_cents=None,
        stage_count=1,
        is_active=True,
        created_at=1,
    )
    session.add_all([worker, product])
    session.flush()
    operation = Operation(
        product_id=product.id,
        parent_id=None,
        operation_catalog_entry_id=None,
        name="Операция статистики",
        price_cents=None,
        standard_time_seconds=None,
        stage_start=1,
        stage_end=1,
        sort_order=0,
    )
    session.add(operation)
    session.flush()
    session.add(
        OperationTimeEstimate(
            operation_id=operation.id,
            seconds_per_item=None,
            completed_orders_count=0,
            items_count=0,
            calculated_at=None,
            algorithm_version=ALGORITHM_VERSION,
            dirty_at=1,
        )
    )
    session.flush()
    return operation, worker


def _create_order(
    session: Session,
    *,
    product_id: int,
    order_number: str,
    quantity: int,
    completed_at: int | None,
) -> WorkOrder:
    order = WorkOrder(
        order_number=order_number,
        product_id=product_id,
        leather_type_id=None,
        quantity=quantity,
        planned_completion_date=None,
        estimated_minutes=0,
        total_spent_seconds=0,
        cutting_spent_seconds=0,
        production_stage="created",
        created_at=1,
        updated_at=1,
        cutting_started_at=None,
        sewing_started_at=None,
        taken_at=None,
        quality_control_at=completed_at,
        defect_quantity=0,
        completed_at=completed_at,
        deleted_at=None,
        planning_priority_rank=1024,
        planning_excluded_at=completed_at,
    )
    session.add(order)
    session.flush()
    return order


def _add_operation_timer(
    session: Session,
    *,
    worker_id: int,
    order_id: int,
    operation_id: int,
    started_at: int,
    duration_seconds: int,
    deleted_at: int | None = None,
) -> None:
    ended_at = started_at + duration_seconds * 1000
    shift = WorkShift(
        user_id=worker_id,
        started_at=started_at,
        ended_at=ended_at,
        business_date="2026-11-05",
        created_at=started_at,
    )
    session.add(shift)
    session.flush()
    session.add(
        TimerSession(
            shift_id=shift.id,
            user_id=worker_id,
            timer_type_code=2,
            order_id=order_id,
            operation_id=operation_id,
            started_at=started_at,
            ended_at=ended_at,
            created_at=started_at,
            updated_at=ended_at,
            deleted_at=deleted_at,
            deleted_by_user_id=None,
        )
    )


def _find_task(planning_input, order_id: int, operation_id: int):
    return next(
        task
        for order in planning_input.orders
        if order.order_id == order_id
        for task in order.tasks
        if task.operation_id == operation_id
    )

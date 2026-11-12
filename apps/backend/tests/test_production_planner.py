from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.domain.production_planning import (
    PlanningInput,
    PlanningOrderInput,
    PlanningTaskInput,
    ProductionPlanningCalculator,
)
from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.planning import (
    PlanningOperationResult,
    PlanningOrderResult,
    PlanningRun,
    PlanningSettings,
    PlanningWorkerDayAllocation,
    ProductionPlanningState,
    UserWorkScheduleDay,
)
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.user_operation_skill import UserOperationSkill
from app.models.work_order import WorkOrder, WorkOrderAssignment
from app.models.work_shift import WorkShift
from app.services.operation_time_estimate_service import OperationTimeEstimateService
from app.services.planning_revision_service import PlanningRevisionService
from app.services.production_planner_service import (
    WORKER_STALE_AFTER_MS,
    PlanningSnapshotBuilder,
    ProductionPlannerService,
)

TODAY = date(2026, 11, 5)


def test_planner_subtracts_actual_time_without_repeating_preparation() -> None:
    """
    Проверяем расчёт остатка начатой операции:
    - вычесть 300 секунд факта из норматива 1000 секунд
    - получить остаток 700 секунд
    - не добавлять подготовку повторно
    """
    task = create_task(
        operation_id=1,
        workload_seconds=1000,
        actual_seconds=300,
        eligible_worker_ids=(1,),
    )
    output = calculate(
        orders=(create_order(1, tasks=(task,)),),
        availability={(1, TODAY): 700},
    )

    result = output.operations[0]
    assert result.remaining_seconds == 700
    assert result.preparation_seconds == 0
    assert output.allocations[0].work_seconds == 700
    assert output.allocations[0].preparation_seconds == 0


def test_planner_runs_parallel_stage_operations_on_different_workers() -> None:
    """
    Проверяем параллельное выполнение этапа:
    - распределить две операции этапа разным сотрудникам на один день
    - разрешить следующий этап в тот же день при оставшейся мощности
    """
    tasks = (
        create_task(
            operation_id=1,
            workload_seconds=3600,
            eligible_worker_ids=(1,),
        ),
        create_task(
            operation_id=2,
            workload_seconds=3600,
            eligible_worker_ids=(2,),
        ),
        create_task(
            operation_id=3,
            workload_seconds=3600,
            stage_start=2,
            stage_end=2,
            eligible_worker_ids=(1,),
        ),
    )
    output = calculate(
        orders=(create_order(1, stage_count=2, tasks=tasks),),
        availability={(1, TODAY): 28_800, (2, TODAY): 28_800},
    )

    allocation_dates = {
        allocation.operation_id: allocation.work_date
        for allocation in output.allocations
    }
    assert allocation_dates == {1: TODAY, 2: TODAY, 3: TODAY}
    assert output.orders[0].resource_finish_date == TODAY


def test_planner_uses_only_one_worker_for_operation_per_day() -> None:
    """
    Проверяем последовательное выполнение операции доступными сотрудниками:
    - не складывать доступность двух исполнителей в один день
    - перенести незавершённую операцию на следующий день
    - разрешить замену исполнителя на следующий день без новой подготовки
    """
    tomorrow = TODAY + timedelta(days=1)
    task = create_task(
        operation_id=1,
        workload_seconds=36_000,
        eligible_worker_ids=(1, 2),
    )
    output = calculate(
        orders=(create_order(1, tasks=(task,)),),
        availability={
            (1, TODAY): 28_800,
            (2, TODAY): 28_800,
            (2, tomorrow): 28_800,
        },
    )

    first_day_allocations = [
        allocation
        for allocation in output.allocations
        if allocation.work_date == TODAY
    ]
    assert len(first_day_allocations) == 1
    assert first_day_allocations[0].user_id == 1
    assert output.operations[0].last_planned_date == tomorrow
    assert sum(
        allocation.preparation_seconds for allocation in output.allocations
    ) == 3600


def test_planner_respects_global_order_priority_for_shared_worker() -> None:
    """
    Проверяем конкуренцию заказов за одного сотрудника:
    - занять первый день заказом с более высоким приоритетом
    - перенести следующий заказ на следующий рабочий день
    """
    tomorrow = TODAY + timedelta(days=1)
    high_priority = create_order(
        1,
        priority_rank=1024,
        tasks=(
            create_task(
                operation_id=1,
                workload_seconds=25_200,
                eligible_worker_ids=(1,),
            ),
        ),
    )
    low_priority = create_order(
        2,
        priority_rank=2048,
        tasks=(
            create_task(
                operation_id=2,
                workload_seconds=25_200,
                eligible_worker_ids=(1,),
            ),
        ),
    )
    output = calculate(
        orders=(low_priority, high_priority),
        availability={(1, TODAY): 28_800, (1, tomorrow): 28_800},
    )

    dates_by_order = {
        allocation.order_id: allocation.work_date
        for allocation in output.allocations
    }
    assert dates_by_order == {1: TODAY, 2: tomorrow}


def test_adjacent_operation_blocks_only_its_final_stage_barrier() -> None:
    """
    Проверяем непрерывную смежную операцию:
    - запустить её с первого этапа
    - не блокировать операции второго и третьего этапов
    - заблокировать четвёртый этап до завершения смежной операции
    """
    tomorrow = TODAY + timedelta(days=1)
    tasks = (
        create_task(
            operation_id=1,
            workload_seconds=54_000,
            stage_start=1,
            stage_end=3,
            eligible_worker_ids=(1,),
        ),
        create_task(
            operation_id=2,
            workload_seconds=3600,
            stage_start=2,
            stage_end=2,
            eligible_worker_ids=(2,),
        ),
        create_task(
            operation_id=3,
            workload_seconds=3600,
            stage_start=3,
            stage_end=3,
            eligible_worker_ids=(2,),
        ),
        create_task(
            operation_id=4,
            workload_seconds=3600,
            stage_start=4,
            stage_end=4,
            eligible_worker_ids=(2,),
        ),
    )
    output = calculate(
        orders=(create_order(1, stage_count=4, tasks=tasks),),
        availability={
            (1, TODAY): 28_800,
            (1, tomorrow): 28_800,
            (2, TODAY): 28_800,
            (2, tomorrow): 28_800,
        },
    )
    dates = {
        result.operation_id: result.last_planned_date
        for result in output.operations
    }

    assert dates[1] == tomorrow
    assert dates[2] == TODAY
    assert dates[3] == TODAY
    assert dates[4] == tomorrow


def test_planner_reports_missing_schedule() -> None:
    """
    Проверяем диагностируемое отсутствие прогноза:
    - сохранить назначение и навык
    - не выдумывать доступность при пустом графике
    - вернуть код причины отсутствия графика
    """
    task = create_task(
        operation_id=1,
        workload_seconds=3600,
        eligible_worker_ids=(1,),
    )
    output = calculate(
        orders=(create_order(1, tasks=(task,)),),
        availability={},
    )

    assert output.orders[0].calculated_finish_date is None
    assert output.orders[0].issue_codes == ("no_schedule",)
    assert output.operations[0].issue_codes == ("no_schedule",)


def test_planner_worker_publishes_versioned_empty_snapshot(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем жизненный цикл фонового запуска:
    - создать запрошенную ревизию при отсутствии состояния
    - опубликовать неизменяемый успешный снимок
    - не запускать повторный расчёт без новой ревизии
    """
    session = db_session()
    try:
        service = ProductionPlannerService(session)
        processed = service.run_once(
            datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
        )
        state = session.get(ProductionPlanningState, 1)
        assert state is not None
        assert processed is True
        assert state.active_run_id is not None
        assert state.calculation_status == "idle"
        run = session.get(PlanningRun, state.active_run_id)
        assert run is not None
        assert run.status == "completed"
        assert run.input_revision == 1
        assert service.run_once(
            datetime(2026, 11, 5, 10, 1, tzinfo=UTC)
        ) is False
    finally:
        session.close()


def test_planner_worker_requests_revision_for_outdated_time_estimates(
    db_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Проверяем применение новой версии статистического алгоритма:
    - опубликовать текущую ревизию и перейти в ожидание
    - обнаружить сохранённые оценки предыдущей версии
    - запросить и опубликовать новую ревизию без ручного запуска
    """
    session = db_session()
    try:
        service = ProductionPlannerService(session)
        assert service.run_once(
            datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
        ) is True
        monkeypatch.setattr(
            OperationTimeEstimateService,
            "has_outdated_estimates",
            lambda _service: True,
        )

        assert service.run_once(
            datetime(2026, 11, 5, 10, 1, tzinfo=UTC)
        ) is True

        state = session.get(ProductionPlanningState, 1)
        assert state is not None
        assert state.input_revision == 2
        assert state.requested_revision == 2
        assert state.calculation_status == "idle"
        assert session.query(PlanningRun).count() == 2
    finally:
        session.close()


def test_planning_failure_details_remain_internal(
    client: TestClient,
    db_session: sessionmaker[Session],
    monkeypatch,
) -> None:
    """
    Проверяем конфиденциальность ошибки фонового расчёта:
    - завершить расчёт исключением с техническими данными
    - сохранить только стабильный внутренний код ошибки
    - не возвращать код и детали через публичный статус
    """
    session = db_session()

    def fail_snapshot(_builder, _calculation_time):
        raise RuntimeError("SELECT secret FROM internal_table")

    monkeypatch.setattr(PlanningSnapshotBuilder, "build", fail_snapshot)
    try:
        with pytest.raises(RuntimeError, match="internal_table"):
            ProductionPlannerService(session).run_once(
                datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
            )
        failed_run = session.query(PlanningRun).one()
        assert failed_run.status == "failed"
        assert failed_run.error_code == "calculation_failed"
        assert failed_run.error_details is None
    finally:
        session.close()

    response = client.get("/api/planning/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["calculation_status"] == "error"
    assert "error_code" not in payload
    assert "error_details" not in payload


def test_planner_worker_waits_for_new_revision_after_failure(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем остановку автоматических повторов ошибочной ревизии:
    - не запускать ту же ревизию после завершения с ошибкой
    - разрешить запуск после явного запроса нового пересчёта
    """
    session = db_session()
    now = int(datetime(2026, 11, 5, 10, 0, tzinfo=UTC).timestamp() * 1000)
    try:
        failed_run = PlanningRun(
            input_revision=1,
            algorithm_version="resource-v1",
            horizon_months=1,
            status="failed",
            started_at=now - 1000,
            completed_at=now,
            error_code="RuntimeError",
            error_details="test failure",
        )
        session.add(failed_run)
        session.add(
            ProductionPlanningState(
                id=1,
                input_revision=1,
                requested_revision=1,
                active_run_id=None,
                calculation_status="error",
                running_revision=None,
                worker_heartbeat_at=None,
                updated_at=now,
            )
        )
        session.commit()

        service = ProductionPlannerService(session)
        assert service.run_once(
            datetime(2026, 11, 5, 10, 1, tzinfo=UTC)
        ) is False
        assert session.query(PlanningRun).count() == 1

        PlanningRevisionService(session).request_recalculation()
        session.commit()
        assert service.run_once(
            datetime(2026, 11, 5, 10, 2, tzinfo=UTC)
        ) is True
        assert session.query(PlanningRun).count() == 2
        state = session.get(ProductionPlanningState, 1)
        assert state is not None
        assert state.calculation_status == "idle"
        assert state.input_revision == 2
    finally:
        session.close()


def test_planner_worker_replaces_timed_out_run(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем восстановление после остановки worker:
    - завершить просроченный запуск с диагностикой тайм-аута
    - запустить и опубликовать новый расчёт той же ревизии
    """
    session = db_session()
    now = int(datetime(2026, 11, 5, 10, 0, tzinfo=UTC).timestamp() * 1000)
    try:
        stale_run = PlanningRun(
            input_revision=1,
            algorithm_version="resource-v1",
            horizon_months=1,
            status="running",
            started_at=now - WORKER_STALE_AFTER_MS - 1000,
            completed_at=None,
            error_code=None,
            error_details=None,
        )
        session.add(stale_run)
        session.flush()
        session.add(
            ProductionPlanningState(
                id=1,
                input_revision=1,
                requested_revision=1,
                active_run_id=None,
                calculation_status="running",
                running_revision=1,
                worker_heartbeat_at=now - WORKER_STALE_AFTER_MS - 1,
                updated_at=now - WORKER_STALE_AFTER_MS - 1,
            )
        )
        session.commit()

        assert ProductionPlannerService(session).run_once(
            datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
        ) is True
        session.refresh(stale_run)
        assert stale_run.status == "failed"
        assert stale_run.error_code == "worker_timeout"
        runs = session.query(PlanningRun).order_by(PlanningRun.id).all()
        assert len(runs) == 2
        assert runs[1].status == "completed"
        state = session.get(ProductionPlanningState, 1)
        assert state is not None
        assert state.active_run_id == runs[1].id
        assert state.calculation_status == "idle"
    finally:
        session.close()


def test_planner_worker_uses_union_of_historical_operation_intervals(
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем интеграцию входного снимка с фактическим временем:
    - объединить пересекающиеся интервалы разных исполнителей одной операции
    - вычесть объединённые 900 секунд из норматива 1000 секунд
    - опубликовать оставшиеся 100 секунд без повторной подготовки
    """
    calculation_time = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
    session = db_session()
    try:
        catalog_entry = OperationCatalogEntry(
            name="Операция интеграции",
            operation_kind="regular",
            is_active=True,
            created_at=1,
            updated_at=1,
        )
        product = Product(
            name="Изделие планировщика",
            version="1.0",
            comment=None,
            author="Test Admin",
            author_user_id=1,
            material_cost_cents=None,
            stage_count=1,
            is_active=True,
            created_at=1,
        )
        workers = [
            User(
                name=f"Исполнитель {index}",
                phone=f"+7999000080{index}",
                password_hash=None,
                roles=["worker"],
                is_active=True,
                created_at=index + 1,
                updated_at=index + 1,
                deleted_at=None,
                author_user_id=1,
            )
            for index in (1, 2)
        ]
        session.add_all([catalog_entry, product, *workers])
        session.flush()
        operation = Operation(
            product_id=product.id,
            parent_id=None,
            operation_catalog_entry_id=catalog_entry.id,
            name=catalog_entry.name,
            price_cents=None,
            standard_time_seconds=1000,
            stage_start=1,
            stage_end=1,
            sort_order=0,
        )
        order = WorkOrder(
            order_number="PLAN-1",
            product_id=product.id,
            leather_type_id=None,
            quantity=1,
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
            quality_control_at=None,
            defect_quantity=0,
            completed_at=None,
            deleted_at=None,
            planning_priority_rank=1024,
            planning_excluded_at=None,
        )
        session.add_all([operation, order])
        session.flush()
        session.add_all(
            [
                UserOperationSkill(
                    user_id=worker.id,
                    operation_catalog_entry_id=catalog_entry.id,
                    created_at=1,
                    created_by_user_id=1,
                )
                for worker in workers
            ]
            + [
                UserWorkScheduleDay(
                    user_id=worker.id,
                    work_date=TODAY,
                    available_seconds=28_800,
                    updated_at=1,
                    updated_by_user_id=1,
                )
                for worker in workers
            ]
            + [
                WorkOrderAssignment(
                    work_order_id=order.id,
                    operation_id=operation.id,
                    worker_user_id=worker.id,
                )
                for worker in workers
            ]
        )
        starts = [
            datetime(2026, 11, 5, 9, 0, tzinfo=UTC),
            datetime(2026, 11, 5, 9, 5, tzinfo=UTC),
        ]
        ends = [
            datetime(2026, 11, 5, 9, 10, tzinfo=UTC),
            datetime(2026, 11, 5, 9, 15, tzinfo=UTC),
        ]
        for worker, started_at, ended_at in zip(
            workers,
            starts,
            ends,
            strict=True,
        ):
            start_ts = int(started_at.timestamp() * 1000)
            end_ts = int(ended_at.timestamp() * 1000)
            shift = WorkShift(
                user_id=worker.id,
                started_at=start_ts,
                ended_at=end_ts,
                business_date=TODAY.isoformat(),
                created_at=start_ts,
            )
            session.add(shift)
            session.flush()
            session.add(
                TimerSession(
                    shift_id=shift.id,
                    user_id=worker.id,
                    timer_type_code=2,
                    order_id=order.id,
                    operation_id=operation.id,
                    started_at=start_ts,
                    ended_at=end_ts,
                    created_at=start_ts,
                    updated_at=end_ts,
                    deleted_at=None,
                    deleted_by_user_id=None,
                )
            )
        session.add(
            PlanningSettings(
                id=1,
                display_offset_days=2,
                preparation_seconds=3600,
                horizon_months=1,
                updated_at=1,
                updated_by_user_id=1,
            )
        )
        session.commit()

        assert ProductionPlannerService(session).run_once(calculation_time) is True
        state = session.get(ProductionPlanningState, 1)
        assert state is not None
        assert state.active_run_id is not None
        operation_result = session.query(PlanningOperationResult).filter_by(
            run_id=state.active_run_id,
            order_id=order.id,
            operation_id=operation.id,
        ).one()
        allocations = session.query(PlanningWorkerDayAllocation).filter_by(
            run_id=state.active_run_id,
            order_id=order.id,
            operation_id=operation.id,
        ).all()
        assert operation_result.actual_seconds == 900
        assert operation_result.remaining_seconds == 100
        assert operation_result.preparation_seconds == 0
        assert sum(item.work_seconds for item in allocations) == 100
    finally:
        session.close()


def test_planning_status_keeps_previous_snapshot_while_update_is_pending(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем версионный статус пересчёта:
    - запросить расчёт при изменении настроек
    - опубликовать первый снимок фоновым worker
    - сохранить прошлый снимок и пометить его устаревшим после нового изменения
    """
    initial_status = client.get("/api/planning/status")
    assert initial_status.status_code == 200
    assert initial_status.json()["active_run_id"] is None

    update_response = client.patch(
        "/api/planning/settings",
        json={
            "display_offset_days": 2,
            "preparation_seconds": 3600,
            "horizon_months": 1,
        },
    )
    assert update_response.status_code == 200
    pending_status = client.get("/api/planning/status").json()
    assert pending_status["calculation_status"] == "pending"
    assert pending_status["input_revision"] == 1

    session = db_session()
    try:
        assert ProductionPlannerService(session).run_once(
            datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
        ) is True
    finally:
        session.close()

    published_status = client.get("/api/planning/status").json()
    assert published_status["calculation_status"] == "idle"
    assert published_status["active_revision"] == 1
    assert published_status["is_stale"] is False

    second_update = client.patch(
        "/api/planning/settings",
        json={
            "display_offset_days": 3,
            "preparation_seconds": 3600,
            "horizon_months": 1,
        },
    )
    assert second_update.status_code == 200
    stale_status = client.get("/api/planning/status").json()
    assert stale_status["calculation_status"] == "pending"
    assert stale_status["active_revision"] == 1
    assert stale_status["input_revision"] == 2
    assert stale_status["is_stale"] is True
    assert client.get("/api/planning/results/orders").json() == []


def test_planning_result_api_returns_forecast_detail_and_month_workload(
    client: TestClient,
    db_session: sessionmaker[Session],
) -> None:
    """
    Проверяем публичный контракт опубликованного снимка:
    - вернуть расчётную дату и этап операции из опубликованного снимка
    - сгруппировать месячное распределение и остаток по операции
    - передать дефицит незапланированной части
    """
    session = db_session()
    try:
        product = Product(
            name="Изделие для API",
            version="1.0",
            comment=None,
            author="Test Admin",
            author_user_id=1,
            material_cost_cents=None,
            stage_count=1,
            is_active=True,
            created_at=1,
        )
        worker = User(
            name="Исполнитель API",
            phone="+79990000991",
            password_hash=None,
            roles=["worker"],
            is_active=True,
            created_at=2,
            updated_at=2,
            deleted_at=None,
            author_user_id=1,
        )
        session.add_all([product, worker])
        session.flush()
        operation = Operation(
            product_id=product.id,
            parent_id=None,
            operation_catalog_entry_id=None,
            name="Пошив API",
            price_cents=None,
            standard_time_seconds=7200,
            stage_start=1,
            stage_end=1,
            sort_order=0,
        )
        order = WorkOrder(
            order_number="PLAN-API-1",
            product_id=product.id,
            leather_type_id=None,
            quantity=1,
            planned_completion_date=date(2026, 11, 20),
            estimated_minutes=0,
            total_spent_seconds=0,
            cutting_spent_seconds=0,
            production_stage="created",
            created_at=1,
            updated_at=1,
            cutting_started_at=None,
            sewing_started_at=None,
            taken_at=None,
            quality_control_at=None,
            defect_quantity=0,
            completed_at=None,
            deleted_at=None,
            planning_priority_rank=1024,
            planning_excluded_at=None,
        )
        run = PlanningRun(
            input_revision=3,
            algorithm_version="resource-v1",
            horizon_months=1,
            status="completed",
            started_at=1000,
            completed_at=2000,
            error_code=None,
            error_details=None,
        )
        session.add_all([operation, order, run])
        session.flush()
        session.add_all(
            [
                ProductionPlanningState(
                    id=1,
                    input_revision=3,
                    requested_revision=3,
                    active_run_id=run.id,
                    calculation_status="idle",
                    running_revision=None,
                    worker_heartbeat_at=None,
                    updated_at=2000,
                ),
                PlanningOrderResult(
                    run_id=run.id,
                    order_id=order.id,
                    resource_finish_date=None,
                    calculated_finish_date=None,
                    status="unplanned",
                    issue_codes=["outside_horizon"],
                ),
                PlanningOperationResult(
                    run_id=run.id,
                    order_id=order.id,
                    operation_id=operation.id,
                    stage_start=1,
                    stage_end=1,
                    workload_seconds=7200,
                    actual_seconds=1200,
                    remaining_seconds=6000,
                    preparation_seconds=3600,
                    first_planned_date=date(2026, 11, 5),
                    last_planned_date=None,
                    status="unplanned",
                    issue_codes=["outside_horizon"],
                ),
                PlanningWorkerDayAllocation(
                    run_id=run.id,
                    user_id=worker.id,
                    work_date=date(2026, 11, 5),
                    order_id=order.id,
                    operation_id=operation.id,
                    work_seconds=2400,
                    preparation_seconds=3600,
                ),
            ]
        )
        session.commit()
        operation.stage_start = 2
        operation.stage_end = 2
        session.commit()

        order_results = client.get("/api/planning/results/orders")
        assert order_results.status_code == 200
        assert order_results.json() == [
            {
                "order_id": order.id,
                "order_number": "PLAN-API-1",
                "product_name": "Изделие для API",
                "manual_completion_date": "2026-11-20",
                "resource_finish_date": None,
                "calculated_finish_date": None,
                "status": "unplanned",
                "issue_codes": ["outside_horizon"],
            }
        ]

        detail = client.get(f"/api/planning/results/orders/{order.id}")
        assert detail.status_code == 200
        detail_payload = detail.json()
        assert detail_payload["operations"][0]["stage_start"] == 1
        assert detail_payload["operations"][0]["stage_end"] == 1
        assert detail_payload["operations"][0]["remaining_seconds"] == 6000
        assert detail_payload["allocations"][0] == {
            "user_id": worker.id,
            "user_name": "Исполнитель API",
            "work_date": "2026-11-05",
            "operation_id": operation.id,
            "work_seconds": 2400,
            "preparation_seconds": 3600,
        }

        workload = client.get("/api/planning/workload?month=2026-11")
        assert workload.status_code == 200
        assert workload.json()["items"] == [
            {
                "operation_catalog_entry_id": None,
                "operation_name": "Пошив API",
                "planned_seconds": 6000,
                "remaining_seconds": 9600,
                "orders_count": 1,
                "deficit_seconds": 3600,
            }
        ]
    finally:
        session.close()


def test_planner_does_not_publish_snapshot_for_changed_input_revision(
    db_session: sessionmaker[Session],
    monkeypatch,
) -> None:
    """
    Проверяем атомарную публикацию снимка:
    - изменить входную ревизию после чтения исходных данных
    - пометить рассчитанный запуск устаревшим
    - не переключать активный снимок на устаревший результат
    """
    session = db_session()
    original_calculate = ProductionPlanningCalculator.calculate

    def calculate_and_change_revision(calculator, planning_input, progress_callback):
        output = original_calculate(
            calculator,
            planning_input,
            progress_callback,
        )
        PlanningRevisionService(session).request_recalculation()
        session.commit()
        return output

    monkeypatch.setattr(
        ProductionPlanningCalculator,
        "calculate",
        calculate_and_change_revision,
    )
    try:
        assert ProductionPlannerService(session).run_once(
            datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
        ) is True
        state = session.get(ProductionPlanningState, 1)
        assert state is not None
        assert state.active_run_id is None
        assert state.calculation_status == "pending"
        run = session.query(PlanningRun).one()
        assert run.status == "stale"
        assert run.input_revision == 1
        assert state.input_revision == 2
    finally:
        session.close()


def calculate(
    *,
    orders: tuple[PlanningOrderInput, ...],
    availability: dict[tuple[int, date], int],
):
    return ProductionPlanningCalculator().calculate(
        PlanningInput(
            today=TODAY,
            horizon_end=TODAY + timedelta(days=30),
            display_offset_days=2,
            preparation_seconds=3600,
            orders=orders,
            worker_availability=availability,
        )
    )


def create_order(
    order_id: int,
    *,
    priority_rank: int = 1024,
    stage_count: int = 1,
    tasks: tuple[PlanningTaskInput, ...],
) -> PlanningOrderInput:
    return PlanningOrderInput(
        order_id=order_id,
        priority_rank=priority_rank,
        stage_count=stage_count,
        is_quality_control=False,
        tasks=tasks,
    )


def create_task(
    *,
    operation_id: int,
    workload_seconds: int,
    actual_seconds: int = 0,
    stage_start: int = 1,
    stage_end: int = 1,
    eligible_worker_ids: tuple[int, ...],
) -> PlanningTaskInput:
    return PlanningTaskInput(
        operation_id=operation_id,
        operation_name=f"Операция {operation_id}",
        stage_start=stage_start,
        stage_end=stage_end,
        workload_seconds=workload_seconds,
        actual_seconds=actual_seconds,
        eligible_worker_ids=eligible_worker_ids,
    )

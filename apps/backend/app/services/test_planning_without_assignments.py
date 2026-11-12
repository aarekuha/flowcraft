from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.production_planning import ProductionPlanningCalculator
from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.planning import (
    PlanningRun,
    ProductionPlanningState,
    UserWorkScheduleDay,
)
from app.models.product import Product
from app.models.user import User
from app.models.user_operation_skill import UserOperationSkill
from app.models.work_order import (
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderAssignmentWorkerState,
)
from app.services.production_planner_service import (
    PlanningSnapshotBuilder,
    ProductionPlannerService,
)

NOW = datetime(2026, 11, 12, tzinfo=UTC)


@pytest.fixture()
def planning_session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Product(id=1, name="Изделие", version="1", author="Admin", created_at=1)
        )
        session.add(
            OperationCatalogEntry(
                id=1,
                name="Пошив",
                operation_kind="regular",
                is_active=True,
                created_at=1,
                updated_at=1,
            )
        )
        for user_id in range(1, 7):
            session.add(
                User(
                    id=user_id,
                    name=f"Сотрудник {user_id}",
                    phone=str(user_id),
                    roles=["worker"] if user_id != 5 else ["admin"],
                    is_active=user_id != 3,
                    deleted_at=1 if user_id == 4 else None,
                    created_at=1,
                    updated_at=1,
                )
            )
        session.flush()
        session.add(
            Operation(
                id=1,
                product_id=1,
                operation_catalog_entry_id=1,
                name="Пошив",
                standard_time_seconds=3600,
            )
        )
        session.add(
            WorkOrder(
                id=1,
                order_number="100",
                product_id=1,
                quantity=10,
                created_at=1,
                updated_at=1,
                planning_priority_rank=1,
            )
        )
        for user_id in range(1, 7):
            if user_id != 6:
                session.add(
                    UserOperationSkill(
                        user_id=user_id, operation_catalog_entry_id=1, created_at=1,
                    )
                )
            for offset in (0, 1):
                session.add(
                    UserWorkScheduleDay(
                        user_id=user_id,
                        work_date=NOW.date() + timedelta(days=offset),
                        available_seconds=28800,
                        updated_at=1,
                    )
                )
        session.commit()
        yield session
    engine.dispose()


@pytest.mark.parametrize("assigned", [(), (1,), (1, 2), (3,), (6,)])
def test_assignments_do_not_change_forecast(
    planning_session: Session,
    assigned: tuple[int, ...],
) -> None:
    """
    Проверяем прогноз независимо от назначений:
    - сравнить заказ без назначений и с разными назначенными сотрудниками
    - использовать активных сотрудников с навыком без одновременной работы над операцией
    - сохранить назначения без автоматической замены
    """
    session = planning_session
    builder = PlanningSnapshotBuilder(session)
    baseline = builder.build(NOW)
    for user_id in assigned:
        assignment = WorkOrderAssignment(
            work_order_id=1, operation_id=1, worker_user_id=user_id
        )
        session.add(assignment)
        session.flush()
        session.add(
            WorkOrderAssignmentWorkerState(
                assignment_id=assignment.id,
                worker_user_id=user_id,
                hidden_at=1,
                completed_at=1,
                created_at=1,
                updated_at=1,
            )
        )
    session.commit()
    snapshot = builder.build(NOW)
    assert snapshot == baseline
    result = ProductionPlanningCalculator().calculate(snapshot)
    assert snapshot.orders[0].tasks[0].eligible_worker_ids == (1, 2)
    assert result.orders[0].resource_finish_date == NOW.date() + timedelta(days=1)
    assert sum(item.work_seconds for item in result.allocations) == 36000
    assert (
        len([item for item in result.allocations if item.work_date == NOW.date()]) == 1
    )
    assert (
        tuple(
            session.scalars(
                select(WorkOrderAssignment.worker_user_id).order_by(
                    WorkOrderAssignment.worker_user_id
                )
            )
        )
        == assigned
    )


def test_missing_skill_prevents_forecast(planning_session: Session) -> None:
    """
    Проверяем отсутствие подходящих сотрудников:
    - удалить навыки активных исполнителей
    - вернуть понятную причину отсутствия прогноза вместо ошибки назначения
    """
    session = planning_session
    for skill in session.scalars(select(UserOperationSkill)):
        session.delete(skill)
    session.commit()
    result = ProductionPlanningCalculator().calculate(
        PlanningSnapshotBuilder(session).build(NOW)
    )
    assert result.orders[0].resource_finish_date is None
    assert result.operations[0].issue_codes == ("no_skilled_worker",)


def test_new_algorithm_recalculates_once(planning_session: Session) -> None:
    """
    Проверяем автоматическое обновление опубликованного прогноза:
    - пометить предыдущий успешный расчёт старой версией алгоритма
    - пересчитать без изменения заказа и назначений
    - не повторять расчёт после публикации актуальной версии
    """
    session = planning_session
    service = ProductionPlannerService(session)
    assert service.run_once(NOW)
    state = session.get(ProductionPlanningState, 1)
    assert state is not None
    previous_id = state.active_run_id
    previous = session.get(PlanningRun, previous_id)
    assert previous is not None
    previous.algorithm_version = "resource-v1"
    session.commit()
    assert service.run_once(NOW + timedelta(minutes=1))
    session.refresh(state)
    assert state.active_run_id != previous_id
    assert not service.run_once(NOW + timedelta(minutes=2))

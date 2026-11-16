# ruff: noqa: F811, I001
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.operation import Operation
from app.models.planning import PlanningOperationResult
from app.models.work_order import WorkOrder
from app.services.planning_timeline_service import PlanningTimelineService
from app.services.production_planner_service import ProductionPlannerService
from app.services.test_planning_without_assignments import NOW, planning_session  # noqa: F401

from app.models.planning import PlanningWorkerDayAllocation
from app.models.work_order import WorkOrderAssignment
from app.models.leather_type import LeatherType


def test_empty_timeline_before_calculation(planning_session: Session) -> None:
    """
    Проверяем отсутствие опубликованного расчёта:
    - получить пустой график без запуска планировщика
    - вернуть отсутствие активного расчёта
    """
    result = PlanningTimelineService(planning_session).get_timeline()
    assert result.items == []
    assert result.calculation.active_run_id is None


def test_timeline_uses_published_dates_and_catalog_name(
    planning_session: Session,
) -> None:
    """
    Проверяем даты и группировку опубликованного прогноза:
    - рассчитать операцию на два дня без назначений
    - вернуть имя справочника, заказ и границы операции
    - сохранить опубликованные даты после изменения норматива
    """
    assert ProductionPlannerService(planning_session).run_once(NOW)
    operation = planning_session.get(Operation, 1)
    operation.name = "Старое имя"
    operation.standard_time_seconds = 7200
    planning_session.commit()
    result = PlanningTimelineService(planning_session).get_timeline()
    assert len(result.items) == 1
    item = result.items[0]
    assert item.order_number == "100"
    assert item.operation_name == "Пошив"
    assert item.operation_catalog_entry_id == 1
    assert item.first_planned_date == NOW.date()
    assert item.last_planned_date == NOW.date() + timedelta(days=1)


@pytest.mark.parametrize("field", ["deleted_at", "completed_at"])
def test_timeline_excludes_archived_orders(
    planning_session: Session, field: str,
) -> None:
    """
    Проверяем актуальный состав заказов при старом прогнозе:
    - выполнить или удалить заказ после расчёта
    - исключить его блоки из текущего графика
    """
    assert ProductionPlannerService(planning_session).run_once(NOW)
    setattr(planning_session.get(WorkOrder, 1), field, 1)
    planning_session.commit()
    assert PlanningTimelineService(planning_session).get_timeline().items == []


def test_timeline_preserves_unscheduled_operations(planning_session: Session) -> None:
    """
    Проверяем отсутствие рассчитанных дат:
    - сохранить результат с причиной невозможности планирования
    - вернуть операцию и причину без вымышленных дат
    """
    assert ProductionPlannerService(planning_session).run_once(NOW)
    result = planning_session.scalar(select(PlanningOperationResult))
    result.first_planned_date = None
    result.last_planned_date = None
    result.status = "unplanned"
    result.issue_codes = ["outside_horizon"]
    planning_session.commit()
    item = PlanningTimelineService(planning_session).get_timeline().items[0]
    assert item.first_planned_date is None
    assert item.last_planned_date is None
    assert item.issue_codes == ["outside_horizon"]


def test_day_uses_allocations_and_current_assignments(
    planning_session: Session,
) -> None:
    """
    Проверяем дневной список и назначения:
    - объединить распределения разных ресурсов в одну строку операции
    - показать назначенных исполнителей, кожу и полное количество заказа
    - исключить день без распределений внутри интервала операции
    """
    assert ProductionPlannerService(planning_session).run_once(NOW)
    allocations = planning_session.scalars(select(PlanningWorkerDayAllocation)).all()
    for allocation in allocations:
        if allocation.work_date > NOW.date():
            allocation.work_date += timedelta(days=1)
    first = allocations[0]
    planning_session.add(PlanningWorkerDayAllocation(
        run_id=first.run_id, user_id=6, work_date=NOW.date(),
        order_id=1, operation_id=1, work_seconds=60, preparation_seconds=0,
    ))
    planning_session.add(LeatherType(id=1, name="Флотер", created_at=1, updated_at=1))
    planning_session.flush()
    planning_session.get(WorkOrder, 1).leather_type_id = 1
    planning_session.add_all([
        WorkOrderAssignment(work_order_id=1, operation_id=1, worker_user_id=user_id)
        for user_id in (3, 4)
    ])
    planning_session.commit()
    service = PlanningTimelineService(planning_session)
    result = service.get_day(NOW.date())
    assert len(result.items) == 1
    item = result.items[0]
    assert item.order_number == "100"
    assert item.quantity == 10
    assert item.leather_type_name == "Флотер"
    assert item.operation_name == "Пошив"
    assert item.worker_names == ["Сотрудник 3", "Сотрудник 4"]
    assert service.get_day(NOW.date() + timedelta(days=1)).items == []


def test_day_includes_preparation_without_assignments(
    planning_session: Session,
) -> None:
    """
    Проверяем подготовку и отсутствие назначений:
    - включить день только с подготовкой без вымышленного исполнителя
    - исключить распределения с нулевым временем
    """
    assert ProductionPlannerService(planning_session).run_once(NOW)
    for allocation in planning_session.scalars(select(PlanningWorkerDayAllocation)):
        allocation.work_seconds = 0
        allocation.preparation_seconds = 60 if allocation.work_date == NOW.date() else 0
    planning_session.commit()
    service = PlanningTimelineService(planning_session)
    assert service.get_day(NOW.date()).items[0].worker_names == []
    assert service.get_day(NOW.date() + timedelta(days=1)).items == []


@pytest.mark.parametrize("field", ["deleted_at", "completed_at"])
def test_day_excludes_archived_orders(planning_session: Session, field: str) -> None:
    """
    Проверяем дневной список после архивирования:
    - исключить выполненный или удалённый заказ из опубликованного плана
    """
    assert ProductionPlannerService(planning_session).run_once(NOW)
    setattr(planning_session.get(WorkOrder, 1), field, 1)
    planning_session.commit()
    assert PlanningTimelineService(planning_session).get_day(NOW.date()).items == []


def test_day_before_publication_is_empty(planning_session: Session) -> None:
    """
    Проверяем отсутствие расчёта:
    - вернуть пустой список с выбранной датой без запуска планирования
    """
    result = PlanningTimelineService(planning_session).get_day(NOW.date())
    assert result.items == []
    assert result.work_date == NOW.date()
    assert result.calculation.active_run_id is None

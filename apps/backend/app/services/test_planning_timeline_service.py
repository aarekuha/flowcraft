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

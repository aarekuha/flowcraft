# ruff: noqa: F811, I001

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.work_order import WorkOrder
from app.schemas.order import (
    WorkOrderDeletedStatusUpdate,
    WorkOrderQualityControlAccept,
)
from app.services.order_service import OrderService
from app.services.planning_results_service import PlanningResultsService
from app.services.production_planner_service import ProductionPlannerService
from app.services.test_planning_without_assignments import NOW, planning_session  # noqa: F401


@pytest.mark.parametrize("archived_status", ["completed", "deleted"])
def test_archived_order_preserves_last_published_finish_date(
    planning_session: Session,
    archived_status: str,
) -> None:
    """
    Проверяем фиксацию даты готовности:
    - рассчитать заказ и перенести в выполненные или удалённые
    - повторный расчёт исключает заказ из прогноза
    - API заказа продолжает возвращать зафиксированную дату
    """
    planner = ProductionPlannerService(planning_session)
    assert planner.run_once(NOW)
    orders = OrderService(planning_session)
    saved = orders.get_order(1).calculated_finish_date
    forecast = PlanningResultsService(planning_session).get_order_forecast(1)
    assert saved is not None
    assert saved == forecast.calculated_finish_date
    if archived_status == "completed":
        order = planning_session.get(WorkOrder, 1)
        assert order is not None
        order.production_stage = "in_work"
        order.quality_control_at = 1
        planning_session.commit()
        orders.accept_order_quality_control(1, WorkOrderQualityControlAccept())
    else:
        orders.update_order_deleted_status(
            1, WorkOrderDeletedStatusUpdate(is_deleted=True)
        )
    PlanningResultsService(planning_session).request_recalculation()
    assert planner.run_once(NOW + timedelta(days=10))
    assert PlanningResultsService(planning_session).list_order_forecasts() == []
    assert orders.get_order(1).calculated_finish_date == saved


def test_restored_order_updates_date_and_clears_unavailable_forecast(
    planning_session: Session,
) -> None:
    """
    Проверяем пересчёт восстановленного заказа:
    - удалить заказ с рассчитанной датой и восстановить
    - пересчитать за пределами заполненного графика
    - недоступный прогноз очищает прежнюю дату активного заказа
    """
    planner = ProductionPlannerService(planning_session)
    assert planner.run_once(NOW)
    orders = OrderService(planning_session)
    assert orders.get_order(1).calculated_finish_date is not None
    orders.update_order_deleted_status(1, WorkOrderDeletedStatusUpdate(is_deleted=True))
    orders.update_order_deleted_status(
        1, WorkOrderDeletedStatusUpdate(is_deleted=False)
    )
    PlanningResultsService(planning_session).request_recalculation()
    assert planner.run_once(NOW + timedelta(days=10))
    assert orders.get_order(1).calculated_finish_date is None

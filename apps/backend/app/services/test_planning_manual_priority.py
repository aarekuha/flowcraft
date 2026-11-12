# ruff: noqa: F811, I001

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.work_order import WorkOrder
from app.schemas.planning import PlanningQueueReorder
from app.services.planning_queue_service import PlanningQueueService
from app.services.planning_results_service import PlanningResultsService
from app.services.production_planner_service import (
    PlanningSnapshotBuilder,
    ProductionPlannerService,
)
from app.services.test_planning_without_assignments import NOW, planning_session  # noqa: F401


def reorder(session: Session) -> None:
    if session.get(WorkOrder, 2) is None:
        session.add(
            WorkOrder(
                id=2,
                order_number="200",
                product_id=1,
                quantity=10,
                created_at=1,
                updated_at=1,
                planning_priority_rank=2,
            )
        )
        session.commit()
    service = PlanningQueueService(session)
    queue = service.get_queue()
    service.reorder(
        PlanningQueueReorder(order_id=2, position=1, expected_revision=queue.revision),
        updated_by_user_id=1,
    )


def test_priority_waits_for_button_and_preserves_forecast(
    planning_session: Session,
) -> None:
    """
    Проверяем ручное обновление приоритетов:
    - изменить порядок после опубликованного расчёта
    - сохранить старый прогноз без фонового запуска
    - опубликовать новый порядок после явного пересчёта
    """
    session = planning_session
    planner = ProductionPlannerService(session)
    results = PlanningResultsService(session)
    assert planner.run_once(NOW)
    original = results.get_status().active_run_id
    forecasts = results.list_order_forecasts()
    reorder(session)
    status = results.get_status()
    assert status.is_stale
    assert status.active_run_id == original
    assert not planner.run_once(NOW + timedelta(minutes=1))
    assert results.list_order_forecasts() == forecasts
    results.request_recalculation()
    assert planner.run_once(NOW + timedelta(minutes=2))
    assert not results.get_status().is_stale
    assert results.get_status().active_run_id != original
    assert results.list_order_forecasts()[0].order_id == 2


def test_priority_before_first_forecast_waits_for_button(
    planning_session: Session,
) -> None:
    """
    Проверяем перестановку до первого расчёта:
    - сохранить порядок при отсутствии опубликованного прогноза
    - не запускать расчёт до явного запроса
    """
    reorder(planning_session)
    planner = ProductionPlannerService(planning_session)
    assert not planner.run_once(NOW)
    PlanningResultsService(planning_session).request_recalculation()
    assert planner.run_once(NOW + timedelta(minutes=1))


def test_priority_during_calculation_does_not_publish_old_order(
    planning_session: Session,
    monkeypatch,
) -> None:
    """
    Проверяем смену приоритета во время расчёта:
    - изменить очередь после получения исходных данных расчёта
    - не публиковать устаревший результат и не запускать повтор автоматически
    """
    original = PlanningSnapshotBuilder.build

    def build_and_reorder(builder, calculation_time):
        snapshot = original(builder, calculation_time)
        reorder(planning_session)
        return snapshot

    monkeypatch.setattr(PlanningSnapshotBuilder, "build", build_and_reorder)
    planner = ProductionPlannerService(planning_session)
    assert planner.run_once(NOW)
    status = PlanningResultsService(planning_session).get_status()
    assert status.active_run_id is None
    assert status.calculation_status == "idle"
    assert not planner.run_once(NOW + timedelta(minutes=1))

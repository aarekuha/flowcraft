from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_any_role
from app.schemas.planning import (
    PlanningOrderForecastDetailRead,
    PlanningOrderForecastRead,
    PlanningQueueRead,
    PlanningQueueReorder,
    PlanningSettingsRead,
    PlanningSettingsUpdate,
    PlanningWorkloadRead,
    ProductionPlanningStatusRead,
    WorkScheduleBatchDelete,
    WorkScheduleBatchUpdate,
    WorkScheduleMonthRead,
)
from app.schemas.production_calendar import CalendarStatusRead
from app.services.auth_service import AuthenticatedSession
from app.services.planning_queue_service import PlanningQueueService
from app.services.planning_results_service import PlanningResultsService
from app.services.planning_service import PlanningService
from app.services.production_calendar_service import ProductionCalendarService

router = APIRouter()


@router.get(
    "/status",
    response_model=ProductionPlanningStatusRead,
    summary="Get production planning calculation status",
)
def get_production_planning_status(
    _: object = Depends(require_any_role("brigadier", "admin")),
    session: Session = Depends(get_session),
) -> ProductionPlanningStatusRead:
    return PlanningResultsService(session).get_status()


@router.post(
    "/recalculate",
    response_model=ProductionPlanningStatusRead,
    summary="Request production planning recalculation",
)
def request_production_planning_recalculation(
    _: object = Depends(require_any_role("brigadier", "admin")),
    session: Session = Depends(get_session),
) -> ProductionPlanningStatusRead:
    return PlanningResultsService(session).request_recalculation()


@router.get(
    "/results/orders",
    response_model=list[PlanningOrderForecastRead],
    summary="Get active production planning order results",
)
def list_production_planning_order_results(
    _: object = Depends(require_any_role("brigadier", "admin")),
    session: Session = Depends(get_session),
) -> list[PlanningOrderForecastRead]:
    return PlanningResultsService(session).list_order_forecasts()


@router.get(
    "/results/orders/{order_id}",
    response_model=PlanningOrderForecastDetailRead,
    summary="Get active production planning order details",
)
def get_production_planning_order_result(
    order_id: int,
    _: object = Depends(require_any_role("brigadier", "admin")),
    session: Session = Depends(get_session),
) -> PlanningOrderForecastDetailRead:
    return PlanningResultsService(session).get_order_forecast(order_id)


@router.get(
    "/workload",
    response_model=PlanningWorkloadRead,
    summary="Get production planning workload by operation",
)
def get_production_planning_workload(
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    _: object = Depends(require_any_role("brigadier", "admin")),
    session: Session = Depends(get_session),
) -> PlanningWorkloadRead:
    return PlanningResultsService(session).get_workload(month)


@router.get(
    "/queue",
    response_model=PlanningQueueRead,
    summary="Get production planning priority queue",
)
def get_planning_queue(
    _: object = Depends(require_any_role("brigadier", "admin")),
    session: Session = Depends(get_session),
) -> PlanningQueueRead:
    return PlanningQueueService(session).get_queue()


@router.patch(
    "/queue",
    response_model=PlanningQueueRead,
    summary="Reorder the production planning priority queue",
)
def reorder_planning_queue(
    payload: PlanningQueueReorder,
    auth_session: AuthenticatedSession = Depends(
        require_any_role("brigadier", "admin")
    ),
    session: Session = Depends(get_session),
) -> PlanningQueueRead:
    return PlanningQueueService(session).reorder(
        payload,
        updated_by_user_id=auth_session.user_id,
    )


@router.get(
    "/settings",
    response_model=PlanningSettingsRead,
    summary="Get production planning settings",
)
def get_planning_settings(
    _: object = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> PlanningSettingsRead:
    return PlanningService(session).get_settings()


@router.patch(
    "/settings",
    response_model=PlanningSettingsRead,
    summary="Update production planning settings",
)
def update_planning_settings(
    payload: PlanningSettingsUpdate,
    auth_session: AuthenticatedSession = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> PlanningSettingsRead:
    return PlanningService(session).update_settings(
        payload,
        updated_by_user_id=auth_session.user_id,
    )


@router.get(
    "/work-schedule",
    response_model=WorkScheduleMonthRead,
    summary="Get monthly worker availability",
)
def get_work_schedule(
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    _: object = Depends(require_any_role("brigadier", "admin")),
    session: Session = Depends(get_session),
) -> WorkScheduleMonthRead:
    return PlanningService(session).get_work_schedule(month)


@router.put(
    "/work-schedule",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Create or update worker availability days",
)
def update_work_schedule(
    payload: WorkScheduleBatchUpdate | list[WorkScheduleBatchUpdate],
    auth_session: AuthenticatedSession = Depends(
        require_any_role("brigadier", "admin")
    ),
    session: Session = Depends(get_session),
) -> Response:
    PlanningService(session).update_work_schedule(
        payload,
        updated_by_user_id=auth_session.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/work-schedule",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete worker availability days",
)
def delete_work_schedule(
    payload: WorkScheduleBatchDelete | list[WorkScheduleBatchDelete],
    _: object = Depends(require_any_role("brigadier", "admin")),
    session: Session = Depends(get_session),
) -> Response:
    PlanningService(session).delete_work_schedule(payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/calendar", response_model=CalendarStatusRead)
def get_calendar_status(
    _: object = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> CalendarStatusRead:
    return ProductionCalendarService(session).get_status()


@router.post("/calendar/refresh", response_model=CalendarStatusRead)
def refresh_calendar(
    auth_session: AuthenticatedSession = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> CalendarStatusRead:
    return ProductionCalendarService(session).refresh(auth_session.user_id)

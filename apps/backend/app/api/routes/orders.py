from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_authenticated_session,
    get_session,
    require_any_role,
)
from app.schemas.order import (
    SortDirection,
    WorkerAssignedWorkOrderList,
    WorkOrderCreate,
    WorkOrderDeletedStatusUpdate,
    WorkOrderDetail,
    WorkOrderPage,
    WorkOrderQualityControlAccept,
    WorkOrderQualityControlStatusUpdate,
    WorkOrderSortField,
    WorkOrderStatusFilter,
    WorkOrderStatusUpdate,
    WorkOrderTakenStatusUpdate,
    WorkOrderTimeBreakdown,
    WorkOrderUpdateAssignments,
    WorkOrderVisibilityUpdate,
)
from app.services.auth_service import AuthenticatedSession
from app.services.order_service import OrderService

router = APIRouter()


@router.get("", response_model=WorkOrderPage, summary="List work orders")
def list_orders(
    search: str | None = Query(default=None, max_length=128),
    include_completed: bool = Query(default=False),
    status_filter: WorkOrderStatusFilter = Query(
        default=WorkOrderStatusFilter.IN_WORK,
        alias="status",
    ),
    sort_by: WorkOrderSortField = Query(default=WorkOrderSortField.CREATED),
    sort_direction: SortDirection = Query(default=SortDirection.DESC),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> WorkOrderPage:
    return OrderService(session).list_orders(
        search=search,
        include_completed=include_completed,
        status_filter=status_filter,
        sort_by=sort_by,
        sort_direction=sort_direction,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/worker-assignments",
    response_model=WorkerAssignedWorkOrderList,
    summary="List current worker assigned orders",
)
def list_worker_assignments(
    include_hidden: bool = Query(default=False),
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkerAssignedWorkOrderList:
    return OrderService(session).list_worker_assigned_orders(
        auth_session.user_id,
        include_hidden=include_hidden,
    )


@router.get("/{order_id}", response_model=WorkOrderDetail, summary="Get work order")
def get_order(
    order_id: int,
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).get_order(order_id)


@router.get(
    "/{order_id}/time-breakdown",
    response_model=WorkOrderTimeBreakdown,
    summary="Get work order time breakdown",
)
def get_order_time_breakdown(
    order_id: int,
    session: Session = Depends(get_session),
) -> WorkOrderTimeBreakdown:
    return OrderService(session).get_order_time_breakdown(order_id)


@router.post(
    "",
    response_model=WorkOrderDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create work order",
)
def create_order(
    payload: WorkOrderCreate,
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).create_order(payload)


@router.put(
    "/{order_id}/assignments",
    response_model=WorkOrderDetail,
    summary="Update work order assignments",
)
def update_order_assignments(
    order_id: int,
    payload: WorkOrderUpdateAssignments,
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).update_order_assignments(order_id, payload)


@router.patch(
    "/{order_id}/status",
    response_model=WorkOrderDetail,
    summary="Update work order status",
)
def update_order_status(
    order_id: int,
    payload: WorkOrderStatusUpdate,
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).update_order_status(order_id, payload)


@router.patch(
    "/{order_id}/quality-control-status",
    response_model=WorkOrderDetail,
    summary="Update work order quality control status",
)
def update_order_quality_control_status(
    order_id: int,
    payload: WorkOrderQualityControlStatusUpdate,
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).update_order_quality_control_status(
        order_id,
        payload,
    )


@router.patch(
    "/{order_id}/quality-control-acceptance",
    response_model=WorkOrderDetail,
    summary="Accept work order quality control",
)
def accept_order_quality_control(
    order_id: int,
    payload: WorkOrderQualityControlAccept,
    _auth_session: AuthenticatedSession = Depends(
        require_any_role("quality_control")
    ),
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).accept_order_quality_control(order_id, payload)


@router.patch(
    "/{order_id}/visibility",
    response_model=WorkOrderDetail,
    summary="Update current worker order visibility",
)
def update_order_visibility(
    order_id: int,
    payload: WorkOrderVisibilityUpdate,
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).update_worker_order_visibility(
        auth_session.user_id,
        order_id,
        payload,
    )


@router.patch(
    "/{order_id}/taken-status",
    response_model=WorkOrderDetail,
    summary="Update work order taken status",
)
def update_order_taken_status(
    order_id: int,
    payload: WorkOrderTakenStatusUpdate,
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).update_order_taken_status(order_id, payload)


@router.patch(
    "/{order_id}/deleted-status",
    response_model=WorkOrderDetail,
    summary="Update work order deleted status",
)
def update_order_deleted_status(
    order_id: int,
    payload: WorkOrderDeletedStatusUpdate,
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).update_order_deleted_status(order_id, payload)

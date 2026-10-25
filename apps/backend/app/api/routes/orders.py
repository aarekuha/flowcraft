from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_authenticated_session,
    get_session,
    require_any_role,
)
from app.schemas.order import (
    SortDirection,
    WorkerAssignmentStatusFilter,
    WorkOrderAssignmentWorkerStatusUpdate,
    WorkOrderCreate,
    WorkOrderDeletedStatusUpdate,
    WorkOrderDetail,
    WorkOrderMergeCandidate,
    WorkOrderMergeRequest,
    WorkOrderNumberSearchItem,
    WorkOrderPage,
    WorkOrderPlannedCompletionDateUpdate,
    WorkOrderProductionStageUpdate,
    WorkOrderQrTarget,
    WorkOrderQualityControlAccept,
    WorkOrderQualityControlStatusUpdate,
    WorkOrderSortField,
    WorkOrderSplitRequest,
    WorkOrderSplitResult,
    WorkOrderStatusFilter,
    WorkOrderStatusUpdate,
    WorkOrderTimeBreakdown,
    WorkOrderUpdateAssignments,
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
    "/order-number-search",
    response_model=list[WorkOrderNumberSearchItem],
    summary="Search work orders by number across all stages",
)
def search_orders_by_number(
    search: str = Query(min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[WorkOrderNumberSearchItem]:
    return OrderService(session).search_orders_by_number(
        search=search,
        limit=limit,
    )


@router.get(
    "/worker-assignments",
    response_model=list[WorkOrderDetail],
    summary="List current worker assigned orders",
)
def list_worker_assignments(
    worker_status: WorkerAssignmentStatusFilter = Query(
        default=WorkerAssignmentStatusFilter.IN_WORK,
        alias="status",
    ),
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> list[WorkOrderDetail]:
    return OrderService(session).list_worker_assigned_orders(
        auth_session.user_id,
        worker_status,
    )


@router.patch(
    "/worker-assignments/{assignment_id}/status",
    response_model=WorkOrderDetail,
    summary="Update current worker assignment status",
)
def update_worker_assignment_status(
    assignment_id: int,
    payload: WorkOrderAssignmentWorkerStatusUpdate,
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).update_worker_assignment_status(
        assignment_id=assignment_id,
        worker_user_id=auth_session.user_id,
        payload=payload,
    )


@router.get(
    "/worker-assignments/qr-target",
    response_model=WorkOrderQrTarget,
    summary="Resolve worker orders from QR reference",
)
def get_worker_qr_target(
    order_reference: str | None = Query(default=None, min_length=1, max_length=64),
    legacy_order_id: int | None = Query(default=None, ge=1),
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkOrderQrTarget:
    return OrderService(session).get_worker_orders_by_qr(
        worker_user_id=auth_session.user_id,
        order_reference=order_reference,
        legacy_order_id=legacy_order_id,
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
    "/{order_id}/split",
    response_model=WorkOrderSplitResult,
    status_code=status.HTTP_201_CREATED,
    summary="Split work order",
)
def split_order(
    order_id: int,
    payload: WorkOrderSplitRequest,
    _auth_session: AuthenticatedSession = Depends(require_any_role("brigadier")),
    session: Session = Depends(get_session),
) -> WorkOrderSplitResult:
    return OrderService(session).split_order(order_id, payload)


@router.get(
    "/{order_id}/merge-candidates",
    response_model=list[WorkOrderMergeCandidate],
    summary="List compatible work orders for merging",
)
def list_merge_candidates(
    order_id: int,
    search: str | None = Query(default=None, max_length=64),
    _auth_session: AuthenticatedSession = Depends(require_any_role("brigadier")),
    session: Session = Depends(get_session),
) -> list[WorkOrderMergeCandidate]:
    return OrderService(session).list_merge_candidates(order_id, search)


@router.post(
    "/{order_id}/merge",
    response_model=WorkOrderDetail,
    summary="Merge work orders",
)
def merge_orders(
    order_id: int,
    payload: WorkOrderMergeRequest,
    _auth_session: AuthenticatedSession = Depends(require_any_role("brigadier")),
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).merge_orders(order_id, payload)


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
    "/{order_id}/planned-completion-date",
    response_model=WorkOrderDetail,
    summary="Update work order planned completion date",
)
def update_order_planned_completion_date(
    order_id: int,
    payload: WorkOrderPlannedCompletionDateUpdate,
    _auth_session: AuthenticatedSession = Depends(
        require_any_role("brigadier", "quality_control")
    ),
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).update_order_planned_completion_date(
        order_id,
        payload,
    )


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
    _auth_session: AuthenticatedSession = Depends(require_any_role("quality_control")),
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).accept_order_quality_control(order_id, payload)


@router.patch(
    "/{order_id}/production-stage",
    response_model=WorkOrderDetail,
    summary="Update work order production stage",
)
def update_order_production_stage(
    order_id: int,
    payload: WorkOrderProductionStageUpdate,
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).update_order_production_stage(order_id, payload)


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

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.order import (
    SortDirection,
    WorkOrderCreate,
    WorkOrderDetail,
    WorkOrderPage,
    WorkOrderSortField,
    WorkOrderStatusUpdate,
    WorkOrderUpdateAssignments,
)
from app.services.order_service import OrderService

router = APIRouter()


@router.get("", response_model=WorkOrderPage, summary="List work orders")
def list_orders(
    search: str | None = Query(default=None, max_length=128),
    include_completed: bool = Query(default=False),
    sort_by: WorkOrderSortField = Query(default=WorkOrderSortField.CREATED),
    sort_direction: SortDirection = Query(default=SortDirection.DESC),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> WorkOrderPage:
    return OrderService(session).list_orders(
        search=search,
        include_completed=include_completed,
        sort_by=sort_by,
        sort_direction=sort_direction,
        page=page,
        page_size=page_size,
    )


@router.get("/{order_id}", response_model=WorkOrderDetail, summary="Get work order")
def get_order(
    order_id: int,
    session: Session = Depends(get_session),
) -> WorkOrderDetail:
    return OrderService(session).get_order(order_id)


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

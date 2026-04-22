from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.order import (
    WorkOrderCreate,
    WorkOrderDetail,
    WorkOrderListItem,
    WorkOrderUpdateAssignments,
)
from app.services.order_service import OrderService

router = APIRouter()


@router.get("", response_model=list[WorkOrderListItem], summary="List work orders")
def list_orders(session: Session = Depends(get_session)) -> list[WorkOrderListItem]:
    return OrderService(session).list_orders()


@router.get("/{order_id}", response_model=WorkOrderDetail, summary="Get work order")
def get_order(order_id: int, session: Session = Depends(get_session)) -> WorkOrderDetail:
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

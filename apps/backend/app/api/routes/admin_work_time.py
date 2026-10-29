from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_any_role
from app.schemas.admin_work_time import (
    AdminWorkTimeOperationRead,
    AdminWorkTimeOrderRead,
    AdminWorkTimeOverlapRead,
    AdminWorkTimeSessionCreate,
    AdminWorkTimeSessionRead,
    AdminWorkTimeSessionUpdate,
    AdminWorkTimeWorkerRead,
)
from app.services.admin_work_time_service import AdminWorkTimeService
from app.services.auth_service import AuthenticatedSession

router = APIRouter()


@router.get(
    "/workers",
    response_model=list[AdminWorkTimeWorkerRead],
    summary="List workers for admin work time editing",
)
def list_workers(
    include_inactive: bool = Query(default=False),
    _auth_session: AuthenticatedSession = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> list[AdminWorkTimeWorkerRead]:
    return AdminWorkTimeService(session).list_workers(
        include_inactive=include_inactive,
    )


@router.get(
    "/sessions",
    response_model=list[AdminWorkTimeSessionRead],
    summary="List worker time sessions",
)
def list_sessions(
    worker_user_id: int = Query(gt=0),
    from_ts: int = Query(ge=0),
    to_ts: int = Query(gt=0),
    _auth_session: AuthenticatedSession = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> list[AdminWorkTimeSessionRead]:
    return AdminWorkTimeService(session).list_sessions(
        worker_user_id=worker_user_id,
        period_start=from_ts,
        period_end=to_ts,
    )


@router.get(
    "/overlaps",
    response_model=list[AdminWorkTimeOverlapRead],
    summary="List overlapping work orders for an interval",
)
def list_overlaps(
    worker_user_id: int = Query(gt=0),
    order_id: int = Query(gt=0),
    started_at: int = Query(ge=0),
    ended_at: int = Query(gt=0),
    exclude_session_id: int | None = Query(default=None, gt=0),
    _auth_session: AuthenticatedSession = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> list[AdminWorkTimeOverlapRead]:
    return AdminWorkTimeService(session).list_cross_order_overlaps(
        worker_user_id=worker_user_id,
        order_id=order_id,
        started_at=started_at,
        ended_at=ended_at,
        exclude_session_id=exclude_session_id,
    )


@router.get(
    "/orders/search",
    response_model=list[AdminWorkTimeOrderRead],
    summary="Search work orders for manual time entry",
)
def search_orders(
    query: str = Query(min_length=1, max_length=128),
    limit: int = Query(default=20, ge=1, le=100),
    _auth_session: AuthenticatedSession = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> list[AdminWorkTimeOrderRead]:
    return AdminWorkTimeService(session).search_orders(
        query=query,
        limit=limit,
    )


@router.get(
    "/orders/{order_id}/operations",
    response_model=list[AdminWorkTimeOperationRead],
    summary="List work order operations for manual time entry",
)
def list_order_operations(
    order_id: int,
    _auth_session: AuthenticatedSession = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> list[AdminWorkTimeOperationRead]:
    return AdminWorkTimeService(session).list_order_operations(order_id)


@router.post(
    "/sessions",
    response_model=AdminWorkTimeSessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual operation time",
)
def create_session(
    payload: AdminWorkTimeSessionCreate,
    auth_session: AuthenticatedSession = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> AdminWorkTimeSessionRead:
    return AdminWorkTimeService(session).create_session(
        admin_user_id=auth_session.user_id,
        payload=payload,
    )


@router.patch(
    "/sessions/{session_id}",
    response_model=AdminWorkTimeSessionRead,
    summary="Update manual operation time",
)
def update_session(
    session_id: int,
    payload: AdminWorkTimeSessionUpdate,
    auth_session: AuthenticatedSession = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> AdminWorkTimeSessionRead:
    return AdminWorkTimeService(session).update_session(
        session_id=session_id,
        admin_user_id=auth_session.user_id,
        payload=payload,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete manual operation time",
)
def delete_session(
    session_id: int,
    expected_updated_at: int = Query(ge=0),
    auth_session: AuthenticatedSession = Depends(require_any_role("admin")),
    session: Session = Depends(get_session),
) -> Response:
    AdminWorkTimeService(session).delete_session(
        session_id=session_id,
        admin_user_id=auth_session.user_id,
        expected_updated_at=expected_updated_at,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from typing import Any

from sqlalchemy import Integer, case, exists, literal, select, union_all

from app.models.timer_session import TimerSession
from app.models.work_order import WorkOrderTimeAllocation
from app.schemas.timer import TimerType
from app.services.timer_service import TIMER_TYPE_TO_CODE


def build_effective_operation_order_links_subquery() -> Any:
    allocated_session_exists = exists(
        select(WorkOrderTimeAllocation.id).where(
            WorkOrderTimeAllocation.timer_session_id == TimerSession.id
        )
    )
    # Allocations replace the raw order link; zero seconds do not create a link
    raw_links = select(
        TimerSession.id.label("timer_session_id"),
        TimerSession.order_id.label("order_id"),
        literal(None, type_=Integer).label("allocated_seconds"),
    ).where(
        TimerSession.order_id.is_not(None),
        TimerSession.timer_type_code == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
        TimerSession.deleted_at.is_(None),
        ~allocated_session_exists,
    )
    allocated_links = (
        select(
            TimerSession.id.label("timer_session_id"),
            WorkOrderTimeAllocation.work_order_id.label("order_id"),
            WorkOrderTimeAllocation.allocated_seconds.label("allocated_seconds"),
        )
        .join(
            WorkOrderTimeAllocation,
            WorkOrderTimeAllocation.timer_session_id == TimerSession.id,
        )
        .where(
            TimerSession.timer_type_code
            == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            TimerSession.deleted_at.is_(None),
            WorkOrderTimeAllocation.allocated_seconds > 0,
        )
    )

    return union_all(raw_links, allocated_links).subquery()


def build_effective_operation_time_subquery() -> Any:
    effective_order_links = build_effective_operation_order_links_subquery()
    return (
        select(
            TimerSession.id.label("timer_session_id"),
            effective_order_links.c.order_id.label("order_id"),
            TimerSession.operation_id.label("operation_id"),
            TimerSession.user_id.label("user_id"),
            TimerSession.shift_id.label("shift_id"),
            TimerSession.started_at.label("started_at"),
            TimerSession.ended_at.label("ended_at"),
            case(
                (
                    effective_order_links.c.allocated_seconds.is_not(None),
                    effective_order_links.c.allocated_seconds * 1000,
                ),
                else_=TimerSession.ended_at - TimerSession.started_at,
            ).label("elapsed_ms"),
        )
        .select_from(effective_order_links)
        .join(
            TimerSession,
            TimerSession.id == effective_order_links.c.timer_session_id,
        )
        .where(TimerSession.ended_at.is_not(None))
        .subquery()
    )

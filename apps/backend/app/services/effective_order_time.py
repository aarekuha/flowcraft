from typing import Any

from sqlalchemy import exists, select, union_all

from app.models.timer_session import TimerSession
from app.models.work_order import WorkOrderTimeAllocation
from app.schemas.timer import TimerType
from app.services.timer_service import TIMER_TYPE_TO_CODE


def build_effective_operation_time_subquery() -> Any:
    allocated_session_exists = exists(
        select(WorkOrderTimeAllocation.id).where(
            WorkOrderTimeAllocation.timer_session_id == TimerSession.id
        )
    )
    raw_sessions = select(
        TimerSession.id.label("timer_session_id"),
        TimerSession.order_id.label("order_id"),
        TimerSession.operation_id.label("operation_id"),
        TimerSession.user_id.label("user_id"),
        TimerSession.shift_id.label("shift_id"),
        TimerSession.started_at.label("started_at"),
        TimerSession.ended_at.label("ended_at"),
        (TimerSession.ended_at - TimerSession.started_at).label("elapsed_ms"),
    ).where(
        TimerSession.order_id.is_not(None),
        TimerSession.timer_type_code == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
        TimerSession.ended_at.is_not(None),
        ~allocated_session_exists,
    )
    allocated_sessions = (
        select(
            TimerSession.id.label("timer_session_id"),
            WorkOrderTimeAllocation.work_order_id.label("order_id"),
            TimerSession.operation_id.label("operation_id"),
            TimerSession.user_id.label("user_id"),
            TimerSession.shift_id.label("shift_id"),
            TimerSession.started_at.label("started_at"),
            TimerSession.ended_at.label("ended_at"),
            (WorkOrderTimeAllocation.allocated_seconds * 1000).label("elapsed_ms"),
        )
        .join(
            WorkOrderTimeAllocation,
            WorkOrderTimeAllocation.timer_session_id == TimerSession.id,
        )
        .where(
            TimerSession.timer_type_code
            == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            TimerSession.ended_at.is_not(None),
        )
    )

    return union_all(raw_sessions, allocated_sessions).subquery()

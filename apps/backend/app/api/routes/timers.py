from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_authenticated_session, get_session
from app.core.timer_audit import TimerAudit
from app.schemas.timer import TimerSwitchPayload, WorkerTimerStateRead
from app.services.auth_service import AuthenticatedSession
from app.services.timer_service import TimerService

router = APIRouter()


@router.get(
    "/state", response_model=WorkerTimerStateRead, summary="Current worker timer state"
)
def get_timer_state(
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkerTimerStateRead:
    return TimerService(session).get_state(auth_session.user_id)


@router.post(
    "/start-day", response_model=WorkerTimerStateRead, summary="Start worker day"
)
def start_day(
    request: Request,
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkerTimerStateRead:
    return audited_service(request, session, auth_session).start_day(
        auth_session.user_id
    )


@router.post(
    "/switch", response_model=WorkerTimerStateRead, summary="Switch active timer"
)
def switch_timer(
    request: Request,
    payload: TimerSwitchPayload,
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkerTimerStateRead:
    return audited_service(request, session, auth_session, payload).switch_timer(
        auth_session.user_id,
        payload,
    )


@router.post("/end-day", response_model=WorkerTimerStateRead, summary="End worker day")
def end_day(
    request: Request,
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkerTimerStateRead:
    return audited_service(request, session, auth_session).end_day(auth_session.user_id)


def audited_service(
    request: Request,
    session: Session,
    auth: AuthenticatedSession,
    payload: TimerSwitchPayload | None = None,
) -> TimerService:
    audit: TimerAudit | None = getattr(request.state, "timer_audit", None)
    if audit is not None:
        audit.user_id = auth.user_id
        audit.auth_session_id = auth.session_id
        if payload is not None:
            audit.requested = {
                "timer_type": payload.timer_type.value,
                "order_id": payload.order_id,
                "operation_id": payload.operation_id,
            }
        audit.emit("timer_command_received")
    return TimerService(session, audit=audit)

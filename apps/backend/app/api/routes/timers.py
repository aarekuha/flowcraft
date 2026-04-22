from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_authenticated_session, get_session
from app.schemas.timer import TimerSwitchPayload, WorkerTimerStateRead
from app.services.auth_service import AuthenticatedSession
from app.services.timer_service import TimerService

router = APIRouter()


@router.get("/state", response_model=WorkerTimerStateRead, summary="Current worker timer state")
def get_timer_state(
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkerTimerStateRead:
    return TimerService(session).get_state(auth_session.user_id)


@router.post("/start-day", response_model=WorkerTimerStateRead, summary="Start worker day")
def start_day(
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkerTimerStateRead:
    return TimerService(session).start_day(auth_session.user_id)


@router.post("/switch", response_model=WorkerTimerStateRead, summary="Switch active timer")
def switch_timer(
    payload: TimerSwitchPayload,
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkerTimerStateRead:
    return TimerService(session).switch_timer(auth_session.user_id, payload)


@router.post("/end-day", response_model=WorkerTimerStateRead, summary="End worker day")
def end_day(
    auth_session: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> WorkerTimerStateRead:
    return TimerService(session).end_day(auth_session.user_id)

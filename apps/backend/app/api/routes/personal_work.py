from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_any_role
from app.schemas.completed_work import (
    PersonalReportAccess,
    PersonalReportUnlock,
    PersonalWorkReport,
)
from app.services.auth_service import AuthenticatedSession
from app.services.personal_work_service import PersonalWorkService

router = APIRouter()


@router.post("/completed-work/unlock", response_model=PersonalReportAccess)
def unlock_personal_report(
    payload: PersonalReportUnlock,
    response: Response,
    auth: AuthenticatedSession = Depends(require_any_role("worker")),
    session: Session = Depends(get_session),
) -> PersonalReportAccess:
    response.headers["Cache-Control"] = "no-store"
    return PersonalWorkService(session, auth).unlock(payload.password)


@router.get("/completed-work", response_model=PersonalWorkReport)
def personal_report(
    response: Response,
    year: int = Query(ge=2000, le=9998),
    month: int = Query(ge=1, le=12),
    x_work_report_token: str = Header(default="", max_length=128),
    auth: AuthenticatedSession = Depends(require_any_role("worker")),
    session: Session = Depends(get_session),
) -> PersonalWorkReport:
    response.headers["Cache-Control"] = "no-store"
    return PersonalWorkService(session, auth).calculate(
        x_work_report_token, year, month
    )

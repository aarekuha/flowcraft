from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_authenticated_session, get_session
from app.schemas.statistics import StatisticsOverviewRead
from app.services.auth_service import AuthenticatedSession
from app.services.statistics_service import StatisticsService

router = APIRouter()


@router.get("/overview", response_model=StatisticsOverviewRead, summary="Statistics overview")
def get_statistics_overview(
    days: Annotated[int, Query(ge=1, le=90)] = 14,
    _: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> StatisticsOverviewRead:
    return StatisticsService(session).get_overview(days)

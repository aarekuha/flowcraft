from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_authenticated_session, get_session
from app.schemas.statistics import StatisticsOverviewRead
from app.services.auth_service import AuthenticatedSession
from app.services.statistics_service import StatisticsService

router = APIRouter()


@router.get(
    "/overview",
    response_model=StatisticsOverviewRead,
    summary="Statistics overview",
)
def get_statistics_overview(
    days: Annotated[int | None, Query(ge=1, le=90)] = 14,
    date_from: date | None = None,
    date_to: date | None = None,
    _: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> StatisticsOverviewRead:
    return StatisticsService(session).get_overview(days, date_from, date_to)


@router.get("/export.xlsx", summary="Export statistics as XLSX")
def export_statistics_xlsx(
    days: Annotated[int | None, Query(ge=1, le=90)] = 14,
    date_from: date | None = None,
    date_to: date | None = None,
    _: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> Response:
    content, filename = StatisticsService(session).build_xlsx_export(
        days,
        date_from,
        date_to,
    )
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )

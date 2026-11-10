# ruff: noqa: I001

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_any_role
from app.models.bonus import Bonus, UserBonus, MonthlyBonusExclusion
from app.schemas.completed_work import (
    BonusInput,
    BonusRead,
    CompletedWorkReport,
    UserBonusesInput,
    MonthlyBonusSelection,
    WorkSummary,
)
from app.services.completed_work_service import CompletedWorkService

from app.services.work_summary_service import WorkSummaryService

router = APIRouter(dependencies=[Depends(require_any_role("admin"))])


@router.get("/bonuses", response_model=list[BonusRead])
def list_bonuses(session: Session = Depends(get_session)) -> list[Bonus]:
    return list(session.scalars(select(Bonus).order_by(Bonus.name, Bonus.id)))


@router.post("/bonuses", response_model=BonusRead, status_code=201)
def create_bonus(payload: BonusInput, session: Session = Depends(get_session)) -> Bonus:
    bonus = Bonus(**payload.model_dump())
    session.add(bonus)
    session.commit()
    session.refresh(bonus)
    return bonus


@router.put("/bonuses/{bonus_id}", response_model=BonusRead)
def update_bonus(
    bonus_id: int, payload: BonusInput, session: Session = Depends(get_session)
) -> Bonus:
    bonus = session.get(Bonus, bonus_id)
    if bonus is None:
        raise HTTPException(404, "Премия не найдена")
    bonus.name = payload.name
    bonus.amount_cents = payload.amount_cents
    session.commit()
    session.refresh(bonus)
    return bonus


@router.delete("/bonuses/{bonus_id}", status_code=204)
def delete_bonus(bonus_id: int, session: Session = Depends(get_session)) -> Response:
    bonus = session.get(Bonus, bonus_id)
    if bonus is None:
        raise HTTPException(404, "Премия не найдена")
    session.execute(delete(UserBonus).where(UserBonus.bonus_id == bonus_id))
    session.execute(
        delete(MonthlyBonusExclusion).where(MonthlyBonusExclusion.bonus_id == bonus_id)
    )
    session.delete(bonus)
    session.commit()
    return Response(status_code=204)


@router.get("/users/{user_id}/bonuses", response_model=list[BonusRead])
def user_bonuses(
    user_id: int, session: Session = Depends(get_session)
) -> list[BonusRead]:
    return CompletedWorkService(session).bonuses(user_id)


@router.put("/users/{user_id}/bonuses", response_model=list[BonusRead])
def set_user_bonuses(
    user_id: int, payload: UserBonusesInput, session: Session = Depends(get_session)
) -> list[BonusRead]:
    service = CompletedWorkService(session)
    service.get_user(user_id)
    ids = set(payload.bonus_ids)
    if len(list(session.scalars(select(Bonus.id).where(Bonus.id.in_(ids))))) != len(
        ids
    ):
        raise HTTPException(422, "Премия не найдена в справочнике")
    session.execute(delete(UserBonus).where(UserBonus.user_id == user_id))
    session.add_all([UserBonus(user_id=user_id, bonus_id=bonus_id) for bonus_id in ids])
    session.commit()
    return service.bonuses(user_id)


@router.get("/users/{user_id}/completed-work", response_model=CompletedWorkReport)
def completed_work(
    user_id: int,
    year: int = Query(ge=2000, le=9998),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
) -> CompletedWorkReport:
    return CompletedWorkService(session).calculate(user_id, year, month)


@router.get("/users/{user_id}/completed-work.xlsx")
def export_completed_work(
    user_id: int,
    year: int = Query(ge=2000, le=9998),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
) -> Response:
    content = CompletedWorkService(session).export(user_id, year, month)
    filename = f"completed-work-{user_id}-{year}-{month:02}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.put(
    "/users/{user_id}/completed-work/bonuses/{bonus_id}",
    response_model=CompletedWorkReport,
)
def set_monthly_bonus_selection(
    user_id: int,
    bonus_id: int,
    payload: MonthlyBonusSelection,
    year: int = Query(ge=2000, le=9998),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
) -> CompletedWorkReport:
    return CompletedWorkService(session).set_bonus_selection(
        user_id,
        year,
        month,
        bonus_id,
        selected=payload.selected,
    )


@router.get("/completed-work-summary", response_model=WorkSummary)
def work_summary(
    year: int = Query(ge=2000, le=9998),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
) -> WorkSummary:
    return WorkSummaryService(session).calculate(year, month)


@router.get("/completed-work-summary.xlsx")
def export_work_summary(
    year: int = Query(ge=2000, le=9998),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
) -> Response:
    content = WorkSummaryService(session).export(year, month)
    filename = f"completed-work-summary-{year}-{month:02}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

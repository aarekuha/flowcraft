from calendar import monthrange
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.planning import PlanningSettings, UserWorkScheduleDay
from app.models.user import User
from app.schemas.planning import (
    PlanningSettingsRead,
    PlanningSettingsUpdate,
    WorkScheduleBatchDelete,
    WorkScheduleBatchUpdate,
    WorkScheduleDayRead,
    WorkScheduleMonthRead,
    WorkScheduleWorkerRead,
)
from app.services.planning_revision_service import PlanningRevisionService
from app.services.production_calendar_service import ProductionCalendarService


class PlanningService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_settings(self) -> PlanningSettingsRead:
        settings = self._get_or_create_settings()
        return PlanningSettingsRead.model_validate(settings)

    def update_settings(
        self,
        payload: PlanningSettingsUpdate,
        updated_by_user_id: int,
    ) -> PlanningSettingsRead:
        settings = self._get_or_create_settings()
        settings.display_offset_days = payload.display_offset_days
        settings.preparation_seconds = payload.preparation_seconds
        settings.horizon_months = payload.horizon_months
        settings.updated_at = self._now_ts()
        settings.updated_by_user_id = updated_by_user_id
        PlanningRevisionService(self.session).request_recalculation()
        self.session.commit()
        self.session.refresh(settings)
        return PlanningSettingsRead.model_validate(settings)

    def get_work_schedule(self, month: str) -> WorkScheduleMonthRead:
        month_start, month_end, days_in_month = self._parse_month(month)
        users = self.session.scalars(
            select(User)
            .where(
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .order_by(User.name.asc(), User.id.asc())
        ).all()
        workers = [user for user in users if "worker" in user.roles]
        worker_ids = [worker.id for worker in workers]
        schedule_days: list[UserWorkScheduleDay] = []
        if worker_ids:
            schedule_days = list(
                self.session.scalars(
                    select(UserWorkScheduleDay)
                    .where(
                        UserWorkScheduleDay.user_id.in_(worker_ids),
                        UserWorkScheduleDay.work_date >= month_start,
                        UserWorkScheduleDay.work_date <= month_end,
                    )
                    .order_by(
                        UserWorkScheduleDay.user_id.asc(),
                        UserWorkScheduleDay.work_date.asc(),
                    )
                ).all()
            )
        days_by_user_id: dict[int, list[WorkScheduleDayRead]] = {
            worker.id: [] for worker in workers
        }
        for schedule_day in schedule_days:
            days_by_user_id[schedule_day.user_id].append(
                WorkScheduleDayRead.model_validate(schedule_day, from_attributes=True)
            )

        return WorkScheduleMonthRead(
            production_calendar=ProductionCalendarService(self.session).get_month(
                month_start.year, month_start.month
            ),
            month=month,
            days_in_month=days_in_month,
            workers=[
                WorkScheduleWorkerRead(
                    user_id=worker.id,
                    user_name=worker.name,
                    days=days_by_user_id[worker.id],
                )
                for worker in workers
            ],
        )

    def update_work_schedule(
        self,
        payload: WorkScheduleBatchUpdate | list[WorkScheduleBatchUpdate],
        updated_by_user_id: int,
    ) -> None:
        updates = payload if isinstance(payload, list) else [payload]
        if not updates:
            raise HTTPException(status_code=422, detail="Не выбран диапазон графика.")
        for item in updates:
            self._get_active_worker_or_422(item.user_id)
        for item in updates:
            existing_days = self.session.scalars(
                select(UserWorkScheduleDay).where(
                    UserWorkScheduleDay.user_id == item.user_id,
                    UserWorkScheduleDay.work_date.in_(item.work_dates),
                )
            ).all()
            existing_by_date = {day.work_date: day for day in existing_days}
            now = self._now_ts()
            for work_date in item.work_dates:
                schedule_day = existing_by_date.get(work_date)
                if schedule_day is None:
                    schedule_day = UserWorkScheduleDay(
                        user_id=item.user_id,
                        work_date=work_date,
                        available_seconds=item.available_seconds,
                        period_type=item.period_type,
                        updated_at=now,
                        updated_by_user_id=updated_by_user_id,
                    )
                    self.session.add(schedule_day)
                    continue
                schedule_day.period_type = item.period_type
                schedule_day.available_seconds = item.available_seconds
                schedule_day.updated_at = now
                schedule_day.updated_by_user_id = updated_by_user_id

        PlanningRevisionService(self.session).request_recalculation()
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "График уже изменён другим пользователем. Обновить календарь "
                    "и повторить сохранение."
                ),
            ) from error

    def delete_work_schedule(
        self,
        payload: WorkScheduleBatchDelete | list[WorkScheduleBatchDelete],
    ) -> None:
        selections = payload if isinstance(payload, list) else [payload]
        if not selections:
            raise HTTPException(status_code=422, detail="Не выбран диапазон графика.")
        for item in selections:
            self._get_active_worker_or_422(item.user_id)
        for item in selections:
            schedule_days = self.session.scalars(
                select(UserWorkScheduleDay).where(
                    UserWorkScheduleDay.user_id == item.user_id,
                    UserWorkScheduleDay.work_date.in_(item.work_dates),
                )
            ).all()
            for schedule_day in schedule_days:
                self.session.delete(schedule_day)
        PlanningRevisionService(self.session).request_recalculation()
        self.session.commit()

    def _get_or_create_settings(self) -> PlanningSettings:
        settings = self.session.get(PlanningSettings, 1)
        if settings is not None:
            return settings
        settings = PlanningSettings(
            id=1,
            display_offset_days=2,
            preparation_seconds=3600,
            horizon_months=3,
            updated_at=self._now_ts(),
            updated_by_user_id=None,
        )
        self.session.add(settings)
        self.session.commit()
        self.session.refresh(settings)
        return settings

    def _get_active_worker_or_422(self, user_id: int) -> User:
        user = self.session.get(User, user_id)
        if (
            user is None
            or user.deleted_at is not None
            or not user.is_active
            or "worker" not in user.roles
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="График можно изменять только активному исполнителю.",
            )
        return user

    def _parse_month(self, month: str) -> tuple[date, date, int]:
        try:
            month_start = date.fromisoformat(f"{month}-01")
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Месяц должен быть указан в формате ГГГГ-ММ.",
            ) from error
        days_in_month = monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=days_in_month)
        return month_start, month_end, days_in_month

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)

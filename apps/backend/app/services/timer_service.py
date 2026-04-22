from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.operation import Operation
from app.models.timer_session import TimerSession
from app.models.work_order import WorkOrder, WorkOrderAssignment
from app.models.work_shift import WorkShift
from app.schemas.timer import (
    ActiveTimerRead,
    TimerSessionAggregateRead,
    TimerSwitchPayload,
    TimerType,
    WorkShiftRead,
    WorkerTimerStateRead,
)


TIMER_TYPE_TO_CODE = {
    TimerType.PREPARATION: 1,
    TimerType.OPERATION: 2,
    TimerType.BREAK: 3,
    TimerType.IDLE: 4,
}
CODE_TO_TIMER_TYPE = {code: timer_type for timer_type, code in TIMER_TYPE_TO_CODE.items()}


class TimerService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_state(self, user_id: int) -> WorkerTimerStateRead:
        shift = self._get_open_shift(user_id)
        if shift is None:
            return WorkerTimerStateRead(shift=None, active_timer=None, timer_totals=[])

        return self._serialize_state(shift)

    def start_day(self, user_id: int) -> WorkerTimerStateRead:
        shift = self._get_open_shift(user_id)
        if shift is None:
            now = self._now_ts()
            shift = WorkShift(
                user_id=user_id,
                started_at=now,
                ended_at=None,
                business_date=self._business_date(now),
                created_at=now,
            )
            self.session.add(shift)
            self.session.flush()
            self._open_timer_session(
                user_id=user_id,
                shift_id=shift.id,
                timer_type=TimerType.PREPARATION,
                started_at=now,
            )
            self.session.commit()
            self.session.refresh(shift)
            return self._serialize_state(shift)

        active_session = self._get_open_timer_session(user_id)
        if active_session is None:
            self._open_timer_session(
                user_id=user_id,
                shift_id=shift.id,
                timer_type=TimerType.PREPARATION,
                started_at=self._now_ts(),
            )
            self.session.commit()

        return self._serialize_state(shift)

    def switch_timer(self, user_id: int, payload: TimerSwitchPayload) -> WorkerTimerStateRead:
        shift = self._get_open_shift(user_id)
        if shift is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Рабочий день не начат.",
            )

        self._validate_switch_payload(user_id, payload)
        active_session = self._get_open_timer_session(user_id)
        if active_session is not None and self._is_same_target(active_session, payload):
            return self._serialize_state(shift)

        now = self._now_ts()
        affected_order_ids: set[int] = set()

        if active_session is not None:
            active_session.ended_at = now
            if (
                active_session.timer_type_code == TIMER_TYPE_TO_CODE[TimerType.OPERATION]
                and active_session.order_id is not None
            ):
                affected_order_ids.add(active_session.order_id)

        self._open_timer_session(
            user_id=user_id,
            shift_id=shift.id,
            timer_type=payload.timer_type,
            order_id=payload.order_id,
            operation_id=payload.operation_id,
            started_at=now,
        )

        self._refresh_work_order_totals(affected_order_ids)
        self.session.commit()
        self.session.refresh(shift)
        return self._serialize_state(shift)

    def end_day(self, user_id: int) -> WorkerTimerStateRead:
        shift = self._get_open_shift(user_id)
        if shift is None:
            return WorkerTimerStateRead(shift=None, active_timer=None, timer_totals=[])

        now = self._now_ts()
        active_session = self._get_open_timer_session(user_id)
        affected_order_ids: set[int] = set()

        if active_session is not None:
            active_session.ended_at = now
            if (
                active_session.timer_type_code == TIMER_TYPE_TO_CODE[TimerType.OPERATION]
                and active_session.order_id is not None
            ):
                affected_order_ids.add(active_session.order_id)

        shift.ended_at = now
        self._refresh_work_order_totals(affected_order_ids)
        self.session.commit()
        return WorkerTimerStateRead(shift=None, active_timer=None, timer_totals=[])

    def _serialize_state(self, shift: WorkShift) -> WorkerTimerStateRead:
        now = self._now_ts()
        sessions = self.session.scalars(
            select(TimerSession)
            .where(TimerSession.shift_id == shift.id)
            .order_by(TimerSession.started_at.asc(), TimerSession.id.asc())
        ).all()

        aggregates: dict[tuple[int, int | None, int | None], int] = defaultdict(int)
        active_timer: ActiveTimerRead | None = None

        for timer_session in sessions:
            ended_at = timer_session.ended_at or now
            elapsed_ms = max(0, ended_at - timer_session.started_at)
            key = (
                timer_session.timer_type_code,
                timer_session.order_id,
                timer_session.operation_id,
            )
            aggregates[key] += elapsed_ms

            if timer_session.ended_at is None:
                active_timer = ActiveTimerRead(
                    timer_type=CODE_TO_TIMER_TYPE[timer_session.timer_type_code],
                    order_id=timer_session.order_id,
                    operation_id=timer_session.operation_id,
                    started_at=timer_session.started_at,
                )

        timer_totals = [
            TimerSessionAggregateRead(
                timer_type=CODE_TO_TIMER_TYPE[timer_type_code],
                order_id=order_id,
                operation_id=operation_id,
                elapsed_ms=elapsed_ms,
            )
            for (timer_type_code, order_id, operation_id), elapsed_ms in sorted(
                aggregates.items(),
                key=lambda item: (item[0][0], item[0][1] or 0, item[0][2] or 0),
            )
        ]

        return WorkerTimerStateRead(
            shift=WorkShiftRead(
                id=shift.id,
                started_at=shift.started_at,
                business_date=shift.business_date,
            ),
            active_timer=active_timer,
            timer_totals=timer_totals,
        )

    def _get_open_shift(self, user_id: int) -> WorkShift | None:
        stmt: Select[tuple[WorkShift]] = select(WorkShift).where(
            WorkShift.user_id == user_id,
            WorkShift.ended_at.is_(None),
        )
        return self.session.scalars(stmt).one_or_none()

    def _get_open_timer_session(self, user_id: int) -> TimerSession | None:
        stmt: Select[tuple[TimerSession]] = select(TimerSession).where(
            TimerSession.user_id == user_id,
            TimerSession.ended_at.is_(None),
        )
        return self.session.scalars(stmt).one_or_none()

    def _open_timer_session(
        self,
        *,
        user_id: int,
        shift_id: int,
        timer_type: TimerType,
        started_at: int,
        order_id: int | None = None,
        operation_id: int | None = None,
    ) -> None:
        timer_session = TimerSession(
            shift_id=shift_id,
            user_id=user_id,
            timer_type_code=TIMER_TYPE_TO_CODE[timer_type],
            order_id=order_id,
            operation_id=operation_id,
            started_at=started_at,
            ended_at=None,
            created_at=started_at,
        )
        self.session.add(timer_session)

    def _validate_switch_payload(self, user_id: int, payload: TimerSwitchPayload) -> None:
        if payload.timer_type == TimerType.OPERATION:
            if payload.order_id is None or payload.operation_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Для производственного таймера нужны заказ и операция.",
                )

            assignment_stmt = select(WorkOrderAssignment).where(
                WorkOrderAssignment.work_order_id == payload.order_id,
                WorkOrderAssignment.operation_id == payload.operation_id,
                WorkOrderAssignment.worker_user_id == user_id,
            )
            assignment = self.session.scalars(assignment_stmt).one_or_none()
            if assignment is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Операция не назначена текущему исполнителю.",
                )

            operation = self.session.get(Operation, payload.operation_id)
            order = self.session.get(WorkOrder, payload.order_id)
            if operation is None or order is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Заказ или операция не найдены.",
                )
            return

        if payload.order_id is not None or payload.operation_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Служебные таймеры не должны быть привязаны к заказу или операции.",
            )

    def _is_same_target(self, timer_session: TimerSession, payload: TimerSwitchPayload) -> bool:
        return (
            timer_session.timer_type_code == TIMER_TYPE_TO_CODE[payload.timer_type]
            and timer_session.order_id == payload.order_id
            and timer_session.operation_id == payload.operation_id
        )

    def _refresh_work_order_totals(self, order_ids: set[int]) -> None:
        if not order_ids:
            return

        for order_id in order_ids:
            stmt = select(
                func.coalesce(
                    func.sum(TimerSession.ended_at - TimerSession.started_at),
                    0,
                )
            ).where(
                TimerSession.order_id == order_id,
                TimerSession.timer_type_code == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                TimerSession.ended_at.is_not(None),
            )
            total_ms = int(self.session.execute(stmt).scalar_one())
            order = self.session.get(WorkOrder, order_id)
            if order is not None:
                order.total_spent_minutes = total_ms // 60000
                order.updated_at = self._now_ts()

    def _business_date(self, timestamp_ms: int) -> str:
        return datetime.fromtimestamp(timestamp_ms / 1000, UTC).date().isoformat()

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)

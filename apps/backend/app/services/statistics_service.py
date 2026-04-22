from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.models.timer_session import TimerSession
from app.models.work_order import WorkOrder
from app.schemas.statistics import (
    StatisticsDailyRead,
    StatisticsKpiRead,
    StatisticsOperationRead,
    StatisticsOrderRead,
    StatisticsOverviewRead,
    StatisticsWorkerRead,
)
from app.schemas.timer import TimerType
from app.services.timer_service import TIMER_TYPE_TO_CODE


@dataclass(slots=True)
class _WindowedSession:
    timer_type: TimerType
    user_id: int
    user_name: str
    order_id: int | None
    order_number: str | None
    product_name: str | None
    product_version: str | None
    operation_id: int | None
    operation_name: str | None
    started_at: int
    ended_at: int
    elapsed_ms: int


class StatisticsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_overview(self, days: int) -> StatisticsOverviewRead:
        normalized_days = min(max(days, 1), 90)
        now = self._now_ts()
        period_start = self._period_start(now, normalized_days)
        sessions = self._load_sessions(period_start, now)

        totals_by_type = defaultdict(int)
        orders_touched: set[int] = set()
        daily_breakdown = {
            date_key: {
                "operation_ms": 0,
                "preparation_ms": 0,
                "break_ms": 0,
                "idle_ms": 0,
                "total_ms": 0,
            }
            for date_key in self._date_keys(period_start, now)
        }
        top_operations: dict[int, dict[str, int | str]] = {}
        top_orders: dict[int, dict[str, int | str]] = {}
        workers: dict[int, dict[str, int | str | float]] = {}

        for timer_session in sessions:
            totals_by_type[timer_session.timer_type] += timer_session.elapsed_ms
            if timer_session.order_id is not None:
                orders_touched.add(timer_session.order_id)

            self._accumulate_daily_breakdown(daily_breakdown, timer_session)
            self._accumulate_operation(top_operations, timer_session)
            self._accumulate_order(top_orders, timer_session)
            self._accumulate_worker(workers, timer_session)

        total_tracked_ms = sum(totals_by_type.values())
        operation_ms = totals_by_type[TimerType.OPERATION]
        preparation_ms = totals_by_type[TimerType.PREPARATION]
        break_ms = totals_by_type[TimerType.BREAK]
        idle_ms = totals_by_type[TimerType.IDLE]

        kpis = StatisticsKpiRead(
            total_tracked_ms=total_tracked_ms,
            operation_ms=operation_ms,
            preparation_ms=preparation_ms,
            break_ms=break_ms,
            idle_ms=idle_ms,
            productive_ratio=(operation_ms / total_tracked_ms) if total_tracked_ms else 0.0,
            active_orders_count=len(orders_touched),
        )

        top_operation_rows = sorted(
            [
                StatisticsOperationRead(
                    operation_id=operation_id,
                    operation_name=str(data["operation_name"]),
                    product_name=str(data["product_name"]),
                    product_version=str(data["product_version"]),
                    total_ms=int(data["total_ms"]),
                    sessions_count=int(data["sessions_count"]),
                    average_ms=int(data["total_ms"]) // int(data["sessions_count"]),
                )
                for operation_id, data in top_operations.items()
            ],
            key=lambda row: row.total_ms,
            reverse=True,
        )[:8]

        top_order_rows = sorted(
            [
                StatisticsOrderRead(
                    order_id=order_id,
                    order_number=str(data["order_number"]),
                    product_name=str(data["product_name"]),
                    product_version=str(data["product_version"]),
                    total_ms=int(data["total_ms"]),
                )
                for order_id, data in top_orders.items()
            ],
            key=lambda row: row.total_ms,
            reverse=True,
        )[:8]

        worker_rows = sorted(
            [
                StatisticsWorkerRead(
                    user_id=user_id,
                    user_name=str(data["user_name"]),
                    total_ms=int(data["total_ms"]),
                    operation_ms=int(data["operation_ms"]),
                    idle_ms=int(data["idle_ms"]),
                    productive_ratio=(
                        int(data["operation_ms"]) / int(data["total_ms"])
                        if int(data["total_ms"])
                        else 0.0
                    ),
                )
                for user_id, data in workers.items()
            ],
            key=lambda row: row.total_ms,
            reverse=True,
        )

        daily_rows = [
            StatisticsDailyRead(date=date_key, **values)
            for date_key, values in daily_breakdown.items()
        ]
        idle_rows = [
            StatisticsDailyRead(
                date=date_key,
                operation_ms=0,
                preparation_ms=0,
                break_ms=0,
                idle_ms=values["idle_ms"],
                total_ms=values["idle_ms"],
            )
            for date_key, values in daily_breakdown.items()
        ]

        return StatisticsOverviewRead(
            days=normalized_days,
            generated_at=now,
            kpis=kpis,
            daily_breakdown=daily_rows,
            top_operations=top_operation_rows,
            top_orders=top_order_rows,
            workers=worker_rows,
            idle_by_day=idle_rows,
        )

    def _load_sessions(self, period_start: int, now: int) -> list[_WindowedSession]:
        stmt: Select[tuple[TimerSession]] = (
            select(TimerSession)
            .options(
                joinedload(TimerSession.user),
                joinedload(TimerSession.order).joinedload(WorkOrder.product),
                joinedload(TimerSession.operation),
            )
            .where(TimerSession.started_at < now)
            .where((TimerSession.ended_at.is_(None)) | (TimerSession.ended_at > period_start))
        )

        sessions = self.session.scalars(stmt).all()
        windowed_sessions: list[_WindowedSession] = []
        for timer_session in sessions:
            clipped_start = max(timer_session.started_at, period_start)
            clipped_end = min(timer_session.ended_at or now, now)
            if clipped_end <= clipped_start:
                continue

            order = timer_session.order
            operation = timer_session.operation
            user = timer_session.user
            windowed_sessions.append(
                _WindowedSession(
                    timer_type=self._timer_type_from_code(timer_session.timer_type_code),
                    user_id=user.id,
                    user_name=user.name,
                    order_id=timer_session.order_id,
                    order_number=order.order_number if order is not None else None,
                    product_name=order.product.name if order is not None else None,
                    product_version=order.product.version if order is not None else None,
                    operation_id=timer_session.operation_id,
                    operation_name=operation.name if operation is not None else None,
                    started_at=clipped_start,
                    ended_at=clipped_end,
                    elapsed_ms=clipped_end - clipped_start,
                )
            )
        return windowed_sessions

    def _accumulate_daily_breakdown(
        self,
        daily_breakdown: dict[str, dict[str, int]],
        timer_session: _WindowedSession,
    ) -> None:
        field_name = f"{timer_session.timer_type.value}_ms"
        for date_key, elapsed_ms in self._split_by_day(
            timer_session.started_at,
            timer_session.ended_at,
        ):
            bucket = daily_breakdown[date_key]
            bucket[field_name] += elapsed_ms
            bucket["total_ms"] += elapsed_ms

    def _accumulate_operation(
        self,
        top_operations: dict[int, dict[str, int | str]],
        timer_session: _WindowedSession,
    ) -> None:
        if timer_session.timer_type != TimerType.OPERATION or timer_session.operation_id is None:
            return

        entry = top_operations.setdefault(
            timer_session.operation_id,
            {
                "operation_name": timer_session.operation_name or "Операция",
                "product_name": timer_session.product_name or "—",
                "product_version": timer_session.product_version or "—",
                "total_ms": 0,
                "sessions_count": 0,
            },
        )
        entry["total_ms"] = int(entry["total_ms"]) + timer_session.elapsed_ms
        entry["sessions_count"] = int(entry["sessions_count"]) + 1

    def _accumulate_order(
        self,
        top_orders: dict[int, dict[str, int | str]],
        timer_session: _WindowedSession,
    ) -> None:
        if timer_session.order_id is None:
            return

        entry = top_orders.setdefault(
            timer_session.order_id,
            {
                "order_number": timer_session.order_number or "—",
                "product_name": timer_session.product_name or "—",
                "product_version": timer_session.product_version or "—",
                "total_ms": 0,
            },
        )
        entry["total_ms"] = int(entry["total_ms"]) + timer_session.elapsed_ms

    def _accumulate_worker(
        self,
        workers: dict[int, dict[str, int | str | float]],
        timer_session: _WindowedSession,
    ) -> None:
        entry = workers.setdefault(
            timer_session.user_id,
            {
                "user_name": timer_session.user_name,
                "total_ms": 0,
                "operation_ms": 0,
                "idle_ms": 0,
            },
        )
        entry["total_ms"] = int(entry["total_ms"]) + timer_session.elapsed_ms
        if timer_session.timer_type == TimerType.OPERATION:
            entry["operation_ms"] = int(entry["operation_ms"]) + timer_session.elapsed_ms
        if timer_session.timer_type == TimerType.IDLE:
            entry["idle_ms"] = int(entry["idle_ms"]) + timer_session.elapsed_ms

    def _split_by_day(self, started_at: int, ended_at: int) -> list[tuple[str, int]]:
        parts: list[tuple[str, int]] = []
        current_start = started_at
        while current_start < ended_at:
            current_date = datetime.fromtimestamp(current_start / 1000, UTC).date()
            next_day_start = datetime.combine(
                current_date + timedelta(days=1),
                datetime.min.time(),
                UTC,
            )
            next_day_ts = int(next_day_start.timestamp() * 1000)
            current_end = min(ended_at, next_day_ts)
            parts.append((current_date.isoformat(), current_end - current_start))
            current_start = current_end
        return parts

    def _date_keys(self, period_start: int, now: int) -> list[str]:
        start_date = datetime.fromtimestamp(period_start / 1000, UTC).date()
        end_date = datetime.fromtimestamp(now / 1000, UTC).date()
        current_date = start_date
        keys: list[str] = []
        while current_date <= end_date:
            keys.append(current_date.isoformat())
            current_date += timedelta(days=1)
        return keys

    def _period_start(self, now: int, days: int) -> int:
        current_datetime = datetime.fromtimestamp(now / 1000, UTC)
        midnight_today = datetime.combine(current_datetime.date(), datetime.min.time(), UTC)
        start_datetime = midnight_today - timedelta(days=days - 1)
        return int(start_datetime.timestamp() * 1000)

    def _timer_type_from_code(self, timer_type_code: int) -> TimerType:
        for timer_type, code in TIMER_TYPE_TO_CODE.items():
            if code == timer_type_code:
                return timer_type
        raise ValueError(f"Unsupported timer type code: {timer_type_code}")

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)

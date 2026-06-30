from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.models.operation import Operation
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
from app.services.xlsx_writer import SheetRows, build_xlsx

MAX_STATISTICS_PERIOD_DAYS = 90


@dataclass(slots=True)
class _StatisticsPeriod:
    date_from: date
    date_to: date
    start_ts: int
    end_ts: int
    days: int


@dataclass(slots=True)
class _WindowedSession:
    session_id: int
    timer_type: TimerType
    user_id: int
    user_name: str
    shift_business_date: str
    order_id: int | None
    order_number: str | None
    product_name: str | None
    product_version: str | None
    leather_type_name: str | None
    order_quantity: int | None
    order_estimated_minutes: int | None
    order_total_spent_minutes: int | None
    order_created_at: int | None
    order_taken_at: int | None
    order_quality_control_at: int | None
    order_defect_quantity: int | None
    order_completed_at: int | None
    order_deleted_at: int | None
    operation_id: int | None
    operation_name: str | None
    started_at: int
    ended_at: int
    elapsed_ms: int
    is_open: bool
    is_clipped: bool


@dataclass(slots=True)
class _ExportOrder:
    order_number: str
    product_name: str
    product_version: str
    leather_type_name: str
    quantity: int
    estimated_minutes: int
    total_spent_minutes: int
    created_at: int | None
    taken_at: int | None
    quality_control_at: int | None
    defect_quantity: int
    completed_at: int | None
    deleted_at: int | None
    total_ms: int = 0


@dataclass(slots=True)
class _ExportWorker:
    user_name: str
    total_ms: int = 0
    operation_ms: int = 0
    preparation_ms: int = 0
    break_ms: int = 0
    idle_ms: int = 0
    order_ids: set[int] = field(default_factory=set)
    operation_sessions_count: int = 0
    operation_sessions_ms: int = 0


@dataclass(slots=True)
class _ExportOperation:
    operation_name: str
    product_name: str
    product_version: str
    user_name: str
    order_ids: set[int] = field(default_factory=set)
    sessions_count: int = 0
    total_ms: int = 0
    min_ms: int | None = None
    max_ms: int | None = None


class StatisticsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_overview(
        self,
        days: int | None = 14,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> StatisticsOverviewRead:
        now = self._now_ts()
        period = self._resolve_period(now, days, date_from, date_to)
        sessions = self._load_sessions(period.start_ts, period.end_ts, now)

        totals_by_type: defaultdict[TimerType, int] = defaultdict(int)
        orders_touched: set[int] = set()
        daily_breakdown = {
            date_key: {
                "operation_ms": 0,
                "preparation_ms": 0,
                "break_ms": 0,
                "idle_ms": 0,
                "total_ms": 0,
            }
            for date_key in self._date_keys(period.date_from, period.date_to)
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
            productive_ratio=(operation_ms / total_tracked_ms)
            if total_tracked_ms
            else 0.0,
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
            days=period.days,
            date_from=period.date_from.isoformat(),
            date_to=period.date_to.isoformat(),
            generated_at=now,
            kpis=kpis,
            daily_breakdown=daily_rows,
            top_operations=top_operation_rows,
            top_orders=top_order_rows,
            workers=worker_rows,
            idle_by_day=idle_rows,
        )

    def build_xlsx_export(
        self,
        days: int | None = 14,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[bytes, str]:
        now = self._now_ts()
        period = self._resolve_period(now, days, date_from, date_to)
        sessions = self._load_sessions(period.start_ts, period.end_ts, now)
        overview = self._build_export_overview(period, sessions, now)
        filename = (
            "flowcraft-statistics-"
            f"{period.date_from.isoformat()}_{period.date_to.isoformat()}.xlsx"
        )
        return (
            build_xlsx(
                [
                    ("Сводка", overview["summary"]),
                    ("По дням", overview["daily"]),
                    ("Заказы", overview["orders"]),
                    ("Сотрудники", overview["workers"]),
                    ("Операции", overview["operations"]),
                    ("Таймеры", overview["timers"]),
                ]
            ),
            filename,
        )

    def _build_export_overview(
        self,
        period: _StatisticsPeriod,
        sessions: list[_WindowedSession],
        now: int,
    ) -> dict[str, SheetRows]:
        totals_by_type: defaultdict[TimerType, int] = defaultdict(int)
        daily_breakdown = {
            date_key: {
                "operation_ms": 0,
                "preparation_ms": 0,
                "break_ms": 0,
                "idle_ms": 0,
                "total_ms": 0,
            }
            for date_key in self._date_keys(period.date_from, period.date_to)
        }
        orders: dict[int, _ExportOrder] = {}
        workers: dict[int, _ExportWorker] = {}
        operations: dict[tuple[int, int], _ExportOperation] = {}

        for timer_session in sessions:
            totals_by_type[timer_session.timer_type] += timer_session.elapsed_ms
            self._accumulate_daily_breakdown(daily_breakdown, timer_session)
            self._accumulate_export_order(orders, timer_session)
            self._accumulate_export_worker(workers, timer_session)
            self._accumulate_export_operation(operations, timer_session)

        total_ms = sum(totals_by_type.values())
        operation_ms = totals_by_type[TimerType.OPERATION]
        preparation_ms = totals_by_type[TimerType.PREPARATION]
        break_ms = totals_by_type[TimerType.BREAK]
        idle_ms = totals_by_type[TimerType.IDLE]

        summary_rows: list[list[str | int | float | None]] = [
            ["Показатель", "Значение"],
            ["Период с", period.date_from.isoformat()],
            ["Период по", period.date_to.isoformat()],
            ["Дней", period.days],
            ["Сформировано", self._format_ts(now)],
            ["Всего учтено, мин", self._minutes(total_ms)],
            ["Операции, мин", self._minutes(operation_ms)],
            ["Подготовка, мин", self._minutes(preparation_ms)],
            ["Перерыв, мин", self._minutes(break_ms)],
            ["Простой, мин", self._minutes(idle_ms)],
            ["Полезное время, %", self._percentage(operation_ms, total_ms)],
            ["Заказов с трудозатратами", len(orders)],
            ["Сессий таймеров", len(sessions)],
        ]

        daily_rows: list[list[str | int | float | None]] = [
            [
                "Дата",
                "Операции, мин",
                "Подготовка, мин",
                "Перерыв, мин",
                "Простой, мин",
                "Всего, мин",
                "Полезное время, %",
            ]
        ]
        for date_key, values in daily_breakdown.items():
            daily_rows.append(
                [
                    date_key,
                    self._minutes(values["operation_ms"]),
                    self._minutes(values["preparation_ms"]),
                    self._minutes(values["break_ms"]),
                    self._minutes(values["idle_ms"]),
                    self._minutes(values["total_ms"]),
                    self._percentage(values["operation_ms"], values["total_ms"]),
                ]
            )

        order_rows: list[list[str | int | float | None]] = [
            [
                "Номер заказа",
                "Изделие",
                "Версия",
                "Вид кожи",
                "Количество",
                "План, мин",
                "Факт за период, мин",
                "Факт всего, мин",
                "Отклонение за период, мин",
                "Минут на изделие",
                "Брак, шт",
                "Брак, %",
                "Создан",
                "Взят в работу",
                "ОТК",
                "Завершен",
                "Статус",
            ]
        ]
        for order in sorted(
            orders.values(),
            key=lambda item: item.total_ms,
            reverse=True,
        ):
            period_minutes = self._minutes(order.total_ms)
            order_rows.append(
                [
                    order.order_number,
                    order.product_name,
                    order.product_version,
                    order.leather_type_name,
                    order.quantity,
                    order.estimated_minutes,
                    period_minutes,
                    order.total_spent_minutes,
                    round(period_minutes - order.estimated_minutes, 2),
                    round(period_minutes / order.quantity, 2)
                    if order.quantity > 0
                    else 0,
                    order.defect_quantity,
                    self._percentage(order.defect_quantity, order.quantity),
                    self._format_ts(order.created_at),
                    self._format_ts(order.taken_at),
                    self._format_ts(order.quality_control_at),
                    self._format_ts(order.completed_at),
                    self._order_status(order),
                ]
            )

        worker_rows: list[list[str | int | float | None]] = [
            [
                "Сотрудник",
                "Всего, мин",
                "Операции, мин",
                "Подготовка, мин",
                "Перерыв, мин",
                "Простой, мин",
                "Полезное время, %",
                "Заказов, шт",
                "Запусков операций, шт",
                "Среднее операции, мин",
            ]
        ]
        for worker in sorted(
            workers.values(),
            key=lambda item: item.total_ms,
            reverse=True,
        ):
            worker_rows.append(
                [
                    worker.user_name,
                    self._minutes(worker.total_ms),
                    self._minutes(worker.operation_ms),
                    self._minutes(worker.preparation_ms),
                    self._minutes(worker.break_ms),
                    self._minutes(worker.idle_ms),
                    self._percentage(worker.operation_ms, worker.total_ms),
                    len(worker.order_ids),
                    worker.operation_sessions_count,
                    self._average_minutes(
                        worker.operation_sessions_ms,
                        worker.operation_sessions_count,
                    ),
                ]
            )

        operation_rows: list[list[str | int | float | None]] = [
            [
                "Изделие",
                "Версия",
                "Операция",
                "Исполнитель",
                "Заказов, шт",
                "Запусков, шт",
                "Всего, мин",
                "Среднее, мин",
                "Минимум, мин",
                "Максимум, мин",
            ]
        ]
        for operation in sorted(
            operations.values(),
            key=lambda item: item.total_ms,
            reverse=True,
        ):
            operation_rows.append(
                [
                    operation.product_name,
                    operation.product_version,
                    operation.operation_name,
                    operation.user_name,
                    len(operation.order_ids),
                    operation.sessions_count,
                    self._minutes(operation.total_ms),
                    self._average_minutes(operation.total_ms, operation.sessions_count),
                    self._minutes(operation.min_ms or 0),
                    self._minutes(operation.max_ms or 0),
                ]
            )

        timer_rows: list[list[str | int | float | None]] = [
            [
                "ID сессии",
                "Рабочий день",
                "Сотрудник",
                "Тип таймера",
                "Номер заказа",
                "Изделие",
                "Версия",
                "Вид кожи",
                "Операция",
                "Начало",
                "Конец",
                "Длительность, мин",
                "Открыт",
                "Обрезан периодом",
            ]
        ]
        for timer_session in sorted(sessions, key=lambda item: item.started_at):
            timer_rows.append(
                [
                    timer_session.session_id,
                    timer_session.shift_business_date,
                    timer_session.user_name,
                    self._timer_type_label(timer_session.timer_type),
                    timer_session.order_number or "",
                    timer_session.product_name or "",
                    timer_session.product_version or "",
                    timer_session.leather_type_name or "",
                    timer_session.operation_name or "",
                    self._format_ts(timer_session.started_at),
                    self._format_ts(timer_session.ended_at),
                    self._minutes(timer_session.elapsed_ms),
                    "да" if timer_session.is_open else "нет",
                    "да" if timer_session.is_clipped else "нет",
                ]
            )

        return {
            "summary": summary_rows,
            "daily": daily_rows,
            "orders": order_rows,
            "workers": worker_rows,
            "operations": operation_rows,
            "timers": timer_rows,
        }

    def _load_sessions(
        self,
        period_start: int,
        period_end: int,
        now: int,
    ) -> list[_WindowedSession]:
        stmt: Select[tuple[TimerSession]] = (
            select(TimerSession)
            .options(
                joinedload(TimerSession.shift),
                joinedload(TimerSession.user),
                joinedload(TimerSession.order).joinedload(WorkOrder.product),
                joinedload(TimerSession.order).joinedload(WorkOrder.leather_type),
                joinedload(TimerSession.operation).joinedload(Operation.catalog_entry),
            )
            .where(TimerSession.started_at < period_end)
            .where(
                (TimerSession.ended_at.is_(None))
                | (TimerSession.ended_at > period_start)
            )
        )

        sessions = self.session.scalars(stmt).all()
        windowed_sessions: list[_WindowedSession] = []
        for timer_session in sessions:
            clipped_start = max(timer_session.started_at, period_start)
            clipped_end = min(timer_session.ended_at or now, period_end, now)
            if clipped_end <= clipped_start:
                continue

            order = timer_session.order
            operation = timer_session.operation
            user = timer_session.user
            is_open = timer_session.ended_at is None
            windowed_sessions.append(
                _WindowedSession(
                    session_id=timer_session.id,
                    timer_type=self._timer_type_from_code(
                        timer_session.timer_type_code
                    ),
                    user_id=user.id,
                    user_name=user.name,
                    shift_business_date=timer_session.shift.business_date,
                    order_id=timer_session.order_id,
                    order_number=order.order_number if order is not None else None,
                    product_name=order.product.name if order is not None else None,
                    product_version=order.product.version
                    if order is not None
                    else None,
                    leather_type_name=(
                        order.leather_type.name
                        if order is not None and order.leather_type is not None
                        else None
                    ),
                    order_quantity=order.quantity if order is not None else None,
                    order_estimated_minutes=(
                        order.estimated_minutes if order is not None else None
                    ),
                    order_total_spent_minutes=(
                        order.total_spent_minutes if order is not None else None
                    ),
                    order_created_at=order.created_at if order is not None else None,
                    order_taken_at=order.taken_at if order is not None else None,
                    order_quality_control_at=(
                        order.quality_control_at if order is not None else None
                    ),
                    order_defect_quantity=(
                        order.defect_quantity if order is not None else None
                    ),
                    order_completed_at=(
                        order.completed_at if order is not None else None
                    ),
                    order_deleted_at=order.deleted_at if order is not None else None,
                    operation_id=timer_session.operation_id,
                    operation_name=(
                        self._get_operation_name(operation)
                        if operation is not None
                        else None
                    ),
                    started_at=clipped_start,
                    ended_at=clipped_end,
                    elapsed_ms=clipped_end - clipped_start,
                    is_open=is_open,
                    is_clipped=(
                        clipped_start != timer_session.started_at
                        or clipped_end != (timer_session.ended_at or now)
                    ),
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
        if (
            timer_session.timer_type != TimerType.OPERATION
            or timer_session.operation_id is None
        ):
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
            entry["operation_ms"] = (
                int(entry["operation_ms"]) + timer_session.elapsed_ms
            )
        if timer_session.timer_type == TimerType.IDLE:
            entry["idle_ms"] = int(entry["idle_ms"]) + timer_session.elapsed_ms

    def _accumulate_export_order(
        self,
        orders: dict[int, _ExportOrder],
        timer_session: _WindowedSession,
    ) -> None:
        if timer_session.order_id is None:
            return

        entry = orders.setdefault(
            timer_session.order_id,
            _ExportOrder(
                order_number=timer_session.order_number or "—",
                product_name=timer_session.product_name or "—",
                product_version=timer_session.product_version or "—",
                leather_type_name=timer_session.leather_type_name or "",
                quantity=timer_session.order_quantity or 0,
                estimated_minutes=timer_session.order_estimated_minutes or 0,
                total_spent_minutes=timer_session.order_total_spent_minutes or 0,
                created_at=timer_session.order_created_at,
                taken_at=timer_session.order_taken_at,
                quality_control_at=timer_session.order_quality_control_at,
                defect_quantity=timer_session.order_defect_quantity or 0,
                completed_at=timer_session.order_completed_at,
                deleted_at=timer_session.order_deleted_at,
            ),
        )
        entry.total_ms += timer_session.elapsed_ms

    def _accumulate_export_worker(
        self,
        workers: dict[int, _ExportWorker],
        timer_session: _WindowedSession,
    ) -> None:
        entry = workers.setdefault(
            timer_session.user_id,
            _ExportWorker(user_name=timer_session.user_name),
        )
        entry.total_ms += timer_session.elapsed_ms
        if timer_session.order_id is not None:
            entry.order_ids.add(timer_session.order_id)

        if timer_session.timer_type == TimerType.OPERATION:
            entry.operation_ms += timer_session.elapsed_ms
            entry.operation_sessions_count += 1
            entry.operation_sessions_ms += timer_session.elapsed_ms
        elif timer_session.timer_type == TimerType.PREPARATION:
            entry.preparation_ms += timer_session.elapsed_ms
        elif timer_session.timer_type == TimerType.BREAK:
            entry.break_ms += timer_session.elapsed_ms
        elif timer_session.timer_type == TimerType.IDLE:
            entry.idle_ms += timer_session.elapsed_ms

    def _accumulate_export_operation(
        self,
        operations: dict[tuple[int, int], _ExportOperation],
        timer_session: _WindowedSession,
    ) -> None:
        if (
            timer_session.timer_type != TimerType.OPERATION
            or timer_session.operation_id is None
        ):
            return

        key = (timer_session.operation_id, timer_session.user_id)
        entry = operations.setdefault(
            key,
            _ExportOperation(
                operation_name=timer_session.operation_name or "Операция",
                product_name=timer_session.product_name or "—",
                product_version=timer_session.product_version or "—",
                user_name=timer_session.user_name,
            ),
        )
        if timer_session.order_id is not None:
            entry.order_ids.add(timer_session.order_id)
        entry.sessions_count += 1
        entry.total_ms += timer_session.elapsed_ms
        entry.min_ms = (
            timer_session.elapsed_ms
            if entry.min_ms is None
            else min(entry.min_ms, timer_session.elapsed_ms)
        )
        entry.max_ms = (
            timer_session.elapsed_ms
            if entry.max_ms is None
            else max(entry.max_ms, timer_session.elapsed_ms)
        )

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

    def _date_keys(self, date_from: date, date_to: date) -> list[str]:
        current_date = date_from
        keys: list[str] = []
        while current_date <= date_to:
            keys.append(current_date.isoformat())
            current_date += timedelta(days=1)
        return keys

    def _resolve_period(
        self,
        now: int,
        days: int | None,
        date_from: date | None,
        date_to: date | None,
    ) -> _StatisticsPeriod:
        if date_from is not None or date_to is not None:
            if date_from is None or date_to is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Укажите обе даты периода.",
                )
            if date_to < date_from:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Дата окончания периода не может быть раньше даты начала.",
                )
            period_days = (date_to - date_from).days + 1
            if period_days > MAX_STATISTICS_PERIOD_DAYS:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Период статистики не может быть больше "
                        f"{MAX_STATISTICS_PERIOD_DAYS} дней."
                    ),
                )
            return _StatisticsPeriod(
                date_from=date_from,
                date_to=date_to,
                start_ts=self._date_start_ts(date_from),
                end_ts=self._date_start_ts(date_to + timedelta(days=1)),
                days=period_days,
            )

        normalized_days = min(max(days or 14, 1), MAX_STATISTICS_PERIOD_DAYS)
        current_date = datetime.fromtimestamp(now / 1000, UTC).date()
        period_date_from = current_date - timedelta(days=normalized_days - 1)
        return _StatisticsPeriod(
            date_from=period_date_from,
            date_to=current_date,
            start_ts=self._date_start_ts(period_date_from),
            end_ts=now,
            days=normalized_days,
        )

    def _date_start_ts(self, value: date) -> int:
        return int(
            datetime.combine(value, datetime.min.time(), UTC).timestamp() * 1000
        )

    def _timer_type_from_code(self, timer_type_code: int) -> TimerType:
        for timer_type, code in TIMER_TYPE_TO_CODE.items():
            if code == timer_type_code:
                return timer_type
        raise ValueError(f"Unsupported timer type code: {timer_type_code}")

    def _get_operation_name(self, operation: Operation) -> str:
        if operation.catalog_entry is not None:
            return str(operation.catalog_entry.name)
        return str(operation.name)

    def _order_status(self, order: _ExportOrder) -> str:
        if order.deleted_at is not None:
            return "Удален"
        if order.completed_at is not None:
            return "Выполнен"
        if order.quality_control_at is not None:
            return "ОТК"
        if order.taken_at is not None:
            return "В работе"
        return "Создан"

    def _timer_type_label(self, timer_type: TimerType) -> str:
        labels = {
            TimerType.PREPARATION: "Подготовка",
            TimerType.OPERATION: "Операция",
            TimerType.BREAK: "Перерыв",
            TimerType.IDLE: "Простой",
        }
        return labels[timer_type]

    def _minutes(self, elapsed_ms: int) -> float:
        return round(elapsed_ms / 60_000, 2)

    def _average_minutes(self, total_ms: int, count: int) -> float:
        if count <= 0:
            return 0
        return self._minutes(total_ms // count)

    def _percentage(self, numerator: int | float, denominator: int | float) -> float:
        if denominator <= 0:
            return 0
        return round((numerator / denominator) * 100, 2)

    def _format_ts(self, timestamp_ms: int | None) -> str:
        if timestamp_ms is None:
            return ""
        return datetime.fromtimestamp(timestamp_ms / 1000, UTC).strftime(
            "%Y-%m-%d %H:%M"
        )

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)

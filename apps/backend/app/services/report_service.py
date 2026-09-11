from __future__ import annotations

# ruff: noqa: I001

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from app.models.leather_type import LeatherType
from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderAssignment
from app.models.work_shift import WorkShift
from app.schemas.report import (
    OrderBatchReport,
    OrderBatchReportDetail,
    OrderBatchReportItem,
    ProductQuantityReport,
    ProductQuantityReportRow,
    ReportFilterOptions,
    ReportOperationFilterOption,
    ReportWorkerFilterOption,
    ProductTimeOperationReportRow,
    ProductTimeReport,
    ProductTimeReportSection,
)
from app.schemas.timer import TimerType
from app.services.timer_service import TIMER_TYPE_TO_CODE
from app.services.xlsx_writer import XlsxDuration, XlsxTotal, build_xlsx

MAX_REPORT_PERIOD_DAYS = 366


@dataclass(slots=True)
class _ProductQuantityBucket:
    product_id: int
    product_name: str
    month_quantities: defaultdict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    day_quantities: defaultdict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )


@dataclass(slots=True)
class _TimeRowBucket:
    operation_id: int | None
    operation_name: str
    worker_user_id: int
    worker_user_name: str
    elapsed_by_day: defaultdict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    order_ids_by_day: defaultdict[str, set[int]] = field(
        default_factory=lambda: defaultdict(set)
    )
    order_ids: set[int] = field(default_factory=set)
    total_elapsed_ms: int = 0


@dataclass(slots=True)
class _TimeProductBucket:
    product_id: int
    product_name: str
    rows: dict[tuple[int | None, int], _TimeRowBucket] = field(default_factory=dict)
    elapsed_by_day: defaultdict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    order_ids_by_day: defaultdict[str, set[int]] = field(
        default_factory=lambda: defaultdict(set)
    )
    order_ids: set[int] = field(default_factory=set)
    total_elapsed_ms: int = 0


@dataclass(slots=True)
class _BatchDetailBucket:
    operation_id: int | None
    operation_name: str
    operation_sort_order: int
    worker_user_id: int | None
    worker_user_name: str
    elapsed_ms: int = 0


class ReportService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_filter_options(self) -> ReportFilterOptions:
        historical_worker_ids = set(
            self.session.scalars(select(TimerSession.user_id).distinct()).all()
        )
        historical_worker_ids.update(
            self.session.scalars(
                select(WorkOrderAssignment.worker_user_id)
                .where(WorkOrderAssignment.worker_user_id.is_not(None))
                .distinct()
            ).all()
        )
        workers = [
            ReportWorkerFilterOption(
                id=user.id,
                name=user.name,
                is_active=user.is_active,
                is_deleted=user.deleted_at is not None,
            )
            for user in self.session.scalars(select(User)).all()
            if "worker" in user.roles or user.id in historical_worker_ids
        ]
        workers.sort(key=lambda item: (item.name.casefold(), item.id))

        operations = [
            ReportOperationFilterOption(
                id=operation.id,
                name=operation.name,
                is_active=operation.is_active,
            )
            for operation in self.session.scalars(
                select(OperationCatalogEntry)
            ).all()
        ]
        operations.sort(key=lambda item: (item.name.casefold(), item.id))

        return ReportFilterOptions(workers=workers, operations=operations)

    def get_product_quantity_report(
        self,
        date_from: date,
        date_to: date,
        product_id: int | None = None,
    ) -> ProductQuantityReport:
        self._validate_period(date_from, date_to)
        start_ts = self._date_start_ts(date_from)
        end_ts = self._date_start_ts(date_to + timedelta(days=1))
        stmt = (
            select(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                WorkOrder.quantity,
                WorkOrder.completed_at,
            )
            .select_from(WorkOrder)
            .join(Product, Product.id == WorkOrder.product_id)
            .where(WorkOrder.completed_at.is_not(None))
            .where(WorkOrder.deleted_at.is_(None))
            .where(WorkOrder.completed_at >= start_ts)
            .where(WorkOrder.completed_at < end_ts)
        )
        if product_id is not None:
            stmt = stmt.where(Product.id == product_id)

        buckets: dict[int, _ProductQuantityBucket] = {}
        for row in self.session.execute(stmt).all():
            completed_date = datetime.fromtimestamp(
                row.completed_at / 1000,
                UTC,
            ).date()
            day_key = completed_date.isoformat()
            month_key = day_key[:7]
            bucket = buckets.setdefault(
                row.product_id,
                _ProductQuantityBucket(
                    product_id=row.product_id,
                    product_name=row.product_name,
                ),
            )
            bucket.month_quantities[month_key] += row.quantity
            bucket.day_quantities[day_key] += row.quantity

        months = self._month_keys(date_from, date_to)
        days = self._date_keys(date_from, date_to)
        items = [
            ProductQuantityReportRow(
                product_id=bucket.product_id,
                product_name=bucket.product_name,
                month_quantities=[bucket.month_quantities[key] for key in months],
                day_quantities=[bucket.day_quantities[key] for key in days],
                total_quantity=sum(bucket.day_quantities.values()),
            )
            for bucket in sorted(
                buckets.values(),
                key=lambda item: (item.product_name.casefold(), item.product_id),
            )
        ]

        return ProductQuantityReport(
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            months=months,
            days=days,
            items=items,
            total_by_month=[
                sum(item.month_quantities[index] for item in items)
                for index in range(len(months))
            ],
            total_by_day=[
                sum(item.day_quantities[index] for item in items)
                for index in range(len(days))
            ],
            total_quantity=sum(item.total_quantity for item in items),
        )

    def get_product_time_report(
        self,
        date_from: date,
        date_to: date,
        product_id: int | None = None,
        worker_user_id: int | None = None,
        order_number: str | None = None,
    ) -> ProductTimeReport:
        self._validate_period(date_from, date_to)
        operation_name = func.coalesce(
            OperationCatalogEntry.name,
            Operation.name,
            "Операция удалена",
        )
        stmt = (
            select(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                WorkOrder.id.label("order_id"),
                WorkOrder.quantity,
                WorkShift.business_date,
                TimerSession.operation_id,
                operation_name.label("operation_name"),
                User.id.label("worker_user_id"),
                User.name.label("worker_user_name"),
                func.sum(TimerSession.ended_at - TimerSession.started_at).label(
                    "elapsed_ms"
                ),
            )
            .select_from(TimerSession)
            .join(WorkShift, WorkShift.id == TimerSession.shift_id)
            .join(User, User.id == TimerSession.user_id)
            .join(WorkOrder, WorkOrder.id == TimerSession.order_id)
            .join(Product, Product.id == WorkOrder.product_id)
            .outerjoin(Operation, Operation.id == TimerSession.operation_id)
            .outerjoin(
                OperationCatalogEntry,
                OperationCatalogEntry.id == Operation.operation_catalog_entry_id,
            )
            .where(
                TimerSession.timer_type_code == TIMER_TYPE_TO_CODE[TimerType.OPERATION]
            )
            .where(TimerSession.ended_at.is_not(None))
            .where(WorkOrder.deleted_at.is_(None))
            .where(WorkShift.business_date >= date_from.isoformat())
            .where(WorkShift.business_date <= date_to.isoformat())
            .group_by(
                Product.id,
                Product.name,
                WorkOrder.id,
                WorkOrder.quantity,
                WorkShift.business_date,
                TimerSession.operation_id,
                OperationCatalogEntry.name,
                Operation.name,
                User.id,
                User.name,
            )
        )
        if product_id is not None:
            stmt = stmt.where(Product.id == product_id)
        if worker_user_id is not None:
            stmt = stmt.where(User.id == worker_user_id)
        normalized_order_number = (order_number or "").strip().casefold()
        if normalized_order_number:
            stmt = stmt.where(
                func.lower(WorkOrder.order_number).contains(normalized_order_number)
            )

        products: dict[int, _TimeProductBucket] = {}
        order_quantities: dict[int, int] = {}
        for row in self.session.execute(stmt).all():
            order_quantities[row.order_id] = row.quantity
            product = products.setdefault(
                row.product_id,
                _TimeProductBucket(
                    product_id=row.product_id,
                    product_name=row.product_name,
                ),
            )
            row_key = (row.operation_id, row.worker_user_id)
            detail = product.rows.setdefault(
                row_key,
                _TimeRowBucket(
                    operation_id=row.operation_id,
                    operation_name=row.operation_name,
                    worker_user_id=row.worker_user_id,
                    worker_user_name=row.worker_user_name,
                ),
            )
            elapsed_ms = int(row.elapsed_ms)
            detail.elapsed_by_day[row.business_date] += elapsed_ms
            detail.order_ids_by_day[row.business_date].add(row.order_id)
            detail.order_ids.add(row.order_id)
            detail.total_elapsed_ms += elapsed_ms
            product.elapsed_by_day[row.business_date] += elapsed_ms
            product.order_ids_by_day[row.business_date].add(row.order_id)
            product.order_ids.add(row.order_id)
            product.total_elapsed_ms += elapsed_ms

        days = self._date_keys(date_from, date_to)
        sections: list[ProductTimeReportSection] = []
        for product in sorted(
            products.values(),
            key=lambda item: (item.product_name.casefold(), item.product_id),
        ):
            detail_rows = [
                ProductTimeOperationReportRow(
                    operation_id=detail.operation_id,
                    operation_name=detail.operation_name,
                    worker_user_id=detail.worker_user_id,
                    worker_user_name=detail.worker_user_name,
                    daily_average_ms=[
                        self._average_for_orders(
                            detail.elapsed_by_day[day_key],
                            detail.order_ids_by_day[day_key],
                            order_quantities,
                        )
                        for day_key in days
                    ],
                    average_ms=self._average_for_orders(
                        detail.total_elapsed_ms,
                        detail.order_ids,
                        order_quantities,
                    ),
                    total_elapsed_ms=detail.total_elapsed_ms,
                    share_of_product_time=(
                        detail.total_elapsed_ms / product.total_elapsed_ms
                        if product.total_elapsed_ms
                        else 0.0
                    ),
                )
                for detail in sorted(
                    product.rows.values(),
                    key=lambda item: (
                        item.operation_name.casefold(),
                        item.worker_user_name.casefold(),
                        item.worker_user_id,
                    ),
                )
            ]
            sections.append(
                ProductTimeReportSection(
                    product_id=product.product_id,
                    product_name=product.product_name,
                    rows=detail_rows,
                    daily_average_ms=[
                        self._average_for_orders(
                            product.elapsed_by_day[day_key],
                            product.order_ids_by_day[day_key],
                            order_quantities,
                        )
                        for day_key in days
                    ],
                    average_ms=self._average_for_orders(
                        product.total_elapsed_ms,
                        product.order_ids,
                        order_quantities,
                    ),
                    total_elapsed_ms=product.total_elapsed_ms,
                )
            )

        return ProductTimeReport(
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            days=days,
            products=sections,
        )

    def get_order_batch_report(
        self,
        date_from: date,
        date_to: date,
        product_id: int | None = None,
        worker_user_id: int | None = None,
        operation_catalog_entry_id: int | None = None,
        order_number: str | None = None,
        page: int | None = 1,
        page_size: int | None = 20,
    ) -> OrderBatchReport:
        self._validate_period(date_from, date_to)
        start_ts = self._date_start_ts(date_from)
        end_ts = self._date_start_ts(date_to + timedelta(days=1))
        conditions = [
            WorkOrder.completed_at.is_not(None),
            WorkOrder.deleted_at.is_(None),
            WorkOrder.completed_at >= start_ts,
            WorkOrder.completed_at < end_ts,
        ]
        if product_id is not None:
            conditions.append(WorkOrder.product_id == product_id)
        normalized_order_number = (order_number or "").strip().casefold()
        if normalized_order_number:
            conditions.append(
                func.lower(WorkOrder.order_number).contains(normalized_order_number)
            )
        if worker_user_id is not None or operation_catalog_entry_id is not None:
            assignment_match = (
                select(WorkOrderAssignment.id)
                .join(Operation, Operation.id == WorkOrderAssignment.operation_id)
                .where(WorkOrderAssignment.work_order_id == WorkOrder.id)
            )
            timer_match = (
                select(TimerSession.id)
                .outerjoin(Operation, Operation.id == TimerSession.operation_id)
                .where(TimerSession.order_id == WorkOrder.id)
                .where(
                    TimerSession.timer_type_code
                    == TIMER_TYPE_TO_CODE[TimerType.OPERATION]
                )
                .where(TimerSession.ended_at.is_not(None))
            )
            if worker_user_id is not None:
                assignment_match = assignment_match.where(
                    WorkOrderAssignment.worker_user_id == worker_user_id
                )
                timer_match = timer_match.where(TimerSession.user_id == worker_user_id)
            if operation_catalog_entry_id is not None:
                assignment_match = assignment_match.where(
                    Operation.operation_catalog_entry_id == operation_catalog_entry_id
                )
                timer_match = timer_match.where(
                    Operation.operation_catalog_entry_id == operation_catalog_entry_id
                )
            conditions.append(or_(exists(assignment_match), exists(timer_match)))

        total = (
            self.session.scalar(select(func.count(WorkOrder.id)).where(*conditions))
            or 0
        )
        stmt = (
            select(
                WorkOrder.id.label("order_id"),
                WorkOrder.order_number,
                WorkOrder.quantity,
                WorkOrder.defect_quantity,
                WorkOrder.completed_at,
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                LeatherType.name.label("leather_type_name"),
            )
            .select_from(WorkOrder)
            .join(Product, Product.id == WorkOrder.product_id)
            .outerjoin(LeatherType, LeatherType.id == WorkOrder.leather_type_id)
            .where(*conditions)
            .order_by(WorkOrder.completed_at.desc(), WorkOrder.id.desc())
        )
        if page is not None and page_size is not None:
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        order_rows = self.session.execute(stmt).all()
        submitted_quantities = {
            row.order_id: max(row.quantity - row.defect_quantity, 0)
            for row in order_rows
        }
        details_by_order = self._get_batch_details(
            submitted_quantities,
            worker_user_id,
            operation_catalog_entry_id,
        )
        items: list[OrderBatchReportItem] = []
        for row in order_rows:
            details = details_by_order.get(row.order_id, [])
            total_elapsed_ms = sum(item.elapsed_ms for item in details)
            items.append(
                OrderBatchReportItem(
                    order_id=row.order_id,
                    order_number=row.order_number,
                    product_id=row.product_id,
                    product_name=row.product_name,
                    leather_type_name=row.leather_type_name,
                    quantity=row.quantity,
                    submitted_quantity=submitted_quantities[row.order_id],
                    completed_at=row.completed_at,
                    total_elapsed_ms=total_elapsed_ms,
                    average_ms=(
                        total_elapsed_ms // submitted_quantities[row.order_id]
                        if submitted_quantities[row.order_id] > 0
                        else 0
                    ),
                    details=details,
                )
            )

        effective_page = page or 1
        effective_page_size = page_size or max(total, 1)
        pages = (
            max(1, (total + effective_page_size - 1) // effective_page_size)
            if page is not None and page_size is not None
            else 1
        )
        return OrderBatchReport(
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            items=items,
            total=total,
            page=effective_page,
            page_size=effective_page_size,
            pages=pages,
        )

    def _get_batch_details(
        self,
        submitted_quantities: dict[int, int],
        worker_user_id: int | None,
        operation_catalog_entry_id: int | None,
    ) -> dict[int, list[OrderBatchReportDetail]]:
        if not submitted_quantities:
            return {}
        order_ids = list(submitted_quantities)
        operation_name = func.coalesce(
            OperationCatalogEntry.name,
            Operation.name,
            "Операция удалена",
        )
        assignment_stmt = (
            select(
                WorkOrderAssignment.work_order_id,
                Operation.id.label("operation_id"),
                operation_name.label("operation_name"),
                Operation.sort_order.label("operation_sort_order"),
                User.id.label("worker_user_id"),
                User.name.label("worker_user_name"),
            )
            .select_from(WorkOrderAssignment)
            .join(Operation, Operation.id == WorkOrderAssignment.operation_id)
            .outerjoin(
                OperationCatalogEntry,
                OperationCatalogEntry.id == Operation.operation_catalog_entry_id,
            )
            .outerjoin(User, User.id == WorkOrderAssignment.worker_user_id)
            .where(WorkOrderAssignment.work_order_id.in_(order_ids))
        )
        if worker_user_id is not None:
            assignment_stmt = assignment_stmt.where(
                WorkOrderAssignment.worker_user_id == worker_user_id
            )
        if operation_catalog_entry_id is not None:
            assignment_stmt = assignment_stmt.where(
                Operation.operation_catalog_entry_id == operation_catalog_entry_id
            )

        buckets: dict[
            int,
            dict[tuple[int | None, int | None], _BatchDetailBucket],
        ] = defaultdict(dict)
        for row in self.session.execute(assignment_stmt).all():
            key = (row.operation_id, row.worker_user_id)
            buckets[row.work_order_id][key] = _BatchDetailBucket(
                operation_id=row.operation_id,
                operation_name=row.operation_name,
                operation_sort_order=row.operation_sort_order,
                worker_user_id=row.worker_user_id,
                worker_user_name=row.worker_user_name or "Не назначен",
            )

        timer_stmt = (
            select(
                TimerSession.order_id,
                TimerSession.operation_id,
                operation_name.label("operation_name"),
                Operation.sort_order.label("operation_sort_order"),
                User.id.label("worker_user_id"),
                User.name.label("worker_user_name"),
                func.sum(TimerSession.ended_at - TimerSession.started_at).label(
                    "elapsed_ms"
                ),
            )
            .select_from(TimerSession)
            .outerjoin(Operation, Operation.id == TimerSession.operation_id)
            .outerjoin(
                OperationCatalogEntry,
                OperationCatalogEntry.id == Operation.operation_catalog_entry_id,
            )
            .join(User, User.id == TimerSession.user_id)
            .where(TimerSession.order_id.in_(order_ids))
            .where(
                TimerSession.timer_type_code == TIMER_TYPE_TO_CODE[TimerType.OPERATION]
            )
            .where(TimerSession.ended_at.is_not(None))
            .group_by(
                TimerSession.order_id,
                TimerSession.operation_id,
                OperationCatalogEntry.name,
                Operation.name,
                Operation.sort_order,
                User.id,
                User.name,
            )
        )
        if worker_user_id is not None:
            timer_stmt = timer_stmt.where(TimerSession.user_id == worker_user_id)
        if operation_catalog_entry_id is not None:
            timer_stmt = timer_stmt.where(
                Operation.operation_catalog_entry_id == operation_catalog_entry_id
            )
        for row in self.session.execute(timer_stmt).all():
            key = (row.operation_id, row.worker_user_id)
            detail = buckets[row.order_id].setdefault(
                key,
                _BatchDetailBucket(
                    operation_id=row.operation_id,
                    operation_name=row.operation_name,
                    operation_sort_order=row.operation_sort_order or 0,
                    worker_user_id=row.worker_user_id,
                    worker_user_name=row.worker_user_name,
                ),
            )
            detail.elapsed_ms += int(row.elapsed_ms)

        result: dict[int, list[OrderBatchReportDetail]] = {}
        for order_id, order_buckets in buckets.items():
            result[order_id] = [
                OrderBatchReportDetail(
                    operation_id=detail.operation_id,
                    operation_name=detail.operation_name,
                    worker_user_id=detail.worker_user_id,
                    worker_user_name=detail.worker_user_name,
                    elapsed_ms=detail.elapsed_ms,
                    average_ms=(
                        detail.elapsed_ms // submitted_quantities[order_id]
                        if submitted_quantities[order_id] > 0
                        else 0
                    ),
                )
                for detail in sorted(
                    order_buckets.values(),
                    key=lambda item: (
                        item.operation_sort_order,
                        item.operation_name.casefold(),
                        item.worker_user_name.casefold(),
                        item.worker_user_id or 0,
                    ),
                )
            ]
        return result

    def build_product_quantity_xlsx(
        self,
        date_from: date,
        date_to: date,
        product_id: int | None = None,
    ) -> tuple[bytes, str]:
        report = self.get_product_quantity_report(date_from, date_to, product_id)
        monthly_rows: list[list[str | int | float | None]] = [
            ["Изделие", *report.months, "Итого"]
        ]
        monthly_rows.extend(
            [item.product_name, *item.month_quantities, item.total_quantity]
            for item in report.items
        )
        monthly_rows.append(["Итого", *report.total_by_month, report.total_quantity])
        daily_rows: list[list[str | int | float | None]] = [
            ["Изделие", *report.days, "Итого"]
        ]
        daily_rows.extend(
            [item.product_name, *item.day_quantities, item.total_quantity]
            for item in report.items
        )
        daily_rows.append(["Итого", *report.total_by_day, report.total_quantity])
        filename = f"flowcraft-products-{report.date_from}_{report.date_to}.xlsx"
        return (
            build_xlsx(
                [("По месяцам", monthly_rows), ("По дням", daily_rows)],
                auto_width=True,
                freeze_header=True,
            ),
            filename,
        )

    def build_product_time_xlsx(
        self,
        date_from: date,
        date_to: date,
        product_id: int | None = None,
        worker_user_id: int | None = None,
        order_number: str | None = None,
    ) -> tuple[bytes, str]:
        report = self.get_product_time_report(
            date_from,
            date_to,
            product_id,
            worker_user_id,
            order_number,
        )
        rows: list[list[str | int | float | XlsxDuration | None]] = [
            [
                "Изделие",
                "Операция",
                "Исполнитель",
                *report.days,
                "Среднее за период",
                "% от общего времени",
            ]
        ]
        for product in report.products:
            rows.extend(
                [
                    product.product_name,
                    item.operation_name,
                    item.worker_user_name,
                    *[
                        XlsxDuration(milliseconds=value)
                        for value in item.daily_average_ms
                    ],
                    XlsxDuration(milliseconds=item.average_ms),
                    round(item.share_of_product_time * 100, 2),
                ]
                for item in product.rows
            )
            rows.append(
                [
                    product.product_name,
                    "Итого",
                    "",
                    *[
                        XlsxDuration(milliseconds=value)
                        for value in product.daily_average_ms
                    ],
                    XlsxDuration(milliseconds=product.average_ms),
                    100,
                ]
            )
        filename = f"flowcraft-product-time-{report.date_from}_{report.date_to}.xlsx"
        return (
            build_xlsx(
                [("Время по операциям", rows)],
                auto_width=True,
                freeze_header=True,
            ),
            filename,
        )

    def build_order_batch_xlsx(
        self,
        date_from: date,
        date_to: date,
        product_id: int | None = None,
        worker_user_id: int | None = None,
        operation_catalog_entry_id: int | None = None,
        order_number: str | None = None,
    ) -> tuple[bytes, str]:
        report = self.get_order_batch_report(
            date_from,
            date_to,
            product_id,
            worker_user_id,
            operation_catalog_entry_id,
            order_number,
            page=None,
            page_size=None,
        )
        rows: list[list[str | int | XlsxDuration | XlsxTotal | None]] = [
            [
                "Партия",
                "ФИО",
                "Изделие / вид кожи",
                "Операция",
                "Сдано, шт.",
                "Затрачено времени",
                "Время на 1 шт.",
            ]
        ]
        for item in report.items:
            product_label = item.product_name
            if item.leather_type_name:
                product_label = f"{product_label} / {item.leather_type_name}"
            rows.append(
                [
                    XlsxTotal(item.order_number),
                    XlsxTotal("Общее время"),
                    XlsxTotal(product_label),
                    XlsxTotal(""),
                    XlsxTotal(item.submitted_quantity),
                    XlsxTotal(XlsxDuration(item.total_elapsed_ms)),
                    XlsxTotal(XlsxDuration(item.average_ms)),
                ]
            )
            rows.extend(
                [
                    item.order_number,
                    detail.worker_user_name,
                    product_label,
                    detail.operation_name,
                    item.submitted_quantity,
                    XlsxDuration(detail.elapsed_ms),
                    XlsxDuration(detail.average_ms),
                ]
                for detail in item.details
            )
            rows.append([None, None, None, None, None, None, None])
        filename = f"flowcraft-order-batches-{report.date_from}_{report.date_to}.xlsx"
        return (
            build_xlsx(
                [("По партиям", rows)],
                auto_width=True,
                freeze_header=True,
            ),
            filename,
        )

    def _validate_period(self, date_from: date, date_to: date) -> None:
        if date_from > date_to:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Дата начала периода не должна быть позже даты окончания.",
            )
        if (date_to - date_from).days + 1 > MAX_REPORT_PERIOD_DAYS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Период отчета не должен превышать {MAX_REPORT_PERIOD_DAYS} дней."
                ),
            )

    def _average_for_orders(
        self,
        elapsed_ms: int,
        order_ids: set[int],
        order_quantities: dict[int, int],
    ) -> int:
        quantity = sum(order_quantities[order_id] for order_id in order_ids)
        return elapsed_ms // quantity if quantity > 0 else 0

    def _date_start_ts(self, value: date) -> int:
        return int(datetime.combine(value, datetime.min.time(), UTC).timestamp() * 1000)

    def _date_keys(self, date_from: date, date_to: date) -> list[str]:
        return [
            (date_from + timedelta(days=offset)).isoformat()
            for offset in range((date_to - date_from).days + 1)
        ]

    def _month_keys(self, date_from: date, date_to: date) -> list[str]:
        keys: list[str] = []
        current = date(date_from.year, date_from.month, 1)
        end = date(date_to.year, date_to.month, 1)
        while current <= end:
            keys.append(current.strftime("%Y-%m"))
            current = (
                date(current.year + 1, 1, 1)
                if current.month == 12
                else date(current.year, current.month + 1, 1)
            )
        return keys

from calendar import monthrange
from collections import defaultdict
from datetime import date
from typing import TypedDict

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.planning import (
    PlanningOperationResult,
    PlanningOrderResult,
    PlanningRun,
    PlanningWorkerDayAllocation,
    ProductionPlanningState,
)
from app.models.product import Product
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.planning import (
    PlanningAllocationRead,
    PlanningOperationForecastRead,
    PlanningOrderForecastDetailRead,
    PlanningOrderForecastRead,
    PlanningWorkloadItemRead,
    PlanningWorkloadRead,
    ProductionPlanningStatusRead,
)
from app.services.planning_revision_service import PlanningRevisionService


class _WorkloadAggregate(TypedDict):
    planned_seconds: int
    remaining_seconds: int
    order_ids: set[int]
    deficit_seconds: int


class PlanningResultsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_status(self) -> ProductionPlanningStatusRead:
        state = self.session.get(ProductionPlanningState, 1)
        if state is None:
            return ProductionPlanningStatusRead(
                calculation_status="idle",
                input_revision=0,
                requested_revision=0,
                running_revision=None,
                active_run_id=None,
                active_revision=None,
                active_completed_at=None,
                is_stale=False,
            )
        active_run = (
            self.session.get(PlanningRun, state.active_run_id)
            if state.active_run_id is not None
            else None
        )
        active_revision = active_run.input_revision if active_run is not None else None
        return ProductionPlanningStatusRead(
            calculation_status=state.calculation_status,
            input_revision=state.input_revision,
            requested_revision=state.requested_revision,
            running_revision=state.running_revision,
            active_run_id=state.active_run_id,
            active_revision=active_revision,
            active_completed_at=(
                active_run.completed_at if active_run is not None else None
            ),
            is_stale=(
                active_revision is None or active_revision < state.input_revision
            ),
        )

    def request_recalculation(self) -> ProductionPlanningStatusRead:
        PlanningRevisionService(self.session).request_recalculation()
        self.session.commit()
        return self.get_status()

    def list_order_forecasts(self) -> list[PlanningOrderForecastRead]:
        active_run_id = self._active_run_id()
        if active_run_id is None:
            return []
        rows = self.session.execute(
            select(
                PlanningOrderResult,
                WorkOrder.order_number,
                Product.name,
                WorkOrder.planned_completion_date,
            )
            .join(WorkOrder, WorkOrder.id == PlanningOrderResult.order_id)
            .join(Product, Product.id == WorkOrder.product_id)
            .where(PlanningOrderResult.run_id == active_run_id)
            .order_by(
                WorkOrder.planning_priority_rank.asc(),
                WorkOrder.id.asc(),
            )
        ).all()
        return [
            self._serialize_order_result(
                result,
                order_number,
                product_name,
                manual_completion_date,
            )
            for result, order_number, product_name, manual_completion_date in rows
        ]

    def get_order_forecast(self, order_id: int) -> PlanningOrderForecastDetailRead:
        active_run_id = self._active_run_id()
        if active_run_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Расчёт планирования ещё не опубликован.",
            )
        row = self.session.execute(
            select(
                PlanningOrderResult,
                WorkOrder.order_number,
                Product.name,
                WorkOrder.planned_completion_date,
            )
            .join(WorkOrder, WorkOrder.id == PlanningOrderResult.order_id)
            .join(Product, Product.id == WorkOrder.product_id)
            .where(
                PlanningOrderResult.run_id == active_run_id,
                PlanningOrderResult.order_id == order_id,
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Заказ отсутствует в активном расчёте планирования.",
            )
        order_result, order_number, product_name, manual_completion_date = row
        operation_rows = self.session.execute(
            select(PlanningOperationResult, Operation)
            .join(Operation, Operation.id == PlanningOperationResult.operation_id)
            .where(
                PlanningOperationResult.run_id == active_run_id,
                PlanningOperationResult.order_id == order_id,
            )
            .order_by(
                PlanningOperationResult.stage_start.asc(),
                Operation.sort_order.asc(),
                Operation.id.asc(),
            )
        ).all()
        allocation_rows = self.session.execute(
            select(PlanningWorkerDayAllocation, User.name)
            .join(User, User.id == PlanningWorkerDayAllocation.user_id)
            .where(
                PlanningWorkerDayAllocation.run_id == active_run_id,
                PlanningWorkerDayAllocation.order_id == order_id,
            )
            .order_by(
                PlanningWorkerDayAllocation.work_date.asc(),
                PlanningWorkerDayAllocation.operation_id.asc(),
                PlanningWorkerDayAllocation.user_id.asc(),
            )
        ).all()
        base = self._serialize_order_result(
            order_result,
            order_number,
            product_name,
            manual_completion_date,
        )
        return PlanningOrderForecastDetailRead(
            **base.model_dump(),
            operations=[
                PlanningOperationForecastRead(
                    operation_id=result.operation_id,
                    operation_name=operation.name,
                    stage_start=result.stage_start,
                    stage_end=result.stage_end,
                    standard_time_seconds=result.standard_time_seconds,
                    standard_time_source=result.standard_time_source or "missing",
                    workload_seconds=result.workload_seconds,
                    actual_seconds=result.actual_seconds,
                    remaining_seconds=result.remaining_seconds,
                    preparation_seconds=result.preparation_seconds,
                    first_planned_date=result.first_planned_date,
                    last_planned_date=result.last_planned_date,
                    status=result.status,
                    issue_codes=list(result.issue_codes),
                )
                for result, operation in operation_rows
            ],
            allocations=[
                PlanningAllocationRead(
                    user_id=allocation.user_id,
                    user_name=user_name,
                    work_date=allocation.work_date,
                    operation_id=allocation.operation_id,
                    work_seconds=allocation.work_seconds,
                    preparation_seconds=allocation.preparation_seconds,
                )
                for allocation, user_name in allocation_rows
            ],
        )

    def get_workload(self, month: str) -> PlanningWorkloadRead:
        month_start, month_end = self._parse_month(month)
        active_run_id = self._active_run_id()
        if active_run_id is None:
            return PlanningWorkloadRead(
                month=month,
                active_run_id=None,
                items=[],
            )
        operation_rows = self.session.execute(
            select(
                PlanningOperationResult,
                Operation.operation_catalog_entry_id,
                Operation.name,
            )
            .join(Operation, Operation.id == PlanningOperationResult.operation_id)
            .where(PlanningOperationResult.run_id == active_run_id)
        ).all()
        allocation_rows = self.session.execute(
            select(
                PlanningWorkerDayAllocation,
                Operation.operation_catalog_entry_id,
                Operation.name,
            )
            .join(
                Operation,
                Operation.id == PlanningWorkerDayAllocation.operation_id,
            )
            .where(PlanningWorkerDayAllocation.run_id == active_run_id)
        ).all()
        catalog_names = {
            entry.id: entry.name
            for entry in self.session.scalars(select(OperationCatalogEntry)).all()
        }
        grouped: dict[tuple[int | None, str], _WorkloadAggregate] = {}
        allocated_by_task: dict[tuple[int, int], int] = defaultdict(int)
        for allocation, catalog_entry_id, operation_name in allocation_rows:
            allocated_by_task[(allocation.order_id, allocation.operation_id)] += (
                allocation.work_seconds + allocation.preparation_seconds
            )
            if not month_start <= allocation.work_date <= month_end:
                continue
            name = catalog_names.get(catalog_entry_id, operation_name)
            values = grouped.setdefault(
                (catalog_entry_id, name),
                {
                    "planned_seconds": 0,
                    "remaining_seconds": 0,
                    "order_ids": set(),
                    "deficit_seconds": 0,
                },
            )
            values["planned_seconds"] += (
                allocation.work_seconds + allocation.preparation_seconds
            )
        for result, catalog_entry_id, operation_name in operation_rows:
            name = catalog_names.get(catalog_entry_id, operation_name)
            values = grouped.setdefault(
                (catalog_entry_id, name),
                {
                    "planned_seconds": 0,
                    "remaining_seconds": 0,
                    "order_ids": set(),
                    "deficit_seconds": 0,
                },
            )
            values["remaining_seconds"] += (
                result.remaining_seconds + result.preparation_seconds
            )
            values["order_ids"].add(result.order_id)
            if result.status == "unplanned":
                allocated = allocated_by_task[(result.order_id, result.operation_id)]
                values["deficit_seconds"] += max(
                    result.remaining_seconds + result.preparation_seconds - allocated,
                    0,
                )
        items = [
            PlanningWorkloadItemRead(
                operation_catalog_entry_id=catalog_entry_id,
                operation_name=operation_name,
                planned_seconds=values["planned_seconds"],
                remaining_seconds=values["remaining_seconds"],
                orders_count=len(values["order_ids"]),
                deficit_seconds=values["deficit_seconds"],
            )
            for (catalog_entry_id, operation_name), values in sorted(
                grouped.items(),
                key=lambda item: (item[0][1].casefold(), item[0][0] or 0),
            )
        ]
        return PlanningWorkloadRead(
            month=month,
            active_run_id=active_run_id,
            items=items,
        )

    def _serialize_order_result(
        self,
        result: PlanningOrderResult,
        order_number: str,
        product_name: str,
        manual_completion_date: date | None,
    ) -> PlanningOrderForecastRead:
        return PlanningOrderForecastRead(
            order_id=result.order_id,
            order_number=order_number,
            product_name=product_name,
            manual_completion_date=manual_completion_date,
            resource_finish_date=result.resource_finish_date,
            calculated_finish_date=result.calculated_finish_date,
            status=result.status,
            issue_codes=list(result.issue_codes),
        )

    def _active_run_id(self) -> int | None:
        state = self.session.get(ProductionPlanningState, 1)
        return state.active_run_id if state is not None else None

    def _parse_month(self, month: str) -> tuple[date, date]:
        try:
            month_start = date.fromisoformat(f"{month}-01")
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Месяц должен быть указан в формате ГГГГ-ММ.",
            ) from error
        month_end = month_start.replace(
            day=monthrange(month_start.year, month_start.month)[1]
        )
        return month_start, month_end


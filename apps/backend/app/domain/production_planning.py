from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class PlanningTaskInput:
    operation_id: int
    operation_name: str
    stage_start: int
    stage_end: int
    workload_seconds: int | None
    actual_seconds: int
    eligible_worker_ids: tuple[int, ...]
    standard_time_seconds: int | None = None
    standard_time_source: str = "missing"
    missing_time_issue: str = "missing_standard_time"


@dataclass(frozen=True)
class PlanningOrderInput:
    order_id: int
    priority_rank: int
    stage_count: int
    is_quality_control: bool
    tasks: tuple[PlanningTaskInput, ...]


@dataclass(frozen=True)
class PlanningInput:
    today: date
    horizon_end: date
    display_offset_days: int
    preparation_seconds: int
    orders: tuple[PlanningOrderInput, ...]
    worker_availability: dict[tuple[int, date], int]


@dataclass(frozen=True)
class PlannedAllocation:
    user_id: int
    work_date: date
    order_id: int
    operation_id: int
    work_seconds: int
    preparation_seconds: int


@dataclass(frozen=True)
class PlannedOperationResult:
    order_id: int
    operation_id: int
    stage_start: int
    stage_end: int
    workload_seconds: int
    actual_seconds: int
    remaining_seconds: int
    preparation_seconds: int
    first_planned_date: date | None
    last_planned_date: date | None
    status: str
    issue_codes: tuple[str, ...]
    standard_time_seconds: int | None = None
    standard_time_source: str = "missing"


@dataclass(frozen=True)
class PlannedOrderResult:
    order_id: int
    resource_finish_date: date | None
    calculated_finish_date: date | None
    status: str
    issue_codes: tuple[str, ...]


@dataclass(frozen=True)
class PlanningOutput:
    orders: tuple[PlannedOrderResult, ...]
    operations: tuple[PlannedOperationResult, ...]
    allocations: tuple[PlannedAllocation, ...]


@dataclass
class _MutableTaskResult:
    input: PlanningTaskInput
    workload_seconds: int
    actual_seconds: int
    remaining_seconds: int
    preparation_seconds: int
    first_planned_date: date | None = None
    last_planned_date: date | None = None
    status: str = "pending"
    issue_codes: list[str] = field(default_factory=list)


class ProductionPlanningCalculator:
    def calculate(
        self,
        planning_input: PlanningInput,
        progress_callback: Callable[[int], None] | None = None,
    ) -> PlanningOutput:
        remaining_availability = dict(planning_input.worker_availability)
        initial_availability = dict(planning_input.worker_availability)
        order_results: list[PlannedOrderResult] = []
        operation_results: list[PlannedOperationResult] = []
        allocations: list[PlannedAllocation] = []

        sorted_orders = sorted(
            planning_input.orders,
            key=lambda item: (item.priority_rank, item.order_id),
        )
        for index, order in enumerate(sorted_orders, start=1):
            order_result, task_results, task_allocations = self._plan_order(
                planning_input,
                order,
                remaining_availability,
                initial_availability,
            )
            order_results.append(order_result)
            operation_results.extend(task_results)
            allocations.extend(task_allocations)
            if progress_callback is not None:
                progress_callback(index)

        return PlanningOutput(
            orders=tuple(order_results),
            operations=tuple(operation_results),
            allocations=tuple(allocations),
        )

    def _plan_order(
        self,
        planning_input: PlanningInput,
        order: PlanningOrderInput,
        remaining_availability: dict[tuple[int, date], int],
        initial_availability: dict[tuple[int, date], int],
    ) -> tuple[
        PlannedOrderResult,
        list[PlannedOperationResult],
        list[PlannedAllocation],
    ]:
        resource_finish: date | None
        calculated_finish: date | None
        if order.is_quality_control:
            resource_finish = planning_input.today
            return (
                PlannedOrderResult(
                    order_id=order.order_id,
                    resource_finish_date=resource_finish,
                    calculated_finish_date=(
                        resource_finish
                        + timedelta(days=planning_input.display_offset_days)
                    ),
                    status="quality_control",
                    issue_codes=(),
                ),
                [],
                [],
            )

        if not order.tasks:
            return (
                PlannedOrderResult(
                    order_id=order.order_id,
                    resource_finish_date=None,
                    calculated_finish_date=None,
                    status="unplanned",
                    issue_codes=("no_operations",),
                ),
                [],
                [],
            )

        mutable_results = {
            task.operation_id: self._initialize_task_result(
                task,
                planning_input.preparation_seconds,
            )
            for task in order.tasks
        }
        allocations: list[PlannedAllocation] = []
        barrier_completion: dict[int, date | None] = {0: planning_input.today}

        for stage in range(1, order.stage_count + 1):
            previous_barrier = barrier_completion.get(stage - 1)
            starting_tasks = [task for task in order.tasks if task.stage_start == stage]
            starting_tasks.sort(
                key=lambda task: self._task_sort_key(task, order.tasks)
            )
            for task in starting_tasks:
                result = mutable_results[task.operation_id]
                if result.status != "pending":
                    continue
                if previous_barrier is None:
                    result.status = "unplanned"
                    result.issue_codes.append("blocked_by_stage")
                    continue
                allocations.extend(
                    self._schedule_task(
                        planning_input=planning_input,
                        order_id=order.order_id,
                        result=result,
                        earliest_date=previous_barrier,
                        remaining_availability=remaining_availability,
                        initial_availability=initial_availability,
                    )
                )

            ending_results = [
                mutable_results[task.operation_id]
                for task in order.tasks
                if task.stage_end == stage
            ]
            if any(result.last_planned_date is None for result in ending_results):
                if any(
                    result.status not in {"completed", "planned"}
                    for result in ending_results
                ):
                    barrier_completion[stage] = None
                    continue
            completed_dates = [
                result.last_planned_date or planning_input.today
                for result in ending_results
                if result.status in {"completed", "planned"}
            ]
            candidates = [
                value
                for value in [previous_barrier, *completed_dates]
                if value is not None
            ]
            barrier_completion[stage] = max(candidates) if candidates else None

        final_results = [
            self._freeze_task_result(order.order_id, mutable_results[task.operation_id])
            for task in sorted(order.tasks, key=lambda item: item.operation_id)
        ]
        issue_codes = sorted(
            {
                issue
                for result in final_results
                for issue in result.issue_codes
            }
        )
        if issue_codes:
            resource_finish = None
            calculated_finish = None
            order_status = "unplanned"
        else:
            completion_dates = [
                result.last_planned_date or planning_input.today
                for result in final_results
            ]
            resource_finish = max(completion_dates, default=planning_input.today)
            calculated_finish = resource_finish + timedelta(
                days=planning_input.display_offset_days
            )
            order_status = "planned"
        return (
            PlannedOrderResult(
                order_id=order.order_id,
                resource_finish_date=resource_finish,
                calculated_finish_date=calculated_finish,
                status=order_status,
                issue_codes=tuple(issue_codes),
            ),
            final_results,
            allocations,
        )

    def _initialize_task_result(
        self,
        task: PlanningTaskInput,
        preparation_seconds: int,
    ) -> _MutableTaskResult:
        if task.workload_seconds is None:
            return _MutableTaskResult(
                input=task,
                workload_seconds=0,
                actual_seconds=task.actual_seconds,
                remaining_seconds=0,
                preparation_seconds=0,
                status="unplanned",
                issue_codes=[task.missing_time_issue],
            )
        remaining = max(task.workload_seconds - task.actual_seconds, 0)
        if remaining == 0:
            return _MutableTaskResult(
                input=task,
                workload_seconds=task.workload_seconds,
                actual_seconds=task.actual_seconds,
                remaining_seconds=0,
                preparation_seconds=0,
                status="completed",
            )
        return _MutableTaskResult(
            input=task,
            workload_seconds=task.workload_seconds,
            actual_seconds=task.actual_seconds,
            remaining_seconds=remaining,
            preparation_seconds=(
                preparation_seconds if task.actual_seconds == 0 else 0
            ),
        )

    def _schedule_task(
        self,
        *,
        planning_input: PlanningInput,
        order_id: int,
        result: _MutableTaskResult,
        earliest_date: date,
        remaining_availability: dict[tuple[int, date], int],
        initial_availability: dict[tuple[int, date], int],
    ) -> list[PlannedAllocation]:
        task = result.input
        if not task.eligible_worker_ids:
            result.status = "unplanned"
            result.issue_codes.append("no_skilled_worker")
            return []

        allocations: list[PlannedAllocation] = []
        preparation_remaining = result.preparation_seconds
        work_remaining = result.remaining_seconds
        current_date = max(earliest_date, planning_input.today)
        has_schedule = False
        while current_date <= planning_input.horizon_end:
            candidates = [
                user_id
                for user_id in task.eligible_worker_ids
                if remaining_availability.get((user_id, current_date), 0) > 0
            ]
            if any(
                initial_availability.get((user_id, current_date), 0) > 0
                for user_id in task.eligible_worker_ids
            ):
                has_schedule = True
            if not candidates:
                current_date += timedelta(days=1)
                continue
            user_id = min(
                candidates,
                key=lambda candidate_id: (
                    initial_availability.get((candidate_id, current_date), 0)
                    - remaining_availability.get((candidate_id, current_date), 0),
                    candidate_id,
                ),
            )
            available = remaining_availability[(user_id, current_date)]
            allocated_preparation = min(available, preparation_remaining)
            preparation_remaining -= allocated_preparation
            available -= allocated_preparation
            allocated_work = min(available, work_remaining)
            work_remaining -= allocated_work
            allocated_total = allocated_preparation + allocated_work
            remaining_availability[(user_id, current_date)] -= allocated_total
            if allocated_total > 0:
                result.first_planned_date = result.first_planned_date or current_date
                result.last_planned_date = current_date
                allocations.append(
                    PlannedAllocation(
                        user_id=user_id,
                        work_date=current_date,
                        order_id=order_id,
                        operation_id=task.operation_id,
                        work_seconds=allocated_work,
                        preparation_seconds=allocated_preparation,
                    )
                )
            if preparation_remaining == 0 and work_remaining == 0:
                result.status = "planned"
                return allocations
            current_date += timedelta(days=1)

        result.status = "unplanned"
        result.issue_codes.append(
            "outside_horizon" if has_schedule else "no_schedule"
        )
        return allocations

    def _task_sort_key(
        self,
        task: PlanningTaskInput,
        all_tasks: tuple[PlanningTaskInput, ...],
    ) -> tuple[int, int, int]:
        eligible_count = len(task.eligible_worker_ids)
        scarcity = eligible_count if eligible_count > 0 else 0
        critical_path = self._task_duration(task)
        final_stage = max(item.stage_end for item in all_tasks)
        for stage in range(task.stage_end + 1, final_stage + 1):
            critical_path += max(
                (
                    self._task_duration(item)
                    for item in all_tasks
                    if item.stage_end == stage
                ),
                default=0,
            )
        return scarcity, -critical_path, task.operation_id

    def _task_duration(self, task: PlanningTaskInput) -> int:
        if task.workload_seconds is None:
            return 0
        return max(task.workload_seconds - task.actual_seconds, 0)

    def _freeze_task_result(
        self,
        order_id: int,
        result: _MutableTaskResult,
    ) -> PlannedOperationResult:
        return PlannedOperationResult(
            order_id=order_id,
            operation_id=result.input.operation_id,
            stage_start=result.input.stage_start,
            stage_end=result.input.stage_end,
            workload_seconds=result.workload_seconds,
            actual_seconds=result.actual_seconds,
            remaining_seconds=result.remaining_seconds,
            preparation_seconds=result.preparation_seconds,
            first_planned_date=result.first_planned_date,
            last_planned_date=result.last_planned_date,
            status=result.status,
            issue_codes=tuple(sorted(set(result.issue_codes))),
            standard_time_seconds=result.input.standard_time_seconds,
            standard_time_source=result.input.standard_time_source,
        )

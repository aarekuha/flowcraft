from calendar import monthrange
from collections import defaultdict
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.production_planning import (
    PlanningInput,
    PlanningOrderInput,
    PlanningOutput,
    PlanningTaskInput,
    ProductionPlanningCalculator,
)
from app.models.operation import Operation
from app.models.planning import (
    PlanningOperationResult,
    PlanningOrderResult,
    PlanningRun,
    PlanningSettings,
    PlanningWorkerDayAllocation,
    ProductionPlanningState,
    UserWorkScheduleDay,
)
from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.user_operation_skill import UserOperationSkill
from app.models.work_order import (
    WorkOrder,
    WorkOrderAssignment,
)
from app.schemas.operation_catalog import OperationCatalogEntryKind
from app.schemas.order import WorkOrderProductionStage
from app.services.effective_order_time import (
    build_effective_operation_order_links_subquery,
    union_duration_seconds,
)
from app.services.operation_time_estimate_service import (
    OperationTimeEstimateService,
)
from app.services.planning_revision_service import PlanningRevisionService

ALGORITHM_VERSION = "resource-v1"
WORKER_STALE_AFTER_MS = 5 * 60 * 1000


class PlanningSnapshotBuilder:
    def __init__(self, session: Session) -> None:
        self.session = session

    def build(self, calculation_time: datetime) -> PlanningInput:
        now = calculation_time.astimezone(UTC)
        now_ts = int(now.timestamp() * 1000)
        today = now.date()
        settings = self.session.get(PlanningSettings, 1)
        display_offset_days = settings.display_offset_days if settings else 2
        preparation_seconds = settings.preparation_seconds if settings else 3600
        horizon_months = settings.horizon_months if settings else 3
        horizon_end = self._add_months(today, horizon_months)

        orders = list(
            self.session.scalars(
                select(WorkOrder)
                .options(
                    selectinload(WorkOrder.assignments).selectinload(
                        WorkOrderAssignment.worker_states
                    )
                )
                .where(
                    WorkOrder.planning_excluded_at.is_(None),
                    WorkOrder.completed_at.is_(None),
                    WorkOrder.deleted_at.is_(None),
                )
                .order_by(
                    WorkOrder.planning_priority_rank.asc(),
                    WorkOrder.id.asc(),
                )
            ).unique().all()
        )
        product_ids = {order.product_id for order in orders}
        operations = list(
            self.session.scalars(
                select(Operation)
                .where(Operation.product_id.in_(product_ids))
                .order_by(Operation.product_id.asc(), Operation.id.asc())
            ).unique().all()
        ) if product_ids else []
        parent_ids = {
            operation.parent_id
            for operation in operations
            if operation.parent_id is not None
        }
        leaf_operations_by_product: dict[int, list[Operation]] = defaultdict(list)
        for operation in operations:
            if operation.id not in parent_ids:
                leaf_operations_by_product[operation.product_id].append(operation)

        active_workers = list(
            self.session.scalars(
                select(User).where(
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            ).all()
        )
        active_worker_ids = {
            worker.id for worker in active_workers if "worker" in worker.roles
        }
        skill_keys = set(
            self.session.execute(
                select(
                    UserOperationSkill.user_id,
                    UserOperationSkill.operation_catalog_entry_id,
                ).where(UserOperationSkill.user_id.in_(active_worker_ids))
            ).all()
        ) if active_worker_ids else set()
        actual_seconds = self._load_actual_seconds(
            {order.id for order in orders},
            now_ts,
        )
        availability = self._load_availability(
            active_worker_ids,
            today,
            horizon_end,
            now,
        )

        planning_orders: list[PlanningOrderInput] = []
        for order in orders:
            tasks: list[PlanningTaskInput] = []
            assignments_by_operation: dict[int, list[WorkOrderAssignment]] = (
                defaultdict(list)
            )
            for assignment in order.assignments:
                assignments_by_operation[assignment.operation_id].append(assignment)
            for operation in leaf_operations_by_product.get(order.product_id, []):
                statistical_time_seconds = (
                    operation.time_estimate.seconds_per_item
                    if operation.time_estimate is not None
                    else None
                )
                standard_time_seconds = (
                    operation.standard_time_seconds
                    if operation.standard_time_seconds is not None
                    else statistical_time_seconds
                )
                standard_time_source = (
                    "manual"
                    if operation.standard_time_seconds is not None
                    else (
                        "statistical"
                        if statistical_time_seconds is not None
                        else "missing"
                    )
                )
                operation_kind = (
                    operation.catalog_entry.operation_kind
                    if operation.catalog_entry is not None
                    else OperationCatalogEntryKind.REGULAR.value
                )
                if (
                    order.production_stage == WorkOrderProductionStage.IN_WORK.value
                    and operation_kind == OperationCatalogEntryKind.CUTTING.value
                ):
                    continue
                assignments = assignments_by_operation.get(operation.id, [])
                assigned_worker_ids = tuple(
                    sorted(
                        {
                            assignment.worker_user_id
                            for assignment in assignments
                            if assignment.worker_user_id is not None
                            and self._assignment_is_available(assignment)
                        }
                    )
                )
                catalog_entry_id = operation.operation_catalog_entry_id
                eligible_worker_ids = tuple(
                    worker_id
                    for worker_id in assigned_worker_ids
                    if worker_id in active_worker_ids
                    and catalog_entry_id is not None
                    and (worker_id, catalog_entry_id) in skill_keys
                )
                tasks.append(
                    PlanningTaskInput(
                        operation_id=operation.id,
                        operation_name=operation.name,
                        stage_start=operation.stage_start,
                        stage_end=operation.stage_end,
                        workload_seconds=(
                            standard_time_seconds * order.quantity
                            if standard_time_seconds is not None
                            else None
                        ),
                        actual_seconds=actual_seconds.get(
                            (order.id, operation.id),
                            0,
                        ),
                        assigned_worker_ids=assigned_worker_ids,
                        eligible_worker_ids=eligible_worker_ids,
                        standard_time_seconds=standard_time_seconds,
                        standard_time_source=standard_time_source,
                        missing_time_issue="insufficient_statistics",
                    )
                )
            planning_orders.append(
                PlanningOrderInput(
                    order_id=order.id,
                    priority_rank=order.planning_priority_rank,
                    stage_count=order.product.stage_count,
                    is_quality_control=order.quality_control_at is not None,
                    tasks=tuple(tasks),
                )
            )

        return PlanningInput(
            today=today,
            horizon_end=horizon_end,
            display_offset_days=display_offset_days,
            preparation_seconds=preparation_seconds,
            orders=tuple(planning_orders),
            worker_availability=availability,
        )

    def _load_actual_seconds(
        self,
        order_ids: set[int],
        now_ts: int,
    ) -> dict[tuple[int, int], int]:
        if not order_ids:
            return {}
        effective_links = build_effective_operation_order_links_subquery()
        rows = self.session.execute(
            select(
                effective_links.c.order_id,
                TimerSession.operation_id,
                TimerSession.started_at,
                TimerSession.ended_at,
                effective_links.c.allocated_seconds,
            )
            .select_from(effective_links)
            .join(
                TimerSession,
                TimerSession.id == effective_links.c.timer_session_id,
            )
            .where(
                effective_links.c.order_id.in_(order_ids),
                TimerSession.operation_id.is_not(None),
                TimerSession.started_at < now_ts,
            )
        ).all()
        intervals: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
        for row in rows:
            if row.operation_id is None:
                continue
            started_at = int(row.started_at)
            if row.allocated_seconds is not None:
                ended_at = min(
                    started_at + int(row.allocated_seconds) * 1000,
                    now_ts,
                )
            else:
                ended_at = min(int(row.ended_at or now_ts), now_ts)
            if ended_at <= started_at:
                continue
            intervals[(int(row.order_id), int(row.operation_id))].append(
                (started_at, ended_at)
            )
        return {
            key: union_duration_seconds(value)
            for key, value in intervals.items()
        }

    def _load_availability(
        self,
        worker_ids: set[int],
        start_date: date,
        end_date: date,
        now: datetime,
    ) -> dict[tuple[int, date], int]:
        if not worker_ids:
            return {}
        schedule_days = self.session.scalars(
            select(UserWorkScheduleDay).where(
                UserWorkScheduleDay.user_id.in_(worker_ids),
                UserWorkScheduleDay.period_type == "work",
                UserWorkScheduleDay.work_date >= start_date,
                UserWorkScheduleDay.work_date <= end_date,
            )
        ).all()
        availability = {
            (day.user_id, day.work_date): day.available_seconds
            for day in schedule_days
        }
        today_start = datetime.combine(start_date, time.min, tzinfo=UTC)
        today_start_ts = int(today_start.timestamp() * 1000)
        now_ts = int(now.timestamp() * 1000)
        rows = self.session.execute(
            select(
                TimerSession.user_id,
                TimerSession.started_at,
                TimerSession.ended_at,
            ).where(
                TimerSession.user_id.in_(worker_ids),
                TimerSession.deleted_at.is_(None),
                TimerSession.started_at < now_ts,
                (TimerSession.ended_at.is_(None))
                | (TimerSession.ended_at > today_start_ts),
            )
        ).all()
        intervals_by_worker: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for user_id, started_at, ended_at in rows:
            clipped_start = max(int(started_at), today_start_ts)
            clipped_end = min(int(ended_at or now_ts), now_ts)
            if clipped_end > clipped_start:
                intervals_by_worker[int(user_id)].append(
                    (clipped_start, clipped_end)
                )
        for worker_id, intervals in intervals_by_worker.items():
            key = (worker_id, start_date)
            if key not in availability:
                continue
            availability[key] = max(
                availability[key] - union_duration_seconds(intervals),
                0,
            )
        return availability

    def _assignment_is_available(self, assignment: WorkOrderAssignment) -> bool:
        for state in assignment.worker_states:
            if state.worker_user_id != assignment.worker_user_id:
                continue
            return state.hidden_at is None and state.completed_at is None
        return True

    def _add_months(self, value: date, months: int) -> date:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, monthrange(year, month)[1])
        return date(year, month, day)


class ProductionPlannerService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def run_once(self, calculation_time: datetime | None = None) -> bool:
        now = (calculation_time or datetime.now(UTC)).astimezone(UTC)
        now_ts = int(now.timestamp() * 1000)
        self._request_outdated_estimate_recalculation()
        claimed = self._claim_run(now_ts)
        if claimed is None:
            return False
        run_id, input_revision = claimed
        try:
            OperationTimeEstimateService(self.session).recalculate_dirty(now_ts)
            planning_input = PlanningSnapshotBuilder(self.session).build(now)
            self.session.rollback()
            output = ProductionPlanningCalculator().calculate(
                planning_input,
                progress_callback=lambda index: self._heartbeat(
                    run_id,
                    index,
                ),
            )
            self._publish(run_id, input_revision, output)
        except Exception:
            self.session.rollback()
            self._mark_failed(run_id)
            raise
        return True

    def _request_outdated_estimate_recalculation(self) -> None:
        state = self.session.get(ProductionPlanningState, 1)
        if state is None or state.calculation_status != "idle":
            return
        if not OperationTimeEstimateService(
            self.session
        ).has_outdated_estimates():
            return
        PlanningRevisionService(self.session).request_recalculation()
        self.session.commit()

    def _claim_run(self, now: int) -> tuple[int, int] | None:
        state = self.session.scalar(
            select(ProductionPlanningState)
            .where(ProductionPlanningState.id == 1)
            .with_for_update()
        )
        if state is None:
            state = ProductionPlanningState(
                id=1,
                input_revision=1,
                requested_revision=1,
                active_run_id=None,
                calculation_status="pending",
                running_revision=None,
                worker_heartbeat_at=None,
                updated_at=now,
            )
            self.session.add(state)
            self.session.flush()
        if state.calculation_status == "error":
            failed_revision = self.session.scalar(
                select(PlanningRun.input_revision)
                .where(PlanningRun.status == "failed")
                .order_by(PlanningRun.id.desc())
                .limit(1)
            )
            if (
                failed_revision is not None
                and failed_revision >= state.requested_revision
            ):
                self.session.rollback()
                return None
        if (
            state.calculation_status == "running"
            and state.worker_heartbeat_at is not None
            and now - state.worker_heartbeat_at < WORKER_STALE_AFTER_MS
        ):
            self.session.rollback()
            return None
        if state.calculation_status == "running":
            stale_run = self.session.scalar(
                select(PlanningRun)
                .where(
                    PlanningRun.status == "running",
                    PlanningRun.input_revision == state.running_revision,
                )
                .order_by(PlanningRun.id.desc())
                .limit(1)
            )
            if stale_run is not None:
                stale_run.status = "failed"
                stale_run.completed_at = now
                stale_run.error_code = "worker_timeout"
                stale_run.error_details = None
        active_revision = self.session.scalar(
            select(PlanningRun.input_revision).where(
                PlanningRun.id == state.active_run_id
            )
        ) if state.active_run_id is not None else None
        if (
            active_revision is not None
            and active_revision >= state.requested_revision
        ):
            state.calculation_status = "idle"
            state.running_revision = None
            state.worker_heartbeat_at = None
            state.updated_at = now
            self.session.commit()
            return None

        settings = self.session.get(PlanningSettings, 1)
        run = PlanningRun(
            input_revision=state.requested_revision,
            algorithm_version=ALGORITHM_VERSION,
            horizon_months=settings.horizon_months if settings is not None else 3,
            status="running",
            started_at=now,
            completed_at=None,
            error_code=None,
            error_details=None,
        )
        self.session.add(run)
        self.session.flush()
        state.calculation_status = "running"
        state.running_revision = run.input_revision
        state.worker_heartbeat_at = now
        state.updated_at = now
        self.session.commit()
        return run.id, run.input_revision

    def _heartbeat(self, run_id: int, completed_orders: int) -> None:
        if completed_orders % 25 != 0:
            return
        state = self.session.get(ProductionPlanningState, 1)
        if state is None or state.running_revision is None:
            return
        run = self.session.get(PlanningRun, run_id)
        if run is None or run.status != "running":
            return
        state.worker_heartbeat_at = self._now_ts()
        state.updated_at = state.worker_heartbeat_at
        self.session.commit()

    def _publish(
        self,
        run_id: int,
        input_revision: int,
        output: PlanningOutput,
    ) -> None:
        now = self._now_ts()
        state = self.session.scalar(
            select(ProductionPlanningState)
            .where(ProductionPlanningState.id == 1)
            .with_for_update()
        )
        run = self.session.get(PlanningRun, run_id)
        if state is None or run is None:
            raise RuntimeError("Planning run state disappeared before publication")
        if state.input_revision != input_revision:
            run.status = "stale"
            run.completed_at = now
            state.calculation_status = "pending"
            state.running_revision = None
            state.worker_heartbeat_at = None
            state.updated_at = now
            self.session.commit()
            return

        self.session.add_all(
            [
                PlanningOrderResult(
                    run_id=run_id,
                    order_id=result.order_id,
                    resource_finish_date=result.resource_finish_date,
                    calculated_finish_date=result.calculated_finish_date,
                    status=result.status,
                    issue_codes=list(result.issue_codes),
                )
                for result in output.orders
            ]
        )
        self.session.add_all(
            [
                PlanningOperationResult(
                    run_id=run_id,
                    order_id=result.order_id,
                    operation_id=result.operation_id,
                    standard_time_seconds=result.standard_time_seconds,
                    standard_time_source=result.standard_time_source,
                    stage_start=result.stage_start,
                    stage_end=result.stage_end,
                    workload_seconds=result.workload_seconds,
                    actual_seconds=result.actual_seconds,
                    remaining_seconds=result.remaining_seconds,
                    preparation_seconds=result.preparation_seconds,
                    first_planned_date=result.first_planned_date,
                    last_planned_date=result.last_planned_date,
                    status=result.status,
                    issue_codes=list(result.issue_codes),
                )
                for result in output.operations
            ]
        )
        self.session.add_all(
            [
                PlanningWorkerDayAllocation(
                    run_id=run_id,
                    user_id=allocation.user_id,
                    work_date=allocation.work_date,
                    order_id=allocation.order_id,
                    operation_id=allocation.operation_id,
                    work_seconds=allocation.work_seconds,
                    preparation_seconds=allocation.preparation_seconds,
                )
                for allocation in output.allocations
            ]
        )
        run.status = "completed"
        run.completed_at = now
        state.active_run_id = run.id
        state.calculation_status = "idle"
        state.running_revision = None
        state.worker_heartbeat_at = None
        state.updated_at = now
        self.session.commit()

    def _mark_failed(self, run_id: int) -> None:
        now = self._now_ts()
        run = self.session.get(PlanningRun, run_id)
        state = self.session.get(ProductionPlanningState, 1)
        if run is not None:
            run.status = "failed"
            run.completed_at = now
            run.error_code = "calculation_failed"
            run.error_details = None
        if state is not None:
            state.calculation_status = "error"
            state.running_revision = None
            state.worker_heartbeat_at = None
            state.updated_at = now
        self.session.commit()

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)

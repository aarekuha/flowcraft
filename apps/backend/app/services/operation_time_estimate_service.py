# ruff: noqa: I001
from collections import defaultdict
from datetime import UTC, datetime
from fractions import Fraction

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.operation import Operation
from app.models.planning import OperationTimeEstimate
from app.models.timer_session import TimerSession
from app.models.work_order import WorkOrder
from app.services.effective_order_time import (
    build_effective_operation_order_links_subquery,
    union_duration_seconds,
)

from app.services.operation_pricing import recalculate_prices

ALGORITHM_VERSION = "recent-30d-five-items-mean-v3"
MIN_ITEMS = 5
LOOKBACK_MILLISECONDS = 30 * 24 * 60 * 60 * 1000


class OperationTimeEstimateService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def has_outdated_estimates(self) -> bool:
        return (
            self.session.scalar(
                select(OperationTimeEstimate.operation_id)
                .where(OperationTimeEstimate.algorithm_version != ALGORITHM_VERSION)
                .limit(1)
            )
            is not None
        )

    def mark_operations_dirty(
        self,
        operation_ids: set[int],
        *,
        dirty_at: int | None = None,
    ) -> None:
        if not operation_ids:
            return
        timestamp = dirty_at if dirty_at is not None else self._now_ts()
        estimates = self.session.scalars(
            select(OperationTimeEstimate).where(
                OperationTimeEstimate.operation_id.in_(operation_ids)
            )
        ).all()
        estimates_by_operation_id = {
            estimate.operation_id: estimate for estimate in estimates
        }
        for operation_id in operation_ids:
            estimate = estimates_by_operation_id.get(operation_id)
            if estimate is None:
                self.session.add(
                    OperationTimeEstimate(
                        operation_id=operation_id,
                        seconds_per_item=None,
                        completed_orders_count=0,
                        items_count=0,
                        calculated_at=None,
                        algorithm_version=ALGORITHM_VERSION,
                        dirty_at=timestamp,
                    )
                )
                continue
            estimate.dirty_at = (
                timestamp
                if estimate.dirty_at is None
                else max(timestamp, estimate.dirty_at + 1)
            )

    def mark_product_dirty(
        self,
        product_id: int,
        *,
        dirty_at: int | None = None,
    ) -> None:
        operations = self.session.execute(
            select(Operation.id, Operation.parent_id).where(
                Operation.product_id == product_id
            )
        ).all()
        parent_ids = {parent_id for _, parent_id in operations if parent_id is not None}
        operation_ids = {
            operation_id
            for operation_id, _ in operations
            if operation_id not in parent_ids
        }
        self.mark_operations_dirty(operation_ids, dirty_at=dirty_at)

    def recalculate_dirty(self, calculated_at: int | None = None) -> int:
        estimates = self.session.scalars(
            select(OperationTimeEstimate)
            .where(
                or_(
                    OperationTimeEstimate.dirty_at.is_not(None),
                    OperationTimeEstimate.algorithm_version != ALGORITHM_VERSION,
                )
            )
            .order_by(OperationTimeEstimate.operation_id.asc())
            .with_for_update()
        ).all()
        if not estimates:
            return 0

        timestamp = calculated_at if calculated_at is not None else self._now_ts()
        dirty_tokens = {
            estimate.operation_id: estimate.dirty_at for estimate in estimates
        }
        algorithm_versions = {
            estimate.operation_id: estimate.algorithm_version for estimate in estimates
        }
        operation_ids = {estimate.operation_id for estimate in estimates}
        samples = self._load_samples(operation_ids)
        for estimate in estimates:
            operation_samples = samples.get(estimate.operation_id, [])
            completed_orders_count = len(operation_samples)
            items_count = sum(
                included_quantity for _, _, included_quantity in operation_samples
            )
            seconds_per_item = (
                self._average_seconds(operation_samples)
                if items_count >= MIN_ITEMS
                else None
            )
            dirty_at = dirty_tokens[estimate.operation_id]
            dirty_condition = (
                OperationTimeEstimate.dirty_at.is_(None)
                if dirty_at is None
                else OperationTimeEstimate.dirty_at == dirty_at
            )
            self.session.execute(
                update(OperationTimeEstimate)
                .where(
                    OperationTimeEstimate.operation_id == estimate.operation_id,
                    dirty_condition,
                    OperationTimeEstimate.algorithm_version
                    == algorithm_versions[estimate.operation_id],
                )
                .values(
                    seconds_per_item=seconds_per_item,
                    completed_orders_count=completed_orders_count,
                    items_count=items_count,
                    calculated_at=timestamp,
                    algorithm_version=ALGORITHM_VERSION,
                    dirty_at=None,
                )
                .execution_options(synchronize_session=False)
            )
        recalculate_prices(self.session, operation_ids)
        self.session.commit()
        return len(estimates)

    def _load_samples(
        self,
        operation_ids: set[int],
    ) -> dict[int, list[tuple[int, int, int]]]:
        effective_links = build_effective_operation_order_links_subquery()
        rows = self.session.execute(
            select(
                TimerSession.operation_id,
                effective_links.c.order_id,
                WorkOrder.quantity,
                WorkOrder.completed_at,
                TimerSession.started_at,
                TimerSession.ended_at,
                effective_links.c.allocated_seconds,
            )
            .select_from(effective_links)
            .join(
                TimerSession,
                TimerSession.id == effective_links.c.timer_session_id,
            )
            .join(WorkOrder, WorkOrder.id == effective_links.c.order_id)
            .where(
                TimerSession.operation_id.in_(operation_ids),
                TimerSession.ended_at.is_not(None),
                WorkOrder.completed_at.is_not(None),
                WorkOrder.quantity > 0,
            )
        ).all()
        intervals: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
        quantities: dict[tuple[int, int], int] = {}
        completed_at_by_order: dict[tuple[int, int], int] = {}
        for row in rows:
            if (
                row.operation_id is None
                or row.ended_at is None
                or row.completed_at is None
            ):
                continue
            key = (int(row.operation_id), int(row.order_id))
            started_at = int(row.started_at)
            ended_at = (
                started_at + int(row.allocated_seconds) * 1000
                if row.allocated_seconds is not None
                else int(row.ended_at)
            )
            if ended_at <= started_at:
                continue
            intervals[key].append((started_at, ended_at))
            quantities[key] = int(row.quantity)
            completed_at_by_order[key] = int(row.completed_at)

        candidates: dict[int, list[tuple[int, int, int, int]]] = defaultdict(list)
        for key, order_intervals in intervals.items():
            operation_id, order_id = key
            elapsed_seconds = union_duration_seconds(order_intervals)
            if elapsed_seconds <= 0:
                continue
            candidates[operation_id].append(
                (
                    completed_at_by_order[key],
                    order_id,
                    elapsed_seconds,
                    quantities[key],
                )
            )

        samples: dict[int, list[tuple[int, int, int]]] = {}
        for operation_id, operation_candidates in candidates.items():
            ordered_candidates = sorted(
                operation_candidates,
                key=lambda item: (item[0], item[1]),
                reverse=True,
            )
            latest_completed_at = ordered_candidates[0][0]
            cutoff = latest_completed_at - LOOKBACK_MILLISECONDS
            selected_samples = [
                (elapsed_seconds, quantity, quantity)
                for completed_at, _, elapsed_seconds, quantity in ordered_candidates
                if completed_at >= cutoff
            ]
            selected_items = sum(
                included_quantity for _, _, included_quantity in selected_samples
            )
            if selected_items < MIN_ITEMS:
                for completed_at, _, elapsed_seconds, quantity in ordered_candidates:
                    if completed_at >= cutoff:
                        continue
                    included_quantity = min(quantity, MIN_ITEMS - selected_items)
                    selected_samples.append(
                        (elapsed_seconds, quantity, included_quantity)
                    )
                    selected_items += included_quantity
                    if selected_items >= MIN_ITEMS:
                        break
            samples[operation_id] = selected_samples
        return samples

    def _average_seconds(
        self,
        samples: list[tuple[int, int, int]],
    ) -> int:
        if not samples:
            raise RuntimeError("Operation time samples unexpectedly empty")
        items_count = sum(included_quantity for _, _, included_quantity in samples)
        if items_count <= 0:
            raise RuntimeError("Operation time samples contain no items")
        total_seconds = sum(
            (
                Fraction(elapsed_seconds, quantity) * included_quantity
                for elapsed_seconds, quantity, included_quantity in samples
            ),
            start=Fraction(0, 1),
        )
        average = total_seconds / Fraction(items_count, 1)
        return (average.numerator + average.denominator - 1) // average.denominator

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)

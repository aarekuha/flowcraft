from datetime import UTC, datetime

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.timer_session import TimerSession
from app.models.work_order import WorkOrder, WorkOrderTimeAllocation
from app.schemas.operation_catalog import OperationCatalogEntryKind

OPERATION_TIMER_TYPE_CODE = 2


class WorkOrderTimeService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def refresh_totals(
        self,
        order_ids: set[int],
        *,
        set_initial_taken_at: bool,
        recalculate_taken_at: bool = False,
        recalculate_cutting_started_at: bool = False,
        updated_at: int | None = None,
    ) -> None:
        if not order_ids:
            return

        self.session.flush()

        for order_id in order_ids:
            allocated_session_exists = exists(
                select(WorkOrderTimeAllocation.id).where(
                    WorkOrderTimeAllocation.timer_session_id == TimerSession.id
                )
            )
            raw_total_ms = int(
                self.session.scalar(
                    select(
                        func.coalesce(
                            func.sum(
                                TimerSession.ended_at - TimerSession.started_at
                            ),
                            0,
                        )
                    ).where(
                        TimerSession.order_id == order_id,
                        TimerSession.timer_type_code == OPERATION_TIMER_TYPE_CODE,
                        TimerSession.ended_at.is_not(None),
                        TimerSession.deleted_at.is_(None),
                        ~allocated_session_exists,
                    )
                )
                or 0
            )
            allocated_total_seconds = int(
                self.session.scalar(
                    select(
                        func.coalesce(
                            func.sum(WorkOrderTimeAllocation.allocated_seconds),
                            0,
                        )
                    )
                    .select_from(WorkOrderTimeAllocation)
                    .join(
                        TimerSession,
                        TimerSession.id == WorkOrderTimeAllocation.timer_session_id,
                    )
                    .where(
                        WorkOrderTimeAllocation.work_order_id == order_id,
                        TimerSession.deleted_at.is_(None),
                    )
                )
                or 0
            )
            raw_cutting_ms = int(
                self.session.scalar(
                    select(
                        func.coalesce(
                            func.sum(
                                TimerSession.ended_at - TimerSession.started_at
                            ),
                            0,
                        )
                    )
                    .select_from(TimerSession)
                    .join(Operation, Operation.id == TimerSession.operation_id)
                    .join(
                        OperationCatalogEntry,
                        OperationCatalogEntry.id
                        == Operation.operation_catalog_entry_id,
                    )
                    .where(
                        TimerSession.order_id == order_id,
                        TimerSession.timer_type_code == OPERATION_TIMER_TYPE_CODE,
                        TimerSession.ended_at.is_not(None),
                        TimerSession.deleted_at.is_(None),
                        OperationCatalogEntry.operation_kind
                        == OperationCatalogEntryKind.CUTTING.value,
                        ~allocated_session_exists,
                    )
                )
                or 0
            )
            allocated_cutting_seconds = int(
                self.session.scalar(
                    select(
                        func.coalesce(
                            func.sum(WorkOrderTimeAllocation.allocated_seconds),
                            0,
                        )
                    )
                    .select_from(WorkOrderTimeAllocation)
                    .join(
                        TimerSession,
                        TimerSession.id == WorkOrderTimeAllocation.timer_session_id,
                    )
                    .join(Operation, Operation.id == TimerSession.operation_id)
                    .join(
                        OperationCatalogEntry,
                        OperationCatalogEntry.id
                        == Operation.operation_catalog_entry_id,
                    )
                    .where(
                        WorkOrderTimeAllocation.work_order_id == order_id,
                        TimerSession.deleted_at.is_(None),
                        OperationCatalogEntry.operation_kind
                        == OperationCatalogEntryKind.CUTTING.value,
                    )
                )
                or 0
            )
            order = self.session.get(WorkOrder, order_id)
            if order is None:
                continue

            order.total_spent_seconds = (
                raw_total_ms // 1000 + allocated_total_seconds
            )
            order.cutting_spent_seconds = (
                raw_cutting_ms // 1000 + allocated_cutting_seconds
            )
            if recalculate_cutting_started_at:
                order.cutting_started_at = self._get_first_cutting_timer_start(
                    order_id
                )
            if recalculate_taken_at:
                order.taken_at = (
                    self._get_first_accounted_timer_start(order_id)
                    if order.total_spent_seconds > 0
                    else None
                )
            elif (
                set_initial_taken_at
                and order.taken_at is None
                and order.total_spent_seconds > 0
            ):
                order.taken_at = self._get_first_accounted_timer_start(order_id)
            order.updated_at = updated_at if updated_at is not None else self._now_ts()

    def _get_first_accounted_timer_start(self, order_id: int) -> int | None:
        allocated_session_exists = exists(
            select(WorkOrderTimeAllocation.id).where(
                WorkOrderTimeAllocation.timer_session_id == TimerSession.id
            )
        )
        raw_started_at = self.session.scalar(
            select(func.min(TimerSession.started_at)).where(
                TimerSession.order_id == order_id,
                TimerSession.timer_type_code == OPERATION_TIMER_TYPE_CODE,
                TimerSession.ended_at.is_not(None),
                TimerSession.ended_at > TimerSession.started_at,
                TimerSession.deleted_at.is_(None),
                ~allocated_session_exists,
            )
        )
        allocated_started_at = self.session.scalar(
            select(func.min(TimerSession.started_at))
            .select_from(WorkOrderTimeAllocation)
            .join(
                TimerSession,
                TimerSession.id == WorkOrderTimeAllocation.timer_session_id,
            )
            .where(
                WorkOrderTimeAllocation.work_order_id == order_id,
                WorkOrderTimeAllocation.allocated_seconds > 0,
                TimerSession.deleted_at.is_(None),
            )
        )
        values = [
            int(value)
            for value in (raw_started_at, allocated_started_at)
            if value is not None
        ]
        return min(values) if values else None

    def _get_first_cutting_timer_start(self, order_id: int) -> int | None:
        allocated_session_exists = exists(
            select(WorkOrderTimeAllocation.id).where(
                WorkOrderTimeAllocation.timer_session_id == TimerSession.id
            )
        )
        raw_started_at = self.session.scalar(
            select(func.min(TimerSession.started_at))
            .select_from(TimerSession)
            .join(Operation, Operation.id == TimerSession.operation_id)
            .join(
                OperationCatalogEntry,
                OperationCatalogEntry.id == Operation.operation_catalog_entry_id,
            )
            .where(
                TimerSession.order_id == order_id,
                TimerSession.timer_type_code == OPERATION_TIMER_TYPE_CODE,
                TimerSession.deleted_at.is_(None),
                OperationCatalogEntry.operation_kind
                == OperationCatalogEntryKind.CUTTING.value,
                ~allocated_session_exists,
            )
        )
        allocated_started_at = self.session.scalar(
            select(func.min(TimerSession.started_at))
            .select_from(WorkOrderTimeAllocation)
            .join(
                TimerSession,
                TimerSession.id == WorkOrderTimeAllocation.timer_session_id,
            )
            .join(Operation, Operation.id == TimerSession.operation_id)
            .join(
                OperationCatalogEntry,
                OperationCatalogEntry.id == Operation.operation_catalog_entry_id,
            )
            .where(
                WorkOrderTimeAllocation.work_order_id == order_id,
                WorkOrderTimeAllocation.allocated_seconds > 0,
                TimerSession.deleted_at.is_(None),
                OperationCatalogEntry.operation_kind
                == OperationCatalogEntryKind.CUTTING.value,
            )
        )
        values = [
            int(value)
            for value in (raw_started_at, allocated_started_at)
            if value is not None
        ]
        return min(values) if values else None

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)

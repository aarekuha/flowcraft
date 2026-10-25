from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, exists, func, or_, select, union_all, update
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.leather_type import LeatherType
from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.work_order import (
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderAssignmentWorkerState,
    WorkOrderFamily,
    WorkOrderNumberCounter,
    WorkOrderQrReference,
    WorkOrderTimeAllocation,
)
from app.schemas.operation_catalog import OperationCatalogEntryKind
from app.schemas.order import (
    SortDirection,
    WorkerAssignmentStatusFilter,
    WorkOrderAssignmentCreate,
    WorkOrderAssignmentRead,
    WorkOrderAssignmentWorkerStatusUpdate,
    WorkOrderCreate,
    WorkOrderDeletedStatusUpdate,
    WorkOrderDetail,
    WorkOrderListItem,
    WorkOrderMergeCandidate,
    WorkOrderMergeRequest,
    WorkOrderNumberSearchItem,
    WorkOrderPage,
    WorkOrderPlannedCompletionDateUpdate,
    WorkOrderProductionStage,
    WorkOrderProductionStageUpdate,
    WorkOrderQrTarget,
    WorkOrderQualityControlAccept,
    WorkOrderQualityControlStatusUpdate,
    WorkOrderSortField,
    WorkOrderSplitRequest,
    WorkOrderSplitResult,
    WorkOrderStatusFilter,
    WorkOrderStatusUpdate,
    WorkOrderTimeBreakdown,
    WorkOrderTimeBreakdownItem,
    WorkOrderUpdateAssignments,
)
from app.schemas.timer import TimerType
from app.services.effective_order_time import build_effective_operation_time_subquery
from app.services.timer_service import TIMER_TYPE_TO_CODE


class OrderService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_orders(
        self,
        *,
        search: str | None,
        include_completed: bool,
        status_filter: WorkOrderStatusFilter,
        sort_by: WorkOrderSortField,
        sort_direction: SortDirection,
        page: int,
        page_size: int,
    ) -> WorkOrderPage:
        assignments_count = (
            select(
                WorkOrderAssignment.work_order_id,
                func.count(WorkOrderAssignment.id).label("assignments_count"),
            )
            .group_by(WorkOrderAssignment.work_order_id)
            .subquery()
        )
        spent_time = self._build_spent_time_subquery()
        filters = self._build_order_list_filters(
            include_completed=include_completed,
            status_filter=status_filter,
        )

        stmt = (
            select(
                WorkOrder.id,
                WorkOrder.order_number,
                WorkOrder.family_id,
                WorkOrder.part_number,
                WorkOrderFamily.base_order_number.label("family_base_order_number"),
                WorkOrder.product_id,
                Product.name.label("product_name"),
                Product.version.label("product_version"),
                WorkOrder.leather_type_id,
                LeatherType.name.label("leather_type_name"),
                WorkOrder.quantity,
                WorkOrder.planned_completion_date,
                WorkOrder.estimated_minutes,
                WorkOrder.total_spent_seconds,
                WorkOrder.cutting_spent_seconds,
                WorkOrder.created_at,
                WorkOrder.updated_at,
                WorkOrder.production_stage,
                WorkOrder.cutting_started_at,
                WorkOrder.taken_at,
                WorkOrder.quality_control_at,
                WorkOrder.defect_quantity,
                WorkOrder.completed_at,
                WorkOrder.deleted_at,
                func.coalesce(assignments_count.c.assignments_count, 0).label(
                    "assignments_count"
                ),
                func.coalesce(spent_time.c.spent_sessions_count, 0).label(
                    "spent_sessions_count"
                ),
            )
            .join(Product, Product.id == WorkOrder.product_id)
            .outerjoin(WorkOrderFamily, WorkOrderFamily.id == WorkOrder.family_id)
            .outerjoin(LeatherType, LeatherType.id == WorkOrder.leather_type_id)
            .outerjoin(
                assignments_count,
                assignments_count.c.work_order_id == WorkOrder.id,
            )
            .outerjoin(
                spent_time,
                spent_time.c.order_id == WorkOrder.id,
            )
        )

        if filters:
            stmt = stmt.where(*filters)

        stmt = stmt.order_by(
            *self._build_order_list_sort(
                sort_by=sort_by,
                sort_direction=sort_direction,
            )
        )

        rows = self.session.execute(stmt).all()
        normalized_search = self._normalize_order_search(search or "")
        matching_rows = [
            row
            for row in rows
            if (
                not normalized_search
                or normalized_search
                in self._normalize_order_search(row.order_number)
                or normalized_search
                in self._normalize_order_search(row.product_name)
            )
        ]
        total = len(matching_rows)
        pages = max(1, (total + page_size - 1) // page_size)
        page_start = (page - 1) * page_size
        page_end = page_start + page_size
        items = [
            WorkOrderListItem(
                id=row.id,
                order_number=row.order_number,
                family_id=row.family_id,
                part_number=row.part_number,
                family_base_order_number=row.family_base_order_number,
                product_id=row.product_id,
                product_name=row.product_name,
                product_version=row.product_version,
                leather_type_id=row.leather_type_id,
                leather_type_name=row.leather_type_name,
                quantity=row.quantity,
                planned_completion_date=row.planned_completion_date,
                estimated_minutes=row.estimated_minutes,
                total_spent_seconds=row.total_spent_seconds,
                cutting_spent_seconds=row.cutting_spent_seconds,
                has_spent_time=row.spent_sessions_count > 0,
                can_split=split_eligibility[0],
                split_block_reason=split_eligibility[1],
                can_merge=self._merge_receiver_is_eligible(row.id),
                assignments_count=row.assignments_count,
                created_at=row.created_at,
                updated_at=row.updated_at,
                production_stage=WorkOrderProductionStage(row.production_stage),
                cutting_started_at=row.cutting_started_at,
                taken_at=row.taken_at,
                quality_control_at=row.quality_control_at,
                defect_quantity=row.defect_quantity,
                completed_at=row.completed_at,
                deleted_at=row.deleted_at,
            )
            for row in matching_rows[page_start:page_end]
            for split_eligibility in [self._split_eligibility(row.id)]
        ]

        return WorkOrderPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    def search_orders_by_number(
        self,
        *,
        search: str,
        limit: int,
    ) -> list[WorkOrderNumberSearchItem]:
        normalized_search = search.strip().casefold()
        if not normalized_search:
            return []

        orders = self.session.scalars(
            select(WorkOrder)
            .where(
                func.lower(WorkOrder.order_number).contains(
                    normalized_search,
                    autoescape=True,
                )
            )
            .order_by(
                func.lower(WorkOrder.order_number).asc(),
                WorkOrder.order_number.asc(),
                WorkOrder.id.asc(),
            )
            .limit(limit)
        ).all()
        return [
            WorkOrderNumberSearchItem(
                id=order.id,
                order_number=order.order_number,
                stage=self._get_order_status(order),
            )
            for order in orders
        ]

    def _build_order_list_filters(
        self,
        *,
        include_completed: bool,
        status_filter: WorkOrderStatusFilter,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []

        if status_filter == WorkOrderStatusFilter.CREATED:
            filters.extend(
                [
                    WorkOrder.deleted_at.is_(None),
                    WorkOrder.completed_at.is_(None),
                    WorkOrder.quality_control_at.is_(None),
                    WorkOrder.production_stage
                    == WorkOrderProductionStage.CREATED.value,
                ]
            )
        elif status_filter == WorkOrderStatusFilter.CUTTING:
            filters.extend(
                [
                    WorkOrder.deleted_at.is_(None),
                    WorkOrder.completed_at.is_(None),
                    WorkOrder.quality_control_at.is_(None),
                    WorkOrder.production_stage
                    == WorkOrderProductionStage.CUTTING.value,
                ]
            )
        elif status_filter == WorkOrderStatusFilter.IN_WORK:
            filters.extend(
                [
                    WorkOrder.deleted_at.is_(None),
                    WorkOrder.completed_at.is_(None),
                    WorkOrder.quality_control_at.is_(None),
                    WorkOrder.production_stage
                    == WorkOrderProductionStage.IN_WORK.value,
                ]
            )
        elif status_filter == WorkOrderStatusFilter.QUALITY_CONTROL:
            filters.extend(
                [
                    WorkOrder.deleted_at.is_(None),
                    WorkOrder.completed_at.is_(None),
                    WorkOrder.quality_control_at.is_not(None),
                ]
            )
        elif status_filter == WorkOrderStatusFilter.COMPLETED:
            filters.extend(
                [
                    WorkOrder.deleted_at.is_(None),
                    WorkOrder.completed_at.is_not(None),
                ]
            )
        elif status_filter == WorkOrderStatusFilter.DELETED:
            filters.append(WorkOrder.deleted_at.is_not(None))
        elif status_filter == WorkOrderStatusFilter.ALL:
            pass
        elif not include_completed:
            filters.extend(
                [
                    WorkOrder.deleted_at.is_(None),
                    WorkOrder.completed_at.is_(None),
                    WorkOrder.quality_control_at.is_(None),
                ]
            )

        return filters

    def _get_order_status(self, order: WorkOrder) -> WorkOrderStatusFilter:
        if order.deleted_at is not None:
            return WorkOrderStatusFilter.DELETED
        if order.completed_at is not None:
            return WorkOrderStatusFilter.COMPLETED
        if order.quality_control_at is not None:
            return WorkOrderStatusFilter.QUALITY_CONTROL
        return WorkOrderStatusFilter(order.production_stage)

    def _matches_order_search(
        self,
        order: WorkOrderListItem,
        normalized_search: str,
    ) -> bool:
        if not normalized_search:
            return True

        return normalized_search in self._normalize_order_search(
            order.order_number
        ) or normalized_search in self._normalize_order_search(order.product_name)

    def _normalize_order_search(self, value: str) -> str:
        return value.strip().casefold()

    def _build_order_list_sort(
        self,
        *,
        sort_by: WorkOrderSortField,
        sort_direction: SortDirection,
    ) -> list[ColumnElement[Any]]:
        is_desc = sort_direction == SortDirection.DESC

        if sort_by == WorkOrderSortField.ORDER_NUMBER:
            order_number_sort = (
                WorkOrder.order_number.desc()
                if is_desc
                else WorkOrder.order_number.asc()
            )
            return [order_number_sort, WorkOrder.id.desc()]

        if sort_by == WorkOrderSortField.NAME:
            product_name_sort = Product.name.desc() if is_desc else Product.name.asc()
            return [
                product_name_sort,
                Product.version.asc(),
                WorkOrder.order_number.asc(),
                WorkOrder.id.desc(),
            ]

        if sort_by == WorkOrderSortField.QUALITY_CONTROL:
            return self._build_nullable_timestamp_sort(
                WorkOrder.quality_control_at,
                sort_direction,
            )

        if sort_by == WorkOrderSortField.CUTTING_STARTED:
            return self._build_nullable_timestamp_sort(
                WorkOrder.cutting_started_at,
                sort_direction,
            )

        if sort_by == WorkOrderSortField.PLANNED_COMPLETION:
            return self._build_nullable_timestamp_sort(
                WorkOrder.planned_completion_date,
                sort_direction,
            )

        if sort_by == WorkOrderSortField.TAKEN:
            return self._build_nullable_timestamp_sort(
                WorkOrder.taken_at,
                sort_direction,
            )

        if sort_by == WorkOrderSortField.COMPLETED:
            return self._build_nullable_timestamp_sort(
                WorkOrder.completed_at,
                sort_direction,
            )

        if sort_by == WorkOrderSortField.DEFECT:
            defect_quantity_sort = (
                WorkOrder.defect_quantity.desc()
                if is_desc
                else WorkOrder.defect_quantity.asc()
            )
            return [
                defect_quantity_sort,
                WorkOrder.created_at.desc(),
                WorkOrder.id.desc(),
            ]

        created_at_sort = (
            WorkOrder.created_at.desc() if is_desc else WorkOrder.created_at.asc()
        )
        return [created_at_sort, WorkOrder.id.desc()]

    def _build_nullable_timestamp_sort(
        self,
        column: ColumnElement[Any],
        sort_direction: SortDirection,
    ) -> list[ColumnElement[Any]]:
        value_sort = (
            column.desc() if sort_direction == SortDirection.DESC else column.asc()
        )
        return [
            column.is_(None).asc(),
            value_sort,
            WorkOrder.created_at.desc(),
            WorkOrder.id.desc(),
        ]

    def get_order(self, order_id: int) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        product = self._get_product_or_404(order.product_id)
        return self._serialize_order(order, product)

    def get_order_time_breakdown(self, order_id: int) -> WorkOrderTimeBreakdown:
        order = self._get_order_or_404(order_id)
        effective_time = build_effective_operation_time_subquery()

        stmt = (
            select(
                effective_time.c.operation_id,
                func.coalesce(
                    OperationCatalogEntry.name,
                    Operation.name,
                    "Операция удалена",
                ).label("operation_name"),
                effective_time.c.user_id,
                User.name.label("worker_user_name"),
                Operation.standard_time_seconds,
                func.coalesce(
                    func.sum(effective_time.c.elapsed_ms),
                    0,
                ).label("elapsed_ms"),
            )
            .select_from(effective_time)
            .join(User, User.id == effective_time.c.user_id)
            .outerjoin(Operation, Operation.id == effective_time.c.operation_id)
            .outerjoin(
                OperationCatalogEntry,
                OperationCatalogEntry.id == Operation.operation_catalog_entry_id,
            )
            .where(
                effective_time.c.order_id == order_id,
            )
            .group_by(
                effective_time.c.operation_id,
                OperationCatalogEntry.name,
                Operation.name,
                effective_time.c.user_id,
                User.name,
                Operation.standard_time_seconds,
            )
            .order_by(
                OperationCatalogEntry.name.asc(),
                Operation.name.asc(),
                User.name.asc(),
                effective_time.c.user_id.asc(),
            )
        )
        rows = self.session.execute(stmt).all()
        operation_elapsed_ms: dict[int | None, int] = {}
        for row in rows:
            operation_elapsed_ms[row.operation_id] = operation_elapsed_ms.get(
                row.operation_id, 0
            ) + int(row.elapsed_ms)

        items = [
            WorkOrderTimeBreakdownItem(
                operation_id=row.operation_id,
                operation_name=row.operation_name,
                worker_user_id=row.user_id,
                worker_user_name=row.worker_user_name,
                elapsed_ms=int(row.elapsed_ms),
                standard_time_seconds=row.standard_time_seconds,
                average_elapsed_ms=(
                    operation_elapsed_ms[row.operation_id] // order.quantity
                ),
            )
            for row in rows
        ]

        return WorkOrderTimeBreakdown(
            order_id=order_id,
            items=items,
            total_standard_time_seconds=sum(
                assignment.operation.standard_time_seconds or 0
                for assignment in {
                    assignment.operation_id: assignment
                    for assignment in order.assignments
                }.values()
            ),
            total_elapsed_ms=sum(item.elapsed_ms for item in items),
        )

    def list_worker_assigned_orders(
        self,
        worker_user_id: int,
        worker_status_filter: WorkerAssignmentStatusFilter,
    ) -> list[WorkOrderDetail]:
        state_join = and_(
            WorkOrderAssignmentWorkerState.assignment_id == WorkOrderAssignment.id,
            WorkOrderAssignmentWorkerState.worker_user_id == worker_user_id,
        )
        stmt: Select[tuple[WorkOrder]] = (
            select(WorkOrder)
            .join(
                WorkOrderAssignment,
                WorkOrderAssignment.work_order_id == WorkOrder.id,
            )
            .outerjoin(WorkOrderAssignmentWorkerState, state_join)
            .options(
                selectinload(WorkOrder.assignments)
                .selectinload(WorkOrderAssignment.operation)
                .selectinload(Operation.catalog_entry),
                selectinload(WorkOrder.assignments).selectinload(
                    WorkOrderAssignment.worker_user
                ),
                selectinload(WorkOrder.assignments).selectinload(
                    WorkOrderAssignment.worker_states
                ),
            )
            .where(
                WorkOrder.deleted_at.is_(None),
                WorkOrderAssignment.worker_user_id == worker_user_id,
                *self._build_worker_assignment_status_filters(
                    worker_status_filter,
                ),
            )
            .order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())
        )
        orders = self.session.scalars(stmt).unique().all()

        serialized_orders = [
            self._serialize_order(
                order,
                order.product,
                assignment_worker_user_id=worker_user_id,
                assignment_worker_status_filter=worker_status_filter,
            )
            for order in orders
        ]
        if worker_status_filter != WorkerAssignmentStatusFilter.IN_WORK:
            return serialized_orders
        return [order for order in serialized_orders if order.assignments]

    def split_order(
        self,
        order_id: int,
        payload: WorkOrderSplitRequest,
    ) -> WorkOrderSplitResult:
        self._lock_order(order_id)
        order = self._get_order_or_404(order_id)
        can_split, block_reason = self._split_eligibility(order.id)
        if not can_split:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=block_reason or "Order cannot be split.",
            )
        if payload.source_quantity >= order.quantity:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Both split parts must contain at least one item.",
            )

        original_quantity = order.quantity
        created_quantity = original_quantity - payload.source_quantity
        now = self._now_ts()
        family = order.family
        if family is None:
            family = WorkOrderFamily(
                base_order_number=order.order_number,
                last_part_number=1,
                created_at=now,
                updated_at=now,
            )
            self.session.add(family)
            self.session.flush()
            order.family_id = family.id
            order.part_number = 1
        else:
            family = self.session.scalar(
                select(WorkOrderFamily)
                .where(WorkOrderFamily.id == family.id)
                .with_for_update()
            )
            if family is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Order family changed during splitting.",
                )

        next_part_number = family.last_part_number + 1
        created_order_number = f"{family.base_order_number}/{next_part_number}"
        while self._order_number_is_reserved(created_order_number):
            next_part_number += 1
            created_order_number = f"{family.base_order_number}/{next_part_number}"
        family.last_part_number = next_part_number
        family.updated_at = now

        created_estimated_minutes = (
            order.estimated_minutes * created_quantity // original_quantity
        )
        source_estimated_minutes = (
            order.estimated_minutes - created_estimated_minutes
        )
        created_order = WorkOrder(
            order_number=created_order_number,
            family_id=family.id,
            part_number=next_part_number,
            product_id=order.product_id,
            leather_type_id=order.leather_type_id,
            quantity=created_quantity,
            planned_completion_date=order.planned_completion_date,
            estimated_minutes=created_estimated_minutes,
            total_spent_seconds=0,
            cutting_spent_seconds=0,
            production_stage=WorkOrderProductionStage(order.production_stage),
            created_at=now,
            updated_at=now,
            cutting_started_at=order.cutting_started_at,
            taken_at=order.taken_at,
            quality_control_at=None,
            defect_quantity=0,
            completed_at=None,
            deleted_at=None,
        )
        created_order.assignments = self._clone_assignments_for_split(order, now)
        self.session.add(created_order)
        self.session.flush()

        self._initialize_order_time_allocations(order.id, now)
        source_seconds, created_seconds = self._split_order_time_allocations(
            source_order_id=order.id,
            created_order_id=created_order.id,
            created_quantity=created_quantity,
            original_quantity=original_quantity,
            now=now,
        )
        order.quantity = payload.source_quantity
        order.estimated_minutes = source_estimated_minutes
        order.total_spent_seconds = source_seconds
        if source_seconds == 0:
            order.taken_at = None
        order.cutting_spent_seconds = self._get_effective_spent_seconds(
            order.id,
            cutting_only=True,
        )
        order.updated_at = now
        created_order.total_spent_seconds = created_seconds
        if created_seconds == 0:
            created_order.taken_at = None
        created_order.cutting_spent_seconds = self._get_effective_spent_seconds(
            created_order.id,
            cutting_only=True,
        )

        self.session.commit()
        return WorkOrderSplitResult(
            source=self.get_order(order.id),
            created=self.get_order(created_order.id),
        )

    def list_merge_candidates(
        self,
        order_id: int,
        search: str | None,
    ) -> list[WorkOrderMergeCandidate]:
        order = self._get_order_or_404(order_id)
        self._validate_merge_receiver(order)
        normalized_search = self._normalize_order_search(search or "")
        family_orders = self.session.scalars(
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.assignments).selectinload(
                    WorkOrderAssignment.worker_states
                )
            )
            .where(
                WorkOrder.family_id == order.family_id,
                WorkOrder.id != order.id,
                WorkOrder.deleted_at.is_(None),
            )
            .order_by(WorkOrder.part_number.asc(), WorkOrder.id.asc())
        ).unique().all()

        return [
            WorkOrderMergeCandidate(
                id=candidate.id,
                order_number=candidate.order_number,
                quantity=candidate.quantity,
            )
            for candidate in family_orders
            if (
                not normalized_search
                or normalized_search
                in self._normalize_order_search(candidate.order_number)
            )
            and self._orders_are_merge_compatible(order, candidate)
        ]

    def merge_orders(
        self,
        order_id: int,
        payload: WorkOrderMergeRequest,
    ) -> WorkOrderDetail:
        included_order_ids = list(dict.fromkeys(payload.included_order_ids))
        if order_id in included_order_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Order cannot be merged into itself.",
            )

        self._lock_order(order_id)
        for included_order_id in included_order_ids:
            self._lock_order(included_order_id)
        receiver = self._get_order_or_404(order_id)
        self._validate_merge_receiver(receiver)
        included_orders = [
            self._get_order_or_404(included_order_id)
            for included_order_id in included_order_ids
        ]
        for included_order in included_orders:
            if not self._orders_are_merge_compatible(receiver, included_order):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        f"Order {included_order.order_number} is not available "
                        "for merging."
                    ),
                )

        family = self.session.scalar(
            select(WorkOrderFamily)
            .where(WorkOrderFamily.id == receiver.family_id)
            .with_for_update()
        )
        if family is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order family changed during merging.",
            )

        now = self._now_ts()
        receiver.quantity += sum(order.quantity for order in included_orders)
        receiver.estimated_minutes += sum(
            order.estimated_minutes for order in included_orders
        )
        receiver.taken_at = self._minimum_timestamp(
            [receiver.taken_at, *(order.taken_at for order in included_orders)]
        )
        receiver.cutting_started_at = self._minimum_timestamp(
            [
                receiver.cutting_started_at,
                *(order.cutting_started_at for order in included_orders),
            ]
        )
        for included_order in included_orders:
            self._merge_order_time_history(
                receiver_order_id=receiver.id,
                included_order_id=included_order.id,
                now=now,
            )
        self.session.flush()
        receiver.total_spent_seconds = self._get_effective_spent_seconds(receiver.id)
        receiver.cutting_spent_seconds = self._get_effective_spent_seconds(
            receiver.id,
            cutting_only=True,
        )
        receiver.updated_at = now
        for included_order in included_orders:
            self._store_qr_reference(
                included_order.id,
                family.base_order_number,
                now,
            )
            self.session.delete(included_order)
        self.session.flush()

        remaining_active_order_ids = self.session.scalars(
            select(WorkOrder.id).where(
                WorkOrder.family_id == family.id,
                WorkOrder.deleted_at.is_(None),
            )
        ).all()
        if (
            len(remaining_active_order_ids) == 1
            and remaining_active_order_ids[0] == receiver.id
        ):
            historical_orders = self.session.scalars(
                select(WorkOrder).where(
                    WorkOrder.family_id == family.id,
                    WorkOrder.id != receiver.id,
                )
            ).all()
            for historical_order in historical_orders:
                self._store_qr_reference(
                    historical_order.id,
                    family.base_order_number,
                    now,
                )
                self.session.delete(historical_order)
            self.session.flush()
            receiver.order_number = family.base_order_number
            receiver.family_id = None
            receiver.part_number = None
            self.session.flush()
            self.session.delete(family)

        self.session.commit()
        return self.get_order(receiver.id)

    def get_worker_orders_by_qr(
        self,
        *,
        worker_user_id: int,
        order_reference: str | None,
        legacy_order_id: int | None,
    ) -> WorkOrderQrTarget:
        resolved_reference = self._resolve_qr_reference(
            order_reference=order_reference,
            legacy_order_id=legacy_order_id,
        )
        family = self.session.scalar(
            select(WorkOrderFamily).where(
                WorkOrderFamily.base_order_number == resolved_reference
            )
        )
        order_filters: list[ColumnElement[bool]]
        if family is not None:
            order_filters = [WorkOrder.family_id == family.id]
        else:
            order_filters = [WorkOrder.order_number == resolved_reference]

        state_join = and_(
            WorkOrderAssignmentWorkerState.assignment_id == WorkOrderAssignment.id,
            WorkOrderAssignmentWorkerState.worker_user_id == worker_user_id,
        )
        order_ids = self.session.scalars(
            select(WorkOrder.id)
            .join(
                WorkOrderAssignment,
                WorkOrderAssignment.work_order_id == WorkOrder.id,
            )
            .outerjoin(WorkOrderAssignmentWorkerState, state_join)
            .where(
                *order_filters,
                WorkOrder.deleted_at.is_(None),
                WorkOrder.completed_at.is_(None),
                WorkOrder.quality_control_at.is_(None),
                WorkOrder.production_stage.in_(
                    [
                        WorkOrderProductionStage.CUTTING.value,
                        WorkOrderProductionStage.IN_WORK.value,
                    ]
                ),
                WorkOrderAssignment.worker_user_id == worker_user_id,
                or_(
                    WorkOrderAssignmentWorkerState.id.is_(None),
                    and_(
                        WorkOrderAssignmentWorkerState.hidden_at.is_(None),
                        WorkOrderAssignmentWorkerState.completed_at.is_(None),
                    ),
                ),
            )
            .order_by(WorkOrder.part_number.asc(), WorkOrder.id.asc())
        ).unique().all()
        orders = [self._get_order_or_404(order_id) for order_id in order_ids]

        serialized_orders = [
            self._serialize_order(
                order,
                order.product,
                assignment_worker_user_id=worker_user_id,
                assignment_worker_status_filter=(
                    WorkerAssignmentStatusFilter.IN_WORK
                ),
            )
            for order in orders
        ]
        return WorkOrderQrTarget(
            order_reference=resolved_reference,
            orders=[order for order in serialized_orders if order.assignments],
        )

    def update_worker_assignment_status(
        self,
        *,
        assignment_id: int,
        worker_user_id: int,
        payload: WorkOrderAssignmentWorkerStatusUpdate,
    ) -> WorkOrderDetail:
        assignment = self._get_worker_assignment_or_404(
            assignment_id=assignment_id,
            worker_user_id=worker_user_id,
        )
        order = assignment.work_order
        self._validate_order_is_not_deleted(order)

        state = self._get_assignment_worker_state(
            assignment_id=assignment.id,
            worker_user_id=worker_user_id,
        )
        now = self._now_ts()
        if state is None:
            state = WorkOrderAssignmentWorkerState(
                assignment_id=assignment.id,
                worker_user_id=worker_user_id,
                hidden_at=None,
                completed_at=None,
                created_at=now,
                updated_at=now,
            )
            self.session.add(state)

        if payload.status == WorkerAssignmentStatusFilter.IN_WORK:
            state.hidden_at = None
            state.completed_at = None
        elif payload.status == WorkerAssignmentStatusFilter.HIDDEN:
            state.hidden_at = now
            state.completed_at = None
        else:
            state.hidden_at = None
            state.completed_at = now

        state.updated_at = now
        self.session.commit()
        self.session.refresh(order)
        return self._serialize_order(
            order,
            order.product,
            assignment_worker_user_id=worker_user_id,
        )

    def create_order(self, payload: WorkOrderCreate) -> WorkOrderDetail:
        if payload.order_number is not None:
            self._validate_order_number(payload.order_number)
        product = self._get_product_or_404(payload.product_id)
        self._validate_product_is_active(product)
        self._validate_leather_type_is_active(payload.leather_type_id)
        self._validate_assignments(product.id, payload.assignments)

        timestamp = self._now_ts()
        order = WorkOrder(
            order_number=payload.order_number or self._generate_next_order_number(),
            product_id=product.id,
            leather_type_id=payload.leather_type_id,
            quantity=payload.quantity,
            planned_completion_date=payload.planned_completion_date,
            estimated_minutes=payload.estimated_minutes,
            total_spent_seconds=0,
            cutting_spent_seconds=0,
            production_stage=WorkOrderProductionStage.CREATED.value,
            created_at=timestamp,
            updated_at=timestamp,
            cutting_started_at=None,
        )
        order.assignments = self._build_assignments(payload.assignments)

        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return self.get_order(order.id)

    def update_order_planned_completion_date(
        self,
        order_id: int,
        payload: WorkOrderPlannedCompletionDateUpdate,
    ) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        order.planned_completion_date = payload.planned_completion_date
        order.updated_at = self._now_ts()
        self.session.commit()
        self.session.refresh(order)
        return self.get_order(order.id)

    def update_order_assignments(
        self,
        order_id: int,
        payload: WorkOrderUpdateAssignments,
    ) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        self._validate_order_is_not_deleted(order)
        product = self._get_product_or_404(order.product_id)
        leather_type_id = self._resolve_update_leather_type_id(order, payload)
        if payload.quantity != order.quantity:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Order quantity can only be changed by splitting or merging.",
            )
        attributes_changed = leather_type_id != order.leather_type_id
        assignments_changed = self._order_assignments_changed(order, payload)

        if attributes_changed:
            self._validate_order_has_no_spent_time(order)
            self._validate_leather_type_is_active(
                leather_type_id,
                current_leather_type_id=order.leather_type_id,
            )
        if assignments_changed:
            self._validate_order_assignments_can_be_changed(order)

        self._validate_assignments(product.id, payload.assignments)
        if assignments_changed:
            self._validate_removed_assignments_have_no_active_timers(
                order,
                payload.assignments,
            )

        order.leather_type_id = leather_type_id
        order.quantity = payload.quantity
        order.estimated_minutes = payload.estimated_minutes
        order.updated_at = self._now_ts()
        self._sync_assignments(order, payload.assignments)

        self.session.commit()
        self.session.refresh(order)
        return self.get_order(order.id)

    def update_order_status(
        self,
        order_id: int,
        payload: WorkOrderStatusUpdate,
    ) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        now = self._now_ts()
        self._validate_order_is_not_deleted(order)
        if payload.is_completed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Use quality control acceptance to complete order.",
            )
        if not payload.is_completed and order.completed_at is not None:
            order.quality_control_at = order.quality_control_at or now

        order.completed_at = None
        order.updated_at = now

        self.session.commit()
        self.session.refresh(order)
        return self.get_order(order.id)

    def update_order_quality_control_status(
        self,
        order_id: int,
        payload: WorkOrderQualityControlStatusUpdate,
    ) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        now = self._now_ts()
        self._validate_order_is_not_deleted(order)

        if payload.is_in_quality_control:
            if order.production_stage != WorkOrderProductionStage.IN_WORK.value:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Only orders in work can be sent to quality control.",
                )
            if order.completed_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Completed order cannot be sent to quality control.",
                )

            order.quality_control_at = order.quality_control_at or now
        else:
            order.quality_control_at = None
            order.completed_at = None
            order.defect_quantity = 0

        order.updated_at = now
        self.session.commit()
        self.session.refresh(order)
        return self.get_order(order.id)

    def accept_order_quality_control(
        self,
        order_id: int,
        payload: WorkOrderQualityControlAccept,
    ) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        now = self._now_ts()
        self._validate_order_is_not_deleted(order)

        if order.quality_control_at is None or order.completed_at is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Only orders in quality control can be accepted.",
            )

        if payload.defect_quantity > order.quantity:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Defect quantity cannot exceed order quantity.",
            )

        order.defect_quantity = payload.defect_quantity
        order.completed_at = now
        order.updated_at = now

        self.session.commit()
        self.session.refresh(order)
        return self.get_order(order.id)

    def update_order_production_stage(
        self,
        order_id: int,
        payload: WorkOrderProductionStageUpdate,
    ) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        now = self._now_ts()
        self._validate_order_is_not_deleted(order)
        if order.quality_control_at is not None or order.completed_at is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Стадию производства можно менять только до передачи в ОТК.",
            )

        current_stage = WorkOrderProductionStage(order.production_stage)
        target_stage = payload.production_stage
        if current_stage == target_stage:
            return self.get_order(order.id)

        allowed_transitions = {
            WorkOrderProductionStage.CREATED: {WorkOrderProductionStage.CUTTING},
            WorkOrderProductionStage.CUTTING: {
                WorkOrderProductionStage.CREATED,
                WorkOrderProductionStage.IN_WORK,
            },
            WorkOrderProductionStage.IN_WORK: {WorkOrderProductionStage.CUTTING},
        }
        if target_stage not in allowed_transitions[current_stage]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Недопустимый переход между стадиями заказа.",
            )

        if self._order_has_active_operation_timer(order.id):
            if target_stage == WorkOrderProductionStage.IN_WORK:
                detail = (
                    "Нельзя передать заказ в работу: сначала остановить "
                    "запущенные таймеры."
                )
            else:
                detail = (
                    "Нельзя изменить стадию заказа: сначала остановить "
                    "запущенные таймеры."
                )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=detail,
            )

        if (
            current_stage == WorkOrderProductionStage.CUTTING
            and target_stage == WorkOrderProductionStage.CREATED
            and self._order_has_spent_time(order.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Нельзя вернуть заказ в созданные после учета времени кроя."
                ),
            )

        order.production_stage = target_stage.value
        order.updated_at = now

        self.session.commit()
        self.session.refresh(order)
        return self.get_order(order.id)

    def update_order_deleted_status(
        self,
        order_id: int,
        payload: WorkOrderDeletedStatusUpdate,
    ) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        now = self._now_ts()
        order.deleted_at = now if payload.is_deleted else None
        order.updated_at = now

        self.session.commit()
        self.session.refresh(order)
        return self.get_order(order.id)

    def _build_worker_assignment_status_filters(
        self,
        worker_status_filter: WorkerAssignmentStatusFilter,
    ) -> list[ColumnElement[bool]]:
        if worker_status_filter == WorkerAssignmentStatusFilter.HIDDEN:
            return [
                WorkOrderAssignmentWorkerState.hidden_at.is_not(None),
                WorkOrderAssignmentWorkerState.completed_at.is_(None),
            ]

        if worker_status_filter == WorkerAssignmentStatusFilter.COMPLETED:
            return [
                WorkOrderAssignmentWorkerState.completed_at.is_not(None),
            ]

        return [
            WorkOrder.completed_at.is_(None),
            WorkOrder.quality_control_at.is_(None),
            WorkOrder.production_stage.in_(
                [
                    WorkOrderProductionStage.CUTTING.value,
                    WorkOrderProductionStage.IN_WORK.value,
                ]
            ),
            or_(
                WorkOrderAssignmentWorkerState.id.is_(None),
                and_(
                    WorkOrderAssignmentWorkerState.hidden_at.is_(None),
                    WorkOrderAssignmentWorkerState.completed_at.is_(None),
                ),
            ),
        ]

    def _split_eligibility(self, order_id: int) -> tuple[bool, str | None]:
        order = self.session.get(WorkOrder, order_id)
        if order is None:
            return False, "Order not found."
        if not self._is_order_in_work(order):
            return False, "Only an order in work can be split."
        if order.quantity < 2:
            return False, "Order must contain at least two items."

        if self._order_has_active_operation_timer(order.id):
            return False, "Сначала остановить запущенные таймеры заказа."

        return True, None

    def _is_order_in_work(self, order: WorkOrder) -> bool:
        return (
            order.production_stage == WorkOrderProductionStage.IN_WORK.value
            and order.quality_control_at is None
            and order.completed_at is None
            and order.deleted_at is None
        )

    def _order_has_active_operation_timer(self, order_id: int) -> bool:
        return bool(
            self.session.scalar(
                select(
                    exists().where(
                        TimerSession.order_id == order_id,
                        TimerSession.timer_type_code
                        == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                        TimerSession.ended_at.is_(None),
                    )
                )
            )
        )

    def _clone_assignments_for_split(
        self,
        order: WorkOrder,
        now: int,
    ) -> list[WorkOrderAssignment]:
        cloned_assignments: list[WorkOrderAssignment] = []
        for assignment in order.assignments:
            cloned_assignment = WorkOrderAssignment(
                operation_id=assignment.operation_id,
                worker_user_id=assignment.worker_user_id,
            )
            catalog_entry = assignment.operation.catalog_entry
            if (
                catalog_entry is not None
                and catalog_entry.operation_kind
                == OperationCatalogEntryKind.CUTTING.value
            ):
                cloned_assignment.worker_states = [
                    WorkOrderAssignmentWorkerState(
                        worker_user_id=state.worker_user_id,
                        hidden_at=None,
                        completed_at=state.completed_at,
                        created_at=now,
                        updated_at=now,
                    )
                    for state in assignment.worker_states
                    if state.completed_at is not None
                    and state.worker_user_id == assignment.worker_user_id
                ]
            cloned_assignments.append(cloned_assignment)

        return cloned_assignments

    def _initialize_order_time_allocations(self, order_id: int, now: int) -> None:
        sessions = self.session.scalars(
            select(TimerSession)
            .where(
                TimerSession.order_id == order_id,
                TimerSession.timer_type_code
                == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                TimerSession.ended_at.is_not(None),
            )
            .order_by(TimerSession.id.asc())
        ).all()
        if not sessions:
            return

        session_ids = [timer_session.id for timer_session in sessions]
        allocated_session_ids = set(
            self.session.scalars(
                select(WorkOrderTimeAllocation.timer_session_id).where(
                    WorkOrderTimeAllocation.timer_session_id.in_(session_ids)
                )
            ).all()
        )
        raw_sessions = [
            timer_session
            for timer_session in sessions
            if timer_session.id not in allocated_session_ids
        ]
        durations_ms = [
            max(0, (timer_session.ended_at or 0) - timer_session.started_at)
            for timer_session in raw_sessions
        ]
        allocated_seconds = [duration_ms // 1000 for duration_ms in durations_ms]
        target_seconds = sum(durations_ms) // 1000
        remaining_seconds = target_seconds - sum(allocated_seconds)
        remainder_order = sorted(
            range(len(raw_sessions)),
            key=lambda index: (durations_ms[index] % 1000, -raw_sessions[index].id),
            reverse=True,
        )
        for index in remainder_order[:remaining_seconds]:
            allocated_seconds[index] += 1

        self.session.add_all(
            [
                WorkOrderTimeAllocation(
                    timer_session_id=timer_session.id,
                    work_order_id=order_id,
                    allocated_seconds=seconds,
                    created_at=now,
                    updated_at=now,
                )
                for timer_session, seconds in zip(
                    raw_sessions,
                    allocated_seconds,
                    strict=True,
                )
            ]
        )
        self.session.flush()

    def _split_order_time_allocations(
        self,
        *,
        source_order_id: int,
        created_order_id: int,
        created_quantity: int,
        original_quantity: int,
        now: int,
    ) -> tuple[int, int]:
        allocations = self.session.scalars(
            select(WorkOrderTimeAllocation)
            .where(WorkOrderTimeAllocation.work_order_id == source_order_id)
            .order_by(WorkOrderTimeAllocation.timer_session_id.asc())
        ).all()
        if not allocations:
            return 0, 0

        total_seconds = sum(allocation.allocated_seconds for allocation in allocations)
        created_total_seconds = (
            total_seconds * created_quantity // original_quantity
        )
        created_seconds_by_allocation = [
            allocation.allocated_seconds * created_quantity // original_quantity
            for allocation in allocations
        ]
        remaining_seconds = created_total_seconds - sum(
            created_seconds_by_allocation
        )
        remainder_order = sorted(
            range(len(allocations)),
            key=lambda index: (
                allocations[index].allocated_seconds
                * created_quantity
                % original_quantity,
                -allocations[index].timer_session_id,
            ),
            reverse=True,
        )
        for index in remainder_order[:remaining_seconds]:
            created_seconds_by_allocation[index] += 1

        for allocation, created_seconds in zip(
            allocations,
            created_seconds_by_allocation,
            strict=True,
        ):
            allocation.allocated_seconds -= created_seconds
            allocation.updated_at = now
            self.session.add(
                WorkOrderTimeAllocation(
                    timer_session_id=allocation.timer_session_id,
                    work_order_id=created_order_id,
                    allocated_seconds=created_seconds,
                    created_at=now,
                    updated_at=now,
                )
            )

        source_total_seconds = total_seconds - created_total_seconds
        return source_total_seconds, created_total_seconds

    def _get_effective_spent_seconds(
        self,
        order_id: int,
        *,
        cutting_only: bool = False,
    ) -> int:
        effective_time = build_effective_operation_time_subquery()
        stmt = select(
            func.coalesce(func.sum(effective_time.c.elapsed_ms), 0)
        ).select_from(effective_time)
        if cutting_only:
            stmt = stmt.join(
                Operation,
                Operation.id == effective_time.c.operation_id,
            ).join(
                OperationCatalogEntry,
                OperationCatalogEntry.id == Operation.operation_catalog_entry_id,
            )
        stmt = stmt.where(effective_time.c.order_id == order_id)
        if cutting_only:
            stmt = stmt.where(
                OperationCatalogEntry.operation_kind
                == OperationCatalogEntryKind.CUTTING.value
            )
        elapsed_ms = int(self.session.scalar(stmt) or 0)
        return elapsed_ms // 1000

    def _merge_order_time_history(
        self,
        *,
        receiver_order_id: int,
        included_order_id: int,
        now: int,
    ) -> None:
        allocations = self.session.scalars(
            select(WorkOrderTimeAllocation).where(
                WorkOrderTimeAllocation.work_order_id == included_order_id
            )
        ).all()
        for allocation in allocations:
            receiver_allocation = self.session.scalar(
                select(WorkOrderTimeAllocation).where(
                    WorkOrderTimeAllocation.timer_session_id
                    == allocation.timer_session_id,
                    WorkOrderTimeAllocation.work_order_id == receiver_order_id,
                )
            )
            if receiver_allocation is None:
                allocation.work_order_id = receiver_order_id
                allocation.updated_at = now
                continue
            receiver_allocation.allocated_seconds += allocation.allocated_seconds
            receiver_allocation.updated_at = now
            self.session.delete(allocation)

        timer_sessions = self.session.scalars(
            select(TimerSession).where(TimerSession.order_id == included_order_id)
        ).all()
        for timer_session in timer_sessions:
            has_allocations = self.session.scalar(
                select(
                    exists().where(
                        WorkOrderTimeAllocation.timer_session_id == timer_session.id
                    )
                )
            )
            if not has_allocations:
                timer_session.order_id = receiver_order_id

    def _minimum_timestamp(self, values: Sequence[int | None]) -> int | None:
        present_values = [value for value in values if value is not None]
        return min(present_values) if present_values else None

    def _validate_merge_receiver(self, order: WorkOrder) -> None:
        if order.family_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Only an order from a split family can be merged.",
            )
        if not self._is_order_in_work(order):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Only an order in work can receive merged orders.",
            )
        if self._order_has_active_operation_timer(order.id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Сначала остановить запущенные таймеры заказа.",
            )
        if not self._all_assignment_states_are_in_work(order):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Every assignment must be in work before merging.",
            )

    def _merge_receiver_is_eligible(self, order_id: int) -> bool:
        order = self._get_order_or_404(order_id)
        return (
            order.family_id is not None
            and self._is_order_in_work(order)
            and not self._order_has_active_operation_timer(order.id)
            and self._all_assignment_states_are_in_work(order)
        )

    def _orders_are_merge_compatible(
        self,
        receiver: WorkOrder,
        candidate: WorkOrder,
    ) -> bool:
        if receiver.family_id is None or candidate.family_id != receiver.family_id:
            return False
        if not self._is_order_in_work(candidate):
            return False
        if self._order_has_active_operation_timer(candidate.id):
            return False
        if not self._all_assignment_states_are_in_work(candidate):
            return False
        if (
            candidate.product_id != receiver.product_id
            or candidate.leather_type_id != receiver.leather_type_id
            or candidate.planned_completion_date
            != receiver.planned_completion_date
        ):
            return False

        return self._assignment_signature(candidate) == self._assignment_signature(
            receiver
        )

    def _assignment_signature(
        self,
        order: WorkOrder,
    ) -> set[tuple[int, int | None]]:
        return {
            (assignment.operation_id, assignment.worker_user_id)
            for assignment in order.assignments
        }

    def _all_assignment_states_are_in_work(self, order: WorkOrder) -> bool:
        return all(
            state.hidden_at is None and state.completed_at is None
            for assignment in order.assignments
            for state in assignment.worker_states
        )

    def _order_has_timer_history(self, order_id: int) -> bool:
        raw_session_exists = self.session.scalar(
            select(exists().where(TimerSession.order_id == order_id))
        )
        allocation_exists = self.session.scalar(
            select(
                exists().where(WorkOrderTimeAllocation.work_order_id == order_id)
            )
        )
        return bool(raw_session_exists or allocation_exists)

    def _store_qr_reference(
        self,
        legacy_order_id: int,
        order_reference: str,
        now: int,
    ) -> None:
        reference = self.session.get(WorkOrderQrReference, legacy_order_id)
        if reference is None:
            self.session.add(
                WorkOrderQrReference(
                    legacy_order_id=legacy_order_id,
                    order_reference=order_reference,
                    created_at=now,
                )
            )
            return
        reference.order_reference = order_reference

    def _resolve_qr_reference(
        self,
        *,
        order_reference: str | None,
        legacy_order_id: int | None,
    ) -> str:
        if order_reference is not None:
            normalized_reference = order_reference.strip()
            if not normalized_reference:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Order reference must not be empty.",
                )
            family_exists = self.session.scalar(
                select(
                    exists().where(
                        WorkOrderFamily.base_order_number == normalized_reference
                    )
                )
            )
            if family_exists:
                return normalized_reference
            order = self.session.scalar(
                select(WorkOrder).where(
                    WorkOrder.order_number == normalized_reference
                )
            )
            if order is not None:
                return (
                    order.family.base_order_number
                    if order.family is not None
                    else order.order_number
                )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order reference not found.",
            )

        if legacy_order_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Order reference or legacy order id is required.",
            )
        order = self.session.get(WorkOrder, legacy_order_id)
        if order is not None:
            return (
                order.family.base_order_number
                if order.family is not None
                else order.order_number
            )
        reference = self.session.get(WorkOrderQrReference, legacy_order_id)
        if reference is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order reference not found.",
            )
        return reference.order_reference

    def _lock_order(self, order_id: int) -> None:
        self.session.execute(
            select(WorkOrder.id)
            .where(WorkOrder.id == order_id)
            .with_for_update()
        ).scalar_one_or_none()

    def _get_worker_assignment_or_404(
        self,
        *,
        assignment_id: int,
        worker_user_id: int,
    ) -> WorkOrderAssignment:
        stmt: Select[tuple[WorkOrderAssignment]] = (
            select(WorkOrderAssignment)
            .options(
                selectinload(WorkOrderAssignment.work_order).selectinload(
                    WorkOrder.assignments
                ),
                selectinload(WorkOrderAssignment.work_order)
                .selectinload(WorkOrder.assignments)
                .selectinload(WorkOrderAssignment.operation),
                selectinload(WorkOrderAssignment.work_order)
                .selectinload(WorkOrder.assignments)
                .selectinload(WorkOrderAssignment.operation)
                .selectinload(Operation.catalog_entry),
                selectinload(WorkOrderAssignment.work_order)
                .selectinload(WorkOrder.assignments)
                .selectinload(WorkOrderAssignment.worker_user),
                selectinload(WorkOrderAssignment.work_order)
                .selectinload(WorkOrder.assignments)
                .selectinload(WorkOrderAssignment.worker_states),
            )
            .where(
                WorkOrderAssignment.id == assignment_id,
                WorkOrderAssignment.worker_user_id == worker_user_id,
            )
        )
        assignment = self.session.scalars(stmt).one_or_none()
        if assignment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker assignment not found.",
            )
        return assignment

    def _get_assignment_worker_state(
        self,
        *,
        assignment_id: int,
        worker_user_id: int,
    ) -> WorkOrderAssignmentWorkerState | None:
        stmt: Select[tuple[WorkOrderAssignmentWorkerState]] = select(
            WorkOrderAssignmentWorkerState
        ).where(
            WorkOrderAssignmentWorkerState.assignment_id == assignment_id,
            WorkOrderAssignmentWorkerState.worker_user_id == worker_user_id,
        )
        return self.session.scalars(stmt).one_or_none()

    def _validate_order_is_not_deleted(self, order: WorkOrder) -> None:
        if order.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Deleted order cannot be changed.",
            )

    def _validate_order_assignments_can_be_changed(self, order: WorkOrder) -> None:
        if order.completed_at is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Completed order assignments cannot be changed.",
            )
        if order.quality_control_at is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Order assignments cannot be changed after quality control stage."
                ),
            )

    def _validate_order_has_no_spent_time(self, order: WorkOrder) -> None:
        if self._order_has_spent_time(order.id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Order cannot be changed after time has been spent.",
            )

    def _order_assignments_changed(
        self,
        order: WorkOrder,
        payload: WorkOrderUpdateAssignments,
    ) -> bool:
        current_assignments = {
            (assignment.operation_id, assignment.worker_user_id)
            for assignment in order.assignments
        }
        incoming_assignments = {
            (assignment.operation_id, assignment.worker_user_id)
            for assignment in payload.assignments
        }

        return incoming_assignments != current_assignments

    def _validate_removed_assignments_have_no_active_timers(
        self,
        order: WorkOrder,
        assignments: Sequence[WorkOrderAssignmentCreate],
    ) -> None:
        incoming_assignment_keys = {
            (assignment.operation_id, assignment.worker_user_id)
            for assignment in assignments
            if assignment.worker_user_id is not None
        }
        removed_assignment_keys = {
            (assignment.operation_id, assignment.worker_user_id)
            for assignment in order.assignments
            if assignment.worker_user_id is not None
        } - incoming_assignment_keys
        if not removed_assignment_keys:
            return

        active_timer_keys = set(
            self.session.execute(
                select(TimerSession.operation_id, TimerSession.user_id).where(
                    TimerSession.order_id == order.id,
                    TimerSession.timer_type_code
                    == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    TimerSession.ended_at.is_(None),
                )
            ).tuples().all()
        )
        if removed_assignment_keys & active_timer_keys:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Нельзя удалить исполнителя из операции: сначала остановить "
                    "его запущенный таймер."
                ),
            )

    def _order_has_spent_time(self, order_id: int) -> bool:
        active_session_exists = self.session.scalar(
            select(
                exists().where(
                    TimerSession.order_id == order_id,
                    TimerSession.timer_type_code
                    == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                    TimerSession.ended_at.is_(None),
                )
            )
        )
        effective_time = build_effective_operation_time_subquery()
        completed_time_exists = self.session.scalar(
            select(
                exists()
                .select_from(effective_time)
                .where(
                    effective_time.c.order_id == order_id,
                    effective_time.c.elapsed_ms > 0,
                )
            )
        )
        return bool(active_session_exists or completed_time_exists)

    def _build_spent_time_subquery(self) -> Any:
        effective_time = build_effective_operation_time_subquery()
        active_orders = select(TimerSession.order_id.label("order_id")).where(
            TimerSession.order_id.is_not(None),
            TimerSession.timer_type_code == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            TimerSession.ended_at.is_(None),
        )
        completed_orders = select(effective_time.c.order_id.label("order_id")).where(
            effective_time.c.elapsed_ms > 0
        )
        spent_orders = union_all(active_orders, completed_orders).subquery()
        return (
            select(
                spent_orders.c.order_id,
                func.count().label("spent_sessions_count"),
            )
            .group_by(spent_orders.c.order_id)
            .subquery()
        )

    def _build_spent_time_filters(
        self,
        *,
        order_id: int | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [
            TimerSession.order_id.is_not(None),
            TimerSession.timer_type_code == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            or_(
                TimerSession.ended_at.is_(None),
                TimerSession.ended_at > TimerSession.started_at,
            ),
        ]
        if order_id is not None:
            filters.append(TimerSession.order_id == order_id)

        return filters

    def _get_order_or_404(self, order_id: int) -> WorkOrder:
        stmt: Select[tuple[WorkOrder]] = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.assignments)
                .selectinload(WorkOrderAssignment.operation)
                .selectinload(Operation.catalog_entry),
                selectinload(WorkOrder.assignments).selectinload(
                    WorkOrderAssignment.worker_user
                ),
                selectinload(WorkOrder.assignments).selectinload(
                    WorkOrderAssignment.worker_states
                ),
            )
            .where(WorkOrder.id == order_id)
        )
        order = self.session.scalars(stmt).one_or_none()
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found.",
            )
        return order

    def _get_product_or_404(self, product_id: int) -> Product:
        product = self.session.get(Product, product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found.",
            )
        return product

    def _validate_product_is_active(self, product: Product) -> None:
        if not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Only active products can be taken into work.",
            )

    def _validate_leather_type_is_active(
        self,
        leather_type_id: int | None,
        *,
        current_leather_type_id: int | None = None,
    ) -> None:
        if leather_type_id is None:
            return

        if leather_type_id == current_leather_type_id:
            return

        leather_type = self.session.get(LeatherType, leather_type_id)
        if leather_type is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Leather type not found.",
            )

        if not leather_type.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Only active leather types can be selected.",
            )

    def _resolve_update_leather_type_id(
        self,
        order: WorkOrder,
        payload: WorkOrderUpdateAssignments,
    ) -> int | None:
        if "leather_type_id" not in payload.model_fields_set:
            return order.leather_type_id

        return payload.leather_type_id

    def _validate_order_number(self, order_number: str) -> None:
        if self._order_number_is_reserved(order_number):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Order with this number already exists.",
            )

    def _order_number_is_reserved(self, order_number: str) -> bool:
        existing_order_id = self.session.execute(
            select(WorkOrder.id).where(WorkOrder.order_number == order_number)
        ).scalar_one_or_none()
        family_id = self.session.execute(
            select(WorkOrderFamily.id).where(
                WorkOrderFamily.base_order_number == order_number
            )
        ).scalar_one_or_none()
        return existing_order_id is not None or family_id is not None

    def _generate_next_order_number(self) -> str:
        while True:
            next_value = self.session.execute(
                update(WorkOrderNumberCounter)
                .where(WorkOrderNumberCounter.id == 1)
                .values(last_value=WorkOrderNumberCounter.last_value + 1)
                .returning(WorkOrderNumberCounter.last_value)
            ).scalar_one_or_none()
            if next_value is None:
                raise RuntimeError("Work order number counter is not initialized.")

            order_number = str(next_value)
            if not self._order_number_is_reserved(order_number):
                return order_number

    def _validate_assignments(
        self,
        product_id: int,
        assignments: Sequence[WorkOrderAssignmentCreate],
    ) -> None:
        operations = self.session.scalars(
            select(Operation).where(Operation.product_id == product_id)
        ).all()
        if not operations:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Product has no operations.",
            )

        leaf_operation_ids = self._collect_leaf_operation_ids(operations)
        assigned_operation_ids = {assignment.operation_id for assignment in assignments}
        assignment_keys = [
            (assignment.operation_id, assignment.worker_user_id)
            for assignment in assignments
        ]
        if len(set(assignment_keys)) != len(assignment_keys):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A worker can be assigned to an operation only once.",
            )

        if assigned_operation_ids != leaf_operation_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Assignments must cover every leaf operation of the product.",
            )

        worker_ids_by_operation: dict[int, list[int | None]] = {}
        for assignment in assignments:
            worker_ids_by_operation.setdefault(assignment.operation_id, []).append(
                assignment.worker_user_id
            )
        if any(
            None in worker_ids and len(worker_ids) > 1
            for worker_ids in worker_ids_by_operation.values()
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "An unassigned operation cannot contain additional worker "
                    "assignments."
                ),
            )

        worker_ids = {
            assignment.worker_user_id
            for assignment in assignments
            if assignment.worker_user_id is not None
        }
        workers = self.session.scalars(
            select(User).where(User.id.in_(worker_ids))
        ).all()
        workers_by_id = {worker.id: worker for worker in workers}

        for assignment in assignments:
            if assignment.worker_user_id is None:
                continue

            worker = workers_by_id.get(assignment.worker_user_id)
            if worker is None or worker.deleted_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Assigned worker not found.",
                )
            if not worker.is_active or "worker" not in worker.roles:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Assigned user must be an active worker.",
                )

    def _collect_leaf_operation_ids(self, operations: Sequence[Operation]) -> set[int]:
        parent_ids = {
            operation.parent_id
            for operation in operations
            if operation.parent_id is not None
        }
        return {
            operation.id for operation in operations if operation.id not in parent_ids
        }

    def _build_assignments(
        self,
        assignments: Sequence[WorkOrderAssignmentCreate],
    ) -> list[WorkOrderAssignment]:
        return [
            WorkOrderAssignment(
                operation_id=assignment.operation_id,
                worker_user_id=assignment.worker_user_id,
            )
            for assignment in assignments
        ]

    def _sync_assignments(
        self,
        order: WorkOrder,
        assignments: Sequence[WorkOrderAssignmentCreate],
    ) -> None:
        existing_by_key = {
            (assignment.operation_id, assignment.worker_user_id): assignment
            for assignment in order.assignments
        }
        incoming_by_key = {
            (assignment.operation_id, assignment.worker_user_id): assignment
            for assignment in assignments
        }

        for existing_assignment in list(order.assignments):
            existing_key = (
                existing_assignment.operation_id,
                existing_assignment.worker_user_id,
            )
            if existing_key not in incoming_by_key:
                order.assignments.remove(existing_assignment)
                self.session.delete(existing_assignment)

        for incoming_key, incoming_assignment in incoming_by_key.items():
            if incoming_key not in existing_by_key:
                order.assignments.append(
                    WorkOrderAssignment(
                        operation_id=incoming_assignment.operation_id,
                        worker_user_id=incoming_assignment.worker_user_id,
                    )
                )

    def _serialize_order(
        self,
        order: WorkOrder,
        product: Product,
        *,
        assignment_worker_user_id: int | None = None,
        assignment_worker_status_filter: WorkerAssignmentStatusFilter | None = None,
    ) -> WorkOrderDetail:
        assignments = [
            assignment
            for assignment in order.assignments
            if (
                assignment_worker_user_id is None
                or assignment.worker_user_id == assignment_worker_user_id
            )
            and self._assignment_matches_worker_status(
                assignment,
                assignment_worker_user_id,
                assignment_worker_status_filter,
            )
            and (
                assignment_worker_user_id is None
                or assignment_worker_status_filter
                != WorkerAssignmentStatusFilter.IN_WORK
                or self._assignment_matches_production_stage(order, assignment)
            )
        ]

        return WorkOrderDetail(
            id=order.id,
            order_number=order.order_number,
            family_id=order.family_id,
            part_number=order.part_number,
            family_base_order_number=(
                order.family.base_order_number if order.family is not None else None
            ),
            product_id=order.product_id,
            product_name=product.name,
            product_version=product.version,
            product_comment=product.comment,
            leather_type_id=order.leather_type_id,
            leather_type_name=order.leather_type.name
            if order.leather_type is not None
            else None,
            quantity=order.quantity,
            planned_completion_date=order.planned_completion_date,
            estimated_minutes=order.estimated_minutes,
            total_spent_seconds=order.total_spent_seconds,
            cutting_spent_seconds=order.cutting_spent_seconds,
            has_spent_time=self._order_has_spent_time(order.id),
            created_at=order.created_at,
            updated_at=order.updated_at,
            production_stage=order.production_stage,
            cutting_started_at=order.cutting_started_at,
            taken_at=order.taken_at,
            quality_control_at=order.quality_control_at,
            defect_quantity=order.defect_quantity,
            completed_at=order.completed_at,
            deleted_at=order.deleted_at,
            assignments=[
                self._serialize_assignment(
                    assignment,
                    assignment_worker_user_id,
                )
                for assignment in assignments
            ],
        )

    def _assignment_matches_worker_status(
        self,
        assignment: WorkOrderAssignment,
        worker_user_id: int | None,
        status_filter: WorkerAssignmentStatusFilter | None,
    ) -> bool:
        if status_filter is None:
            return True

        state = self._get_assignment_worker_state_for_user(
            assignment,
            worker_user_id,
        )

        if status_filter == WorkerAssignmentStatusFilter.COMPLETED:
            return state is not None and state.completed_at is not None

        if status_filter == WorkerAssignmentStatusFilter.HIDDEN:
            return (
                state is not None
                and state.hidden_at is not None
                and state.completed_at is None
            )

        return state is None or (state.hidden_at is None and state.completed_at is None)

    def _assignment_matches_production_stage(
        self,
        order: WorkOrder,
        assignment: WorkOrderAssignment,
    ) -> bool:
        catalog_entry = assignment.operation.catalog_entry
        operation_kind = (
            catalog_entry.operation_kind
            if catalog_entry is not None
            else OperationCatalogEntryKind.REGULAR.value
        )
        if order.production_stage == WorkOrderProductionStage.CUTTING.value:
            return operation_kind == OperationCatalogEntryKind.CUTTING.value
        if order.production_stage == WorkOrderProductionStage.IN_WORK.value:
            return operation_kind != OperationCatalogEntryKind.CUTTING.value
        return False

    def _serialize_assignment(
        self,
        assignment: WorkOrderAssignment,
        worker_user_id: int | None,
    ) -> WorkOrderAssignmentRead:
        state = self._get_assignment_worker_state_for_user(
            assignment,
            worker_user_id,
        )
        worker_status = WorkerAssignmentStatusFilter.IN_WORK
        if state is not None and state.completed_at is not None:
            worker_status = WorkerAssignmentStatusFilter.COMPLETED
        elif state is not None and state.hidden_at is not None:
            worker_status = WorkerAssignmentStatusFilter.HIDDEN

        return WorkOrderAssignmentRead(
            id=assignment.id,
            operation_id=assignment.operation_id,
            operation_name=self._get_operation_name(assignment.operation),
            worker_user_id=assignment.worker_user_id,
            worker_user_name=assignment.worker_user.name
            if assignment.worker_user is not None
            else None,
            worker_status=worker_status,
            worker_hidden_at=state.hidden_at if state is not None else None,
            worker_completed_at=state.completed_at if state is not None else None,
        )

    def _get_operation_name(self, operation: Operation) -> str:
        if operation.catalog_entry is not None:
            return operation.catalog_entry.name
        return operation.name

    def _get_assignment_worker_state_for_user(
        self,
        assignment: WorkOrderAssignment,
        worker_user_id: int | None,
    ) -> WorkOrderAssignmentWorkerState | None:
        if worker_user_id is None:
            return None

        return next(
            (
                state
                for state in assignment.worker_states
                if state.worker_user_id == worker_user_id
            ),
            None,
        )

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, or_, select
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
)
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
    WorkOrderPage,
    WorkOrderPlannedCompletionDateUpdate,
    WorkOrderQualityControlAccept,
    WorkOrderQualityControlStatusUpdate,
    WorkOrderSortField,
    WorkOrderStatusFilter,
    WorkOrderStatusUpdate,
    WorkOrderTakenStatusUpdate,
    WorkOrderTimeBreakdown,
    WorkOrderTimeBreakdownItem,
    WorkOrderUpdateAssignments,
)
from app.schemas.timer import TimerType
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
                WorkOrder.product_id,
                Product.name.label("product_name"),
                Product.version.label("product_version"),
                WorkOrder.leather_type_id,
                LeatherType.name.label("leather_type_name"),
                WorkOrder.quantity,
                WorkOrder.planned_completion_date,
                WorkOrder.estimated_minutes,
                WorkOrder.total_spent_minutes,
                WorkOrder.created_at,
                WorkOrder.updated_at,
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
        items = [
            WorkOrderListItem(
                id=row.id,
                order_number=row.order_number,
                product_id=row.product_id,
                product_name=row.product_name,
                product_version=row.product_version,
                leather_type_id=row.leather_type_id,
                leather_type_name=row.leather_type_name,
                quantity=row.quantity,
                planned_completion_date=row.planned_completion_date,
                estimated_minutes=row.estimated_minutes,
                total_spent_minutes=row.total_spent_minutes,
                has_spent_time=row.spent_sessions_count > 0,
                assignments_count=row.assignments_count,
                created_at=row.created_at,
                updated_at=row.updated_at,
                taken_at=row.taken_at,
                quality_control_at=row.quality_control_at,
                defect_quantity=row.defect_quantity,
                completed_at=row.completed_at,
                deleted_at=row.deleted_at,
            )
            for row in rows
        ]
        filtered_items = [
            item
            for item in items
            if self._matches_order_search(item, normalized_search)
        ]
        total = len(filtered_items)
        pages = max(1, (total + page_size - 1) // page_size)
        page_start = (page - 1) * page_size
        page_end = page_start + page_size

        return WorkOrderPage(
            items=filtered_items[page_start:page_end],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

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
                    WorkOrder.taken_at.is_(None),
                ]
            )
        elif status_filter == WorkOrderStatusFilter.IN_WORK:
            filters.extend(
                [
                    WorkOrder.deleted_at.is_(None),
                    WorkOrder.completed_at.is_(None),
                    WorkOrder.quality_control_at.is_(None),
                    WorkOrder.taken_at.is_not(None),
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

        stmt = (
            select(
                TimerSession.operation_id,
                func.coalesce(
                    OperationCatalogEntry.name,
                    Operation.name,
                    "Операция удалена",
                ).label("operation_name"),
                TimerSession.user_id,
                User.name.label("worker_user_name"),
                Operation.standard_time_seconds,
                func.coalesce(
                    func.sum(TimerSession.ended_at - TimerSession.started_at),
                    0,
                ).label("elapsed_ms"),
            )
            .join(User, User.id == TimerSession.user_id)
            .outerjoin(Operation, Operation.id == TimerSession.operation_id)
            .outerjoin(
                OperationCatalogEntry,
                OperationCatalogEntry.id == Operation.operation_catalog_entry_id,
            )
            .where(
                TimerSession.order_id == order_id,
                TimerSession.timer_type_code == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                TimerSession.ended_at.is_not(None),
            )
            .group_by(
                TimerSession.operation_id,
                OperationCatalogEntry.name,
                Operation.name,
                TimerSession.user_id,
                User.name,
                Operation.standard_time_seconds,
            )
            .order_by(
                OperationCatalogEntry.name.asc(),
                Operation.name.asc(),
                User.name.asc(),
                TimerSession.user_id.asc(),
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
                for assignment in order.assignments
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

        return [
            self._serialize_order(
                order,
                order.product,
                assignment_worker_user_id=worker_user_id,
                assignment_worker_status_filter=worker_status_filter,
            )
            for order in orders
        ]

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
        self._validate_order_number(payload.order_number)
        product = self._get_product_or_404(payload.product_id)
        self._validate_product_is_active(product)
        self._validate_leather_type_is_active(payload.leather_type_id)
        self._validate_assignments(product.id, payload.assignments)

        timestamp = self._now_ts()
        order = WorkOrder(
            order_number=payload.order_number,
            product_id=product.id,
            leather_type_id=payload.leather_type_id,
            quantity=payload.quantity,
            planned_completion_date=payload.planned_completion_date,
            estimated_minutes=payload.estimated_minutes,
            total_spent_minutes=0,
            created_at=timestamp,
            updated_at=timestamp,
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
        attributes_changed = (
            leather_type_id != order.leather_type_id
            or payload.quantity != order.quantity
        )
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
            if order.taken_at is None:
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

    def update_order_taken_status(
        self,
        order_id: int,
        payload: WorkOrderTakenStatusUpdate,
    ) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        now = self._now_ts()
        self._validate_order_is_not_deleted(order)
        if payload.is_taken:
            order.taken_at = order.taken_at or now
        else:
            order.taken_at = None
            order.quality_control_at = None
            order.completed_at = None
            order.defect_quantity = 0
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
            WorkOrder.taken_at.is_not(None),
            or_(
                WorkOrderAssignmentWorkerState.id.is_(None),
                and_(
                    WorkOrderAssignmentWorkerState.hidden_at.is_(None),
                    WorkOrderAssignmentWorkerState.completed_at.is_(None),
                ),
            ),
        ]

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
            assignment.operation_id: assignment.worker_user_id
            for assignment in order.assignments
        }
        incoming_assignments = {
            assignment.operation_id: assignment.worker_user_id
            for assignment in payload.assignments
        }

        return incoming_assignments != current_assignments

    def _order_has_spent_time(self, order_id: int) -> bool:
        stmt = select(func.count(TimerSession.id)).where(
            *self._build_spent_time_filters(order_id=order_id),
        )
        return int(self.session.execute(stmt).scalar_one()) > 0

    def _build_spent_time_subquery(self) -> Any:
        return (
            select(
                TimerSession.order_id,
                func.count(TimerSession.id).label("spent_sessions_count"),
            )
            .where(*self._build_spent_time_filters())
            .group_by(TimerSession.order_id)
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
        stmt = select(WorkOrder.id).where(WorkOrder.order_number == order_number)
        existing_order_id = self.session.execute(stmt).scalar_one_or_none()
        if existing_order_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Order with this number already exists.",
            )

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
        assigned_operation_ids = [assignment.operation_id for assignment in assignments]

        if len(set(assigned_operation_ids)) != len(assigned_operation_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Operations must be assigned only once per order.",
            )

        if set(assigned_operation_ids) != leaf_operation_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Assignments must cover every leaf operation of the product.",
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
        existing_by_operation_id = {
            assignment.operation_id: assignment for assignment in order.assignments
        }
        incoming_operation_ids = {assignment.operation_id for assignment in assignments}

        for existing_assignment in list(order.assignments):
            if existing_assignment.operation_id not in incoming_operation_ids:
                order.assignments.remove(existing_assignment)
                self.session.delete(existing_assignment)

        for incoming_assignment in assignments:
            existing_assignment = existing_by_operation_id.get(
                incoming_assignment.operation_id
            )
            if existing_assignment is None:
                order.assignments.append(
                    WorkOrderAssignment(
                        operation_id=incoming_assignment.operation_id,
                        worker_user_id=incoming_assignment.worker_user_id,
                    )
                )
                continue

            if existing_assignment.worker_user_id != incoming_assignment.worker_user_id:
                for state in list(existing_assignment.worker_states):
                    self.session.delete(state)
            existing_assignment.worker_user_id = incoming_assignment.worker_user_id

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
        ]

        return WorkOrderDetail(
            id=order.id,
            order_number=order.order_number,
            product_id=order.product_id,
            product_name=product.name,
            product_version=product.version,
            leather_type_id=order.leather_type_id,
            leather_type_name=order.leather_type.name
            if order.leather_type is not None
            else None,
            quantity=order.quantity,
            planned_completion_date=order.planned_completion_date,
            estimated_minutes=order.estimated_minutes,
            total_spent_minutes=order.total_spent_minutes,
            has_spent_time=self._order_has_spent_time(order.id),
            created_at=order.created_at,
            updated_at=order.updated_at,
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

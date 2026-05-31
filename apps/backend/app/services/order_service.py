from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.leather_type import LeatherType
from app.models.operation import Operation
from app.models.product import Product
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderAssignment
from app.schemas.order import (
    SortDirection,
    WorkOrderAssignmentCreate,
    WorkOrderAssignmentRead,
    WorkOrderCreate,
    WorkOrderDetail,
    WorkOrderListItem,
    WorkOrderPage,
    WorkOrderSortField,
    WorkOrderStatusUpdate,
    WorkOrderUpdateAssignments,
)


class OrderService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_orders(
        self,
        *,
        search: str | None,
        include_completed: bool,
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
        filters = self._build_order_list_filters(
            include_completed=include_completed,
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
                WorkOrder.total_spent_minutes,
                WorkOrder.created_at,
                WorkOrder.updated_at,
                WorkOrder.completed_at,
                func.coalesce(assignments_count.c.assignments_count, 0).label(
                    "assignments_count"
                ),
            )
            .join(Product, Product.id == WorkOrder.product_id)
            .outerjoin(LeatherType, LeatherType.id == WorkOrder.leather_type_id)
            .outerjoin(
                assignments_count,
                assignments_count.c.work_order_id == WorkOrder.id,
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
                total_spent_minutes=row.total_spent_minutes,
                assignments_count=row.assignments_count,
                created_at=row.created_at,
                updated_at=row.updated_at,
                completed_at=row.completed_at,
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
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []

        if not include_completed:
            filters.append(WorkOrder.completed_at.is_(None))

        return filters

    def _matches_order_search(
        self,
        order: WorkOrderListItem,
        normalized_search: str,
    ) -> bool:
        if not normalized_search:
            return True

        return (
            normalized_search in self._normalize_order_search(order.order_number)
            or normalized_search in self._normalize_order_search(order.product_name)
        )

    def _normalize_order_search(self, value: str) -> str:
        return value.strip().casefold()

    def _build_order_list_sort(
        self,
        *,
        sort_by: WorkOrderSortField,
        sort_direction: SortDirection,
    ) -> list[ColumnElement[object]]:
        is_desc = sort_direction == SortDirection.DESC

        if sort_by == WorkOrderSortField.NAME:
            product_name_sort = Product.name.desc() if is_desc else Product.name.asc()
            return [
                product_name_sort,
                WorkOrder.order_number.asc(),
                WorkOrder.id.desc(),
            ]

        if sort_by == WorkOrderSortField.COMPLETED:
            completed_at_sort = (
                WorkOrder.completed_at.desc()
                if is_desc
                else WorkOrder.completed_at.asc()
            )
            return [
                WorkOrder.completed_at.is_(None).asc(),
                completed_at_sort,
                WorkOrder.created_at.desc(),
                WorkOrder.id.desc(),
            ]

        created_at_sort = (
            WorkOrder.created_at.desc() if is_desc else WorkOrder.created_at.asc()
        )
        return [created_at_sort, WorkOrder.id.desc()]

    def get_order(self, order_id: int) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        product = self._get_product_or_404(order.product_id)
        return self._serialize_order(order, product)

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
            total_spent_minutes=payload.total_spent_minutes,
            created_at=timestamp,
            updated_at=timestamp,
        )
        order.assignments = self._build_assignments(payload.assignments)

        self.session.add(order)
        self.session.commit()
        self.session.refresh(order)
        return self.get_order(order.id)

    def update_order_assignments(
        self,
        order_id: int,
        payload: WorkOrderUpdateAssignments,
    ) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        product = self._get_product_or_404(order.product_id)
        self._validate_leather_type_is_active(
            payload.leather_type_id,
            current_leather_type_id=order.leather_type_id,
        )
        self._validate_assignments(product.id, payload.assignments)

        order.leather_type_id = payload.leather_type_id
        order.quantity = payload.quantity
        order.total_spent_minutes = payload.total_spent_minutes
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
        order.completed_at = now if payload.is_completed else None
        order.updated_at = now

        self.session.commit()
        self.session.refresh(order)
        return self.get_order(order.id)

    def _get_order_or_404(self, order_id: int) -> WorkOrder:
        stmt: Select[tuple[WorkOrder]] = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.assignments).selectinload(
                    WorkOrderAssignment.operation
                ),
                selectinload(WorkOrder.assignments).selectinload(
                    WorkOrderAssignment.worker_user
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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Leather type not found.",
            )

        if not leather_type.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only active leather types can be selected.",
            )

    def _validate_order_number(self, order_number: str) -> None:
        stmt = select(WorkOrder.id).where(WorkOrder.order_number == order_number)
        existing_order_id = self.session.execute(stmt).scalar_one_or_none()
        if existing_order_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Product has no operations.",
            )

        leaf_operation_ids = self._collect_leaf_operation_ids(operations)
        assigned_operation_ids = [assignment.operation_id for assignment in assignments]

        if len(set(assigned_operation_ids)) != len(assigned_operation_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Operations must be assigned only once per order.",
            )

        if set(assigned_operation_ids) != leaf_operation_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Assignments must cover every leaf operation of the product.",
            )

        worker_ids = {assignment.worker_user_id for assignment in assignments}
        workers = self.session.scalars(
            select(User).where(User.id.in_(worker_ids))
        ).all()
        workers_by_id = {worker.id: worker for worker in workers}

        for assignment in assignments:
            worker = workers_by_id.get(assignment.worker_user_id)
            if worker is None or worker.deleted_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Assigned worker not found.",
                )
            if not worker.is_active or "worker" not in worker.roles:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        incoming_operation_ids = {
            assignment.operation_id for assignment in assignments
        }

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

            existing_assignment.worker_user_id = incoming_assignment.worker_user_id

    def _serialize_order(self, order: WorkOrder, product: Product) -> WorkOrderDetail:
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
            total_spent_minutes=order.total_spent_minutes,
            created_at=order.created_at,
            updated_at=order.updated_at,
            completed_at=order.completed_at,
            assignments=[
                WorkOrderAssignmentRead(
                    id=assignment.id,
                    operation_id=assignment.operation_id,
                    operation_name=assignment.operation.name,
                    worker_user_id=assignment.worker_user_id,
                    worker_user_name=assignment.worker_user.name,
                )
                for assignment in order.assignments
            ],
        )

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)

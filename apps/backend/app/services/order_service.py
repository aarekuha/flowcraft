from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.operation import Operation
from app.models.product import Product
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderAssignment
from app.schemas.order import (
    WorkOrderAssignmentCreate,
    WorkOrderAssignmentRead,
    WorkOrderCreate,
    WorkOrderDetail,
    WorkOrderListItem,
    WorkOrderUpdateAssignments,
)


class OrderService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_orders(self) -> list[WorkOrderListItem]:
        assignments_count = (
            select(
                WorkOrderAssignment.work_order_id,
                func.count(WorkOrderAssignment.id).label("assignments_count"),
            )
            .group_by(WorkOrderAssignment.work_order_id)
            .subquery()
        )

        stmt = (
            select(
                WorkOrder.id,
                WorkOrder.order_number,
                WorkOrder.product_id,
                Product.name.label("product_name"),
                Product.version.label("product_version"),
                WorkOrder.quantity,
                WorkOrder.total_spent_minutes,
                WorkOrder.created_at,
                WorkOrder.updated_at,
                func.coalesce(assignments_count.c.assignments_count, 0).label(
                    "assignments_count"
                ),
            )
            .join(Product, Product.id == WorkOrder.product_id)
            .outerjoin(assignments_count, assignments_count.c.work_order_id == WorkOrder.id)
            .order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())
        )

        rows = self.session.execute(stmt).all()
        return [
            WorkOrderListItem(
                id=row.id,
                order_number=row.order_number,
                product_id=row.product_id,
                product_name=row.product_name,
                product_version=row.product_version,
                quantity=row.quantity,
                total_spent_minutes=row.total_spent_minutes,
                assignments_count=row.assignments_count,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    def get_order(self, order_id: int) -> WorkOrderDetail:
        order = self._get_order_or_404(order_id)
        product = self._get_product_or_404(order.product_id)
        return self._serialize_order(order, product)

    def create_order(self, payload: WorkOrderCreate) -> WorkOrderDetail:
        self._validate_order_number(payload.order_number)
        product = self._get_product_or_404(payload.product_id)
        self._validate_product_is_active(product)
        self._validate_assignments(product.id, payload.assignments)

        timestamp = self._now_ts()
        order = WorkOrder(
            order_number=payload.order_number,
            product_id=product.id,
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
        self._validate_assignments(product.id, payload.assignments)

        order.total_spent_minutes = payload.total_spent_minutes
        order.updated_at = self._now_ts()
        self._sync_assignments(order, payload.assignments)

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
        workers = self.session.scalars(select(User).where(User.id.in_(worker_ids))).all()
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
            operation.parent_id for operation in operations if operation.parent_id is not None
        }
        return {operation.id for operation in operations if operation.id not in parent_ids}

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
            quantity=order.quantity,
            total_spent_minutes=order.total_spent_minutes,
            created_at=order.created_at,
            updated_at=order.updated_at,
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

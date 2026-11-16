# ruff: noqa: I001
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.planning import PlanningOperationResult
from app.models.product import Product
from app.models.work_order import WorkOrder
from app.schemas.planning_timeline import PlanningTimelineItem, PlanningTimelineRead
from app.services.planning_results_service import PlanningResultsService


from datetime import date
from app.models.leather_type import LeatherType
from app.models.user import User
from app.models.work_order import WorkOrderAssignment
from app.models.planning import PlanningWorkerDayAllocation
from app.schemas.planning_timeline import PlanningDayItem, PlanningDayRead


class PlanningTimelineService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_timeline(self) -> PlanningTimelineRead:
        calculation = PlanningResultsService(self.session).get_status()
        if calculation.active_run_id is None:
            return PlanningTimelineRead(calculation=calculation, items=[])
        rows = self.session.execute(
            select(
                PlanningOperationResult,
                WorkOrder.order_number,
                Product.name,
                Product.version,
                Operation.operation_catalog_entry_id,
                func.coalesce(OperationCatalogEntry.name, Operation.name),
            )
            .join(WorkOrder, WorkOrder.id == PlanningOperationResult.order_id)
            .join(Product, Product.id == WorkOrder.product_id)
            .join(Operation, Operation.id == PlanningOperationResult.operation_id)
            .outerjoin(
                OperationCatalogEntry,
                OperationCatalogEntry.id == Operation.operation_catalog_entry_id,
            )
            .where(
                PlanningOperationResult.run_id == calculation.active_run_id,
                WorkOrder.deleted_at.is_(None),
                WorkOrder.completed_at.is_(None),
            )
            .order_by(
                WorkOrder.planning_priority_rank,
                WorkOrder.id,
                PlanningOperationResult.stage_start,
                Operation.sort_order,
                Operation.id,
            )
        ).all()
        return PlanningTimelineRead(
            calculation=calculation,
            items=[
                PlanningTimelineItem(
                    order_id=result.order_id,
                    order_number=number,
                    product_name=product,
                    product_version=version,
                    operation_id=result.operation_id,
                    operation_catalog_entry_id=catalog_id,
                    operation_name=name,
                    first_planned_date=result.first_planned_date,
                    last_planned_date=result.last_planned_date,
                    status=result.status,
                    issue_codes=list(result.issue_codes),
                )
                for result, number, product, version, catalog_id, name in rows
            ],
        )

    def get_day(self, work_date: date) -> PlanningDayRead:
        calculation = PlanningResultsService(self.session).get_status()
        if calculation.active_run_id is None:
            return PlanningDayRead(
                work_date=work_date, calculation=calculation, items=[]
            )
        tasks = (
            select(
                PlanningWorkerDayAllocation.order_id,
                PlanningWorkerDayAllocation.operation_id,
            )
            .where(
                PlanningWorkerDayAllocation.run_id == calculation.active_run_id,
                PlanningWorkerDayAllocation.work_date == work_date,
                PlanningWorkerDayAllocation.work_seconds
                + PlanningWorkerDayAllocation.preparation_seconds > 0,
            )
            .distinct()
            .subquery()
        )
        rows = self.session.execute(
            select(
                WorkOrder.id,
                WorkOrder.order_number,
                Product.name,
                Product.version,
                LeatherType.name,
                WorkOrder.quantity,
                Operation.id,
                func.coalesce(OperationCatalogEntry.name, Operation.name),
            )
            .select_from(tasks)
            .join(WorkOrder, WorkOrder.id == tasks.c.order_id)
            .join(Product, Product.id == WorkOrder.product_id)
            .join(Operation, Operation.id == tasks.c.operation_id)
            .outerjoin(LeatherType, LeatherType.id == WorkOrder.leather_type_id)
            .outerjoin(
                OperationCatalogEntry,
                OperationCatalogEntry.id == Operation.operation_catalog_entry_id,
            )
            .where(
                WorkOrder.deleted_at.is_(None),
                WorkOrder.completed_at.is_(None),
            )
            .order_by(
                WorkOrder.planning_priority_rank,
                WorkOrder.id,
                Operation.sort_order,
                Operation.id,
            )
        ).all()
        assignments = self.session.execute(
            select(
                WorkOrderAssignment.work_order_id,
                WorkOrderAssignment.operation_id,
                User.id,
                User.name,
            )
            .join(User, User.id == WorkOrderAssignment.worker_user_id)
            .join(
                tasks,
                (tasks.c.order_id == WorkOrderAssignment.work_order_id)
                & (tasks.c.operation_id == WorkOrderAssignment.operation_id),
            )
            .order_by(User.name, User.id)
        ).all()
        workers: dict[tuple[int, int], dict[int, str]] = {}
        for order_id, operation_id, user_id, name in assignments:
            workers.setdefault((order_id, operation_id), {})[user_id] = name
        return PlanningDayRead(
            work_date=work_date,
            calculation=calculation,
            items=[
                PlanningDayItem(
                    order_id=order_id,
                    order_number=number,
                    product_name=product,
                    product_version=version,
                    leather_type_name=leather,
                    quantity=quantity,
                    operation_id=operation_id,
                    operation_name=operation,
                    worker_names=list(
                        workers.get((order_id, operation_id), {}).values()
                    ),
                )
                for (
                    order_id, number, product, version, leather, quantity,
                    operation_id, operation,
                ) in rows
            ],
        )

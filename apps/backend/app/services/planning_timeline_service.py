from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.planning import PlanningOperationResult
from app.models.product import Product
from app.models.work_order import WorkOrder
from app.schemas.planning_timeline import PlanningTimelineItem, PlanningTimelineRead
from app.services.planning_results_service import PlanningResultsService


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

from datetime import date

from pydantic import BaseModel

from app.schemas.planning import ProductionPlanningStatusRead


class PlanningTimelineItem(BaseModel):
    order_id: int
    order_number: str
    product_name: str
    product_version: str
    operation_id: int
    operation_catalog_entry_id: int | None
    operation_name: str
    first_planned_date: date | None
    last_planned_date: date | None
    status: str
    issue_codes: list[str]


class PlanningTimelineRead(BaseModel):
    calculation: ProductionPlanningStatusRead
    items: list[PlanningTimelineItem]

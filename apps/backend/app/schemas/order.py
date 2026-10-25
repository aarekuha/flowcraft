from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class WorkOrderSortField(StrEnum):
    CUTTING_STARTED = "cutting_started"
    CREATED = "created"
    COMPLETED = "completed"
    DEFECT = "defect"
    NAME = "name"
    ORDER_NUMBER = "order_number"
    PLANNED_COMPLETION = "planned_completion"
    QUALITY_CONTROL = "quality_control"
    TAKEN = "taken"


class WorkOrderStatusFilter(StrEnum):
    ALL = "all"
    CREATED = "created"
    CUTTING = "cutting"
    IN_WORK = "in_work"
    QUALITY_CONTROL = "quality_control"
    COMPLETED = "completed"
    DELETED = "deleted"


class WorkerAssignmentStatusFilter(StrEnum):
    IN_WORK = "in_work"
    HIDDEN = "hidden"
    COMPLETED = "completed"


class WorkOrderProductionStage(StrEnum):
    CREATED = "created"
    CUTTING = "cutting"
    IN_WORK = "in_work"


class WorkOrderAssignmentCreate(BaseModel):
    operation_id: int
    worker_user_id: int | None = None


class WorkOrderAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operation_id: int
    operation_name: str
    worker_user_id: int | None
    worker_user_name: str | None
    worker_status: WorkerAssignmentStatusFilter = WorkerAssignmentStatusFilter.IN_WORK
    worker_hidden_at: int | None = None
    worker_completed_at: int | None = None


class WorkOrderAssignmentWorkerStatusUpdate(BaseModel):
    status: WorkerAssignmentStatusFilter


class WorkOrderCreate(BaseModel):
    order_number: str | None = Field(default=None, min_length=1, max_length=64)
    planned_completion_date: date | None = None
    product_id: int
    leather_type_id: int | None = None
    quantity: int = Field(gt=0)
    estimated_minutes: int = Field(default=0, ge=0)
    assignments: list[WorkOrderAssignmentCreate] = Field(min_length=1)

    @field_validator("order_number")
    @classmethod
    def validate_order_number(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("Order number must not be empty.")
        return normalized


class WorkOrderUpdateAssignments(BaseModel):
    leather_type_id: int | None = None
    quantity: int = Field(gt=0)
    estimated_minutes: int = Field(default=0, ge=0)
    assignments: list[WorkOrderAssignmentCreate] = Field(min_length=1)


class WorkOrderStatusUpdate(BaseModel):
    is_completed: bool


class WorkOrderPlannedCompletionDateUpdate(BaseModel):
    planned_completion_date: date


class WorkOrderQualityControlStatusUpdate(BaseModel):
    is_in_quality_control: bool


class WorkOrderQualityControlAccept(BaseModel):
    defect_quantity: int = Field(default=0, ge=0)


class WorkOrderProductionStageUpdate(BaseModel):
    production_stage: WorkOrderProductionStage


class WorkOrderDeletedStatusUpdate(BaseModel):
    is_deleted: bool


class WorkOrderSplitRequest(BaseModel):
    source_quantity: int = Field(gt=0)


class WorkOrderMergeRequest(BaseModel):
    included_order_ids: list[int] = Field(min_length=1)


class WorkOrderMergeCandidate(BaseModel):
    id: int
    order_number: str
    quantity: int


class WorkOrderNumberSearchItem(BaseModel):
    id: int
    order_number: str
    stage: WorkOrderStatusFilter


class WorkOrderListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    family_id: int | None
    part_number: int | None
    family_base_order_number: str | None
    product_id: int
    product_name: str
    product_version: str
    leather_type_id: int | None
    leather_type_name: str | None
    quantity: int
    planned_completion_date: date | None
    estimated_minutes: int
    total_spent_seconds: int
    cutting_spent_seconds: int
    has_spent_time: bool
    can_split: bool
    split_block_reason: str | None
    can_merge: bool
    assignments_count: int
    created_at: int
    updated_at: int
    production_stage: WorkOrderProductionStage
    cutting_started_at: int | None
    taken_at: int | None
    quality_control_at: int | None
    defect_quantity: int
    completed_at: int | None
    deleted_at: int | None


class WorkOrderPage(BaseModel):
    items: list[WorkOrderListItem]
    total: int
    page: int
    page_size: int
    pages: int


class WorkOrderDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    family_id: int | None
    part_number: int | None
    family_base_order_number: str | None
    product_id: int
    product_name: str
    product_version: str
    product_comment: str | None
    leather_type_id: int | None
    leather_type_name: str | None
    quantity: int
    planned_completion_date: date | None
    estimated_minutes: int
    total_spent_seconds: int
    cutting_spent_seconds: int
    has_spent_time: bool
    created_at: int
    updated_at: int
    production_stage: WorkOrderProductionStage
    cutting_started_at: int | None
    taken_at: int | None
    quality_control_at: int | None
    defect_quantity: int
    completed_at: int | None
    deleted_at: int | None
    assignments: list[WorkOrderAssignmentRead] = Field(default_factory=list)


class WorkOrderSplitResult(BaseModel):
    source: WorkOrderDetail
    created: WorkOrderDetail


class WorkOrderQrTarget(BaseModel):
    order_reference: str
    orders: list[WorkOrderDetail] = Field(default_factory=list)


class WorkOrderTimeBreakdownItem(BaseModel):
    operation_id: int | None
    operation_name: str
    worker_user_id: int
    worker_user_name: str
    elapsed_ms: int
    standard_time_seconds: int | None
    average_elapsed_ms: int


class WorkOrderTimeBreakdown(BaseModel):
    order_id: int
    items: list[WorkOrderTimeBreakdownItem] = Field(default_factory=list)
    total_standard_time_seconds: int
    total_elapsed_ms: int

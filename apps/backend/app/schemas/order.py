from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class WorkOrderSortField(StrEnum):
    CREATED = "created"
    COMPLETED = "completed"
    NAME = "name"


class WorkOrderAssignmentCreate(BaseModel):
    operation_id: int
    worker_user_id: int


class WorkOrderAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operation_id: int
    operation_name: str
    worker_user_id: int
    worker_user_name: str


class WorkOrderCreate(BaseModel):
    order_number: str = Field(min_length=1, max_length=64)
    product_id: int
    leather_type_id: int | None = None
    quantity: int = Field(gt=0)
    total_spent_minutes: int = Field(default=0, ge=0)
    assignments: list[WorkOrderAssignmentCreate] = Field(min_length=1)

    @field_validator("order_number")
    @classmethod
    def validate_order_number(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Order number must not be empty.")
        return normalized


class WorkOrderUpdateAssignments(BaseModel):
    leather_type_id: int | None = None
    quantity: int = Field(gt=0)
    total_spent_minutes: int = Field(default=0, ge=0)
    assignments: list[WorkOrderAssignmentCreate] = Field(min_length=1)


class WorkOrderStatusUpdate(BaseModel):
    is_completed: bool


class WorkOrderListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    product_id: int
    product_name: str
    product_version: str
    leather_type_id: int | None
    leather_type_name: str | None
    quantity: int
    total_spent_minutes: int
    assignments_count: int
    created_at: int
    updated_at: int
    completed_at: int | None


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
    product_id: int
    product_name: str
    product_version: str
    leather_type_id: int | None
    leather_type_name: str | None
    quantity: int
    total_spent_minutes: int
    created_at: int
    updated_at: int
    completed_at: int | None
    assignments: list[WorkOrderAssignmentRead] = Field(default_factory=list)

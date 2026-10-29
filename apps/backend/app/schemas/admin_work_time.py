from pydantic import BaseModel, Field

from app.schemas.timer import TimerType


class AdminWorkTimeWorkerRead(BaseModel):
    id: int
    name: str
    is_active: bool
    is_deleted: bool
    can_add_time: bool


class AdminWorkTimeAllocationRead(BaseModel):
    order_id: int
    order_number: str
    allocated_seconds: int


class AdminWorkTimeSessionRead(BaseModel):
    id: int
    shift_id: int
    worker_user_id: int
    timer_type: TimerType
    label: str
    order_id: int | None
    order_number: str | None
    operation_id: int | None
    operation_name: str | None
    started_at: int
    ended_at: int | None
    is_active: bool
    has_allocations: bool
    allocated_order_numbers: list[str] = Field(default_factory=list)
    allocations: list[AdminWorkTimeAllocationRead] = Field(default_factory=list)
    editable: bool
    blocked_reason: str | None
    updated_at: int


class AdminWorkTimeOrderRead(BaseModel):
    id: int
    order_number: str
    product_name: str
    product_version: str
    is_deleted: bool


class AdminWorkTimeOperationRead(BaseModel):
    id: int
    name: str


class AdminWorkTimeOverlapRead(BaseModel):
    order_id: int
    order_number: str


class AdminWorkTimeSessionCreate(BaseModel):
    worker_user_id: int
    order_id: int
    operation_id: int
    started_at: int
    ended_at: int


class AdminWorkTimeSessionUpdate(BaseModel):
    order_id: int | None = None
    operation_id: int | None = None
    started_at: int
    ended_at: int
    expected_updated_at: int

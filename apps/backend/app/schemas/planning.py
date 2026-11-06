from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_HORIZON_MONTHS = {1, 3, 6, 12}


class PlanningSettingsUpdate(BaseModel):
    display_offset_days: int = Field(ge=0)
    preparation_seconds: int = Field(ge=0)
    horizon_months: int

    @field_validator("horizon_months")
    @classmethod
    def validate_horizon_months(cls, value: int) -> int:
        if value not in ALLOWED_HORIZON_MONTHS:
            raise ValueError("Planning horizon must be 1, 3, 6, or 12 months.")
        return value


class PlanningSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    display_offset_days: int
    preparation_seconds: int
    horizon_months: int
    updated_at: int
    updated_by_user_id: int | None


class WorkScheduleBatchUpdate(BaseModel):
    user_id: int = Field(ge=1)
    work_dates: list[date] = Field(min_length=1, max_length=366)
    available_seconds: int = Field(ge=3600, le=57_600)

    @field_validator("work_dates")
    @classmethod
    def validate_work_dates(cls, values: list[date]) -> list[date]:
        if len(values) != len(set(values)):
            raise ValueError("Work dates must be unique.")
        return values

class WorkScheduleBatchDelete(BaseModel):
    user_id: int = Field(ge=1)
    work_dates: list[date] = Field(min_length=1, max_length=366)

    @field_validator("work_dates")
    @classmethod
    def validate_work_dates(cls, values: list[date]) -> list[date]:
        if len(values) != len(set(values)):
            raise ValueError("Work dates must be unique.")
        return values


class WorkScheduleDayRead(BaseModel):
    work_date: date
    available_seconds: int


class WorkScheduleWorkerRead(BaseModel):
    user_id: int
    user_name: str
    days: list[WorkScheduleDayRead]


class WorkScheduleMonthRead(BaseModel):
    month: str
    days_in_month: int
    workers: list[WorkScheduleWorkerRead]


class PlanningQueueItemRead(BaseModel):
    order_id: int
    position: int
    order_number: str
    product_name: str
    leather_type_name: str | None
    quantity: int
    stage: str


class PlanningQueueRead(BaseModel):
    revision: int
    items: list[PlanningQueueItemRead]


class PlanningQueueReorder(BaseModel):
    order_id: int = Field(ge=1)
    expected_revision: int = Field(ge=0)
    before_order_id: int | None = Field(default=None, ge=1)
    after_order_id: int | None = Field(default=None, ge=1)
    position: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_target(self) -> "PlanningQueueReorder":
        has_neighbors = (
            self.before_order_id is not None or self.after_order_id is not None
        )
        if self.position is None and not has_neighbors:
            raise ValueError("Specify a position or neighboring orders.")
        if self.position is not None and has_neighbors:
            raise ValueError("Position cannot be combined with neighboring orders.")
        if self.before_order_id == self.order_id:
            raise ValueError("Order cannot be its own previous neighbor.")
        if self.after_order_id == self.order_id:
            raise ValueError("Order cannot be its own next neighbor.")
        if (
            self.before_order_id is not None
            and self.before_order_id == self.after_order_id
        ):
            raise ValueError("Previous and next neighboring orders must differ.")
        return self


class ProductionPlanningStatusRead(BaseModel):
    calculation_status: str
    input_revision: int
    requested_revision: int
    running_revision: int | None
    active_run_id: int | None
    active_revision: int | None
    active_completed_at: int | None
    is_stale: bool


class PlanningOrderForecastRead(BaseModel):
    order_id: int
    order_number: str
    product_name: str
    manual_completion_date: date | None
    resource_finish_date: date | None
    calculated_finish_date: date | None
    status: str
    issue_codes: list[str]


class PlanningOperationForecastRead(BaseModel):
    operation_id: int
    operation_name: str
    stage_start: int
    stage_end: int
    standard_time_seconds: int | None
    standard_time_source: str
    workload_seconds: int
    actual_seconds: int
    remaining_seconds: int
    preparation_seconds: int
    first_planned_date: date | None
    last_planned_date: date | None
    status: str
    issue_codes: list[str]


class PlanningAllocationRead(BaseModel):
    user_id: int
    user_name: str
    work_date: date
    operation_id: int
    work_seconds: int
    preparation_seconds: int


class PlanningOrderForecastDetailRead(PlanningOrderForecastRead):
    operations: list[PlanningOperationForecastRead]
    allocations: list[PlanningAllocationRead]


class PlanningWorkloadItemRead(BaseModel):
    operation_catalog_entry_id: int | None
    operation_name: str
    planned_seconds: int
    remaining_seconds: int
    orders_count: int
    deficit_seconds: int


class PlanningWorkloadRead(BaseModel):
    month: str
    active_run_id: int | None
    items: list[PlanningWorkloadItemRead]

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TimerType(StrEnum):
    PREPARATION = "preparation"
    OPERATION = "operation"
    BREAK = "break"
    IDLE = "idle"


class WorkShiftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: int
    business_date: str


class TimerSessionAggregateRead(BaseModel):
    timer_type: TimerType
    order_id: int | None = None
    operation_id: int | None = None
    elapsed_ms: int


class ActiveTimerRead(BaseModel):
    timer_type: TimerType
    order_id: int | None = None
    operation_id: int | None = None
    started_at: int


class WorkerTimerStateRead(BaseModel):
    shift: WorkShiftRead | None = None
    active_timer: ActiveTimerRead | None = None
    timer_totals: list[TimerSessionAggregateRead]


class TimerSwitchPayload(BaseModel):
    timer_type: TimerType
    order_id: int | None = None
    operation_id: int | None = None

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DiagnosticEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at: int = Field(ge=0)
    kind: Literal[
        "request",
        "timer_click",
        "timer_state",
        "js_error",
        "unhandled_rejection",
        "console_error",
        "online",
        "offline",
        "page_open",
    ]
    path: str | None = Field(
        default=None, max_length=200, pattern=r"^/api/[a-zA-Z0-9/_-]+$"
    )
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] | None = None
    status: int | None = Field(default=None, ge=0, le=599)
    duration_ms: int | None = Field(default=None, ge=0)
    request_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    order_id: int | None = Field(default=None, ge=1)
    operation_id: int | None = Field(default=None, ge=1)
    timer_type: Literal["preparation", "operation", "break", "idle"] | None = None
    timer_started_at: int | None = Field(default=None, ge=0)
    blocked: bool | None = None
    line: int | None = Field(default=None, ge=0)
    column: int | None = Field(default=None, ge=0)


class DiagnosticUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_user_id: int = Field(ge=1)
    report_key: UUID
    captured_at: int = Field(ge=0)
    window_start: int = Field(ge=0)
    build: str = Field(max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    viewport_width: int = Field(ge=0, le=100000)
    viewport_height: int = Field(ge=0, le=100000)
    events: list[DiagnosticEvent] = Field(max_length=100000)

    @model_validator(mode="after")
    def validate_window(self) -> "DiagnosticUpload":
        if self.captured_at - self.window_start != 86400000:
            raise ValueError("Diagnostic window must be 24 hours")
        if any(
            not self.window_start <= event.at <= self.captured_at
            for event in self.events
        ):
            raise ValueError("Event is outside the report window")
        return self

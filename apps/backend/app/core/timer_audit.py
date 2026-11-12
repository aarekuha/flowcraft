import json
import logging
from dataclasses import dataclass, field
from time import perf_counter, time
from uuid import uuid4

from app.models.timer_session import TimerSession

logger = logging.getLogger("uvicorn.error.timer_audit")
logger.setLevel(logging.INFO)


def timer_snapshot(timer: TimerSession | None) -> dict[str, int | None] | None:
    if timer is None:
        return None
    return {
        "timer_session_id": timer.id,
        "shift_id": timer.shift_id,
        "timer_type_code": timer.timer_type_code,
        "order_id": timer.order_id,
        "operation_id": timer.operation_id,
        "started_at": timer.started_at,
    }


@dataclass
class TimerAudit:
    action: str
    request_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: int = field(default_factory=lambda: int(time() * 1000))
    started_clock: float = field(default_factory=perf_counter)
    user_id: int | None = None
    auth_session_id: int | None = None
    requested: dict[str, str | int | None] | None = None
    previous_timer: dict[str, int | None] | None = None
    previous_observed: bool = False
    committed_timer: dict[str, int | None] | None = None
    committed: bool = False
    unchanged: bool = False

    def emit(self, event: str, **details: object) -> None:
        logger.info(
            json.dumps(
                {
                    "event": event,
                    "request_id": self.request_id,
                    "action": self.action,
                    "user_id": self.user_id,
                    "auth_session_id": self.auth_session_id,
                    "requested": self.requested,
                    "previous_timer": self.previous_timer,
                    "previous_observed": self.previous_observed,
                    "committed_timer": self.committed_timer,
                    "committed": self.committed,
                    "unchanged": self.unchanged,
                    "started_at": self.started_at,
                    "recorded_at": int(time() * 1000),
                    "duration_ms": round(
                        (perf_counter() - self.started_clock) * 1000, 3
                    ),
                    **details,
                },
                ensure_ascii=False,
            )
        )

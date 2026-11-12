from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.timer_audit import TimerAudit

ACTIONS = {
    "/api/timers/switch": "switch",
    "/api/timers/start-day": "start_day",
    "/api/timers/end-day": "end_day",
}


class TimerAuditMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        action = ACTIONS.get(scope.get("path", ""))
        if scope["type"] != "http" or scope["method"] != "POST" or action is None:
            await self.app(scope, receive, send)
            return
        audit = TimerAudit(action=action)
        state = scope.setdefault("state", {})
        state["timer_audit"] = audit
        audit.emit("timer_request_started")
        status_code = 500
        exception_type = None

        async def audited_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message = {
                    **message,
                    "headers": [
                        *message.get("headers", []),
                        (b"x-timer-request-id", audit.request_id.encode("ascii")),
                    ],
                }
            await send(message)

        try:
            await self.app(scope, receive, audited_send)
        except BaseException as error:
            exception_type = type(error).__name__
            raise
        finally:
            auth = state.get("auth_session")
            if auth is not None:
                audit.user_id = auth.user_id
                audit.auth_session_id = auth.session_id
            outcome = (
                "error"
                if exception_type is not None or status_code >= 500
                else "rejected"
                if status_code >= 400
                else "unchanged"
                if audit.unchanged
                else "success"
            )
            audit.emit(
                "timer_request_finished",
                outcome=outcome,
                status_code=status_code,
                exception_type=exception_type,
            )

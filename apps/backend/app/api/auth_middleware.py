from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.services.auth_service import SESSION_COOKIE_NAME, AuthService

PUBLIC_PATH_PREFIXES = (
    "/api/health",
    "/api/auth/login",
    "/api/auth/setup-password",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class AuthSessionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        if request.method == "OPTIONS" or request.url.path.startswith(
            PUBLIC_PATH_PREFIXES,
        ):
            await self.app(scope, receive, send)
            return

        session_factory = request.app.state.session_factory
        token = request.cookies.get(SESSION_COOKIE_NAME)

        with session_factory() as session:
            auth_service = AuthService(session)
            try:
                auth_session = auth_service.get_session(token)
                auth_service.touch_session(auth_session.session_id)
            except HTTPException:
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "Требуется аутентификация."},
                )
                response.delete_cookie(
                    key=SESSION_COOKIE_NAME,
                    httponly=True,
                    samesite="lax",
                    secure=False,
                    path="/",
                )
                await response(scope, receive, send)
                return

        scope.setdefault("state", {})["auth_session"] = auth_session
        await self.app(scope, receive, send)

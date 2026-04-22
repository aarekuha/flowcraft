from __future__ import annotations

from fastapi import Request
from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.services.auth_service import AuthService, SESSION_COOKIE_NAME


PUBLIC_PATH_PREFIXES = (
    "/api/health",
    "/api/auth/login",
    "/api/auth/setup-password",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class AuthSessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method == "OPTIONS" or request.url.path.startswith(PUBLIC_PATH_PREFIXES):
            return await call_next(request)

        session_factory = request.app.state.session_factory
        token = request.cookies.get(SESSION_COOKIE_NAME)

        with session_factory() as session:
            auth_service = AuthService(session)
            try:
                auth_session = auth_service.get_session(token)
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
                return response

        request.state.auth_session = auth_session
        response = await call_next(request)

        if response.status_code < 400:
            with session_factory() as session:
                AuthService(session).touch_session(auth_session.session_id)

        return response

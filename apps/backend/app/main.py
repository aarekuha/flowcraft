# ruff: noqa: I001
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth_middleware import AuthSessionMiddleware
from app.api.router import api_router
from app.api.timer_audit_middleware import TimerAuditMiddleware
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.bitrix_service import recover_interrupted_sync


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    recover_interrupted_sync(app.state.session_factory)
    yield


def create_application() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan,
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.session_factory = SessionLocal
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuthSessionMiddleware)
    app.add_middleware(TimerAuditMiddleware)
    app.include_router(api_router, prefix="/api")
    return app


app = create_application()

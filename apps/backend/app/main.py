from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth_middleware import AuthSessionMiddleware
from app.api.router import api_router
from app.core.config import settings
from app.core.database import SessionLocal


def create_application() -> FastAPI:
    app = FastAPI(
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
    app.include_router(api_router, prefix="/api")
    return app


app = create_application()

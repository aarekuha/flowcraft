from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.leather_types import router as leather_types_router
from app.api.routes.orders import router as orders_router
from app.api.routes.products import router as products_router
from app.api.routes.statistics import router as statistics_router
from app.api.routes.timers import router as timers_router
from app.api.routes.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(
    leather_types_router,
    prefix="/leather-types",
    tags=["leather-types"],
)
api_router.include_router(orders_router, prefix="/orders", tags=["orders"])
api_router.include_router(products_router, prefix="/products", tags=["products"])
api_router.include_router(statistics_router, prefix="/statistics", tags=["statistics"])
api_router.include_router(timers_router, prefix="/timers", tags=["timers"])
api_router.include_router(users_router, prefix="/users", tags=["users"])

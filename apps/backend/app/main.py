"""FastAPI application entry point."""

from fastapi import FastAPI

from app.core.config import get_settings
from app.observability import request_observability_middleware
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.routers.recommendations import router as recommendations_router
from app.routers.wardrobe import router as wardrobe_router


settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.middleware("http")(request_observability_middleware)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(health_router)
app.include_router(recommendations_router)
app.include_router(wardrobe_router)

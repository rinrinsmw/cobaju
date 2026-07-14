"""FastAPI application entry point."""

from fastapi import FastAPI

from app.core.config import get_settings
from app.routers.health import router as health_router


settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.include_router(health_router)

"""Celery application configured with the shared Redis broker setting."""

from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "cobaju",
    broker=settings.redis_url,
    include=["app.tasks.clothing_processing"],
)
celery_app.conf.update(
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    enable_utc=True,
    task_serializer="json",
    task_track_started=True,
)

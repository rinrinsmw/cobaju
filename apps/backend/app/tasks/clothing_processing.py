"""Celery wrapper around the synchronous Phase 5 clothing-analysis service."""

from celery import Task
from sqlmodel import Session

from app.celery_app import celery_app
from app.core.config import Settings, get_settings
from app.database import engine
from app.models.clothing_item import ClothingItem, ProcessingStatus
from app.services.clothing_analysis import (
    ClothingAnalysisError,
    ClothingVisionProvider,
    analyze_clothing_item,
)
from app.services.image_uploads import delete_stored_image
from app.services.openrouter import OpenRouterVisionProvider
from app.services.wardrobe import mark_item_failed


class ClothingTaskEnqueueError(Exception):
    """Raised when a clothing task cannot be sent to Redis."""


def enqueue_clothing_analysis(item_id: int) -> None:
    """Send only the database ID; the worker loads all trusted state itself."""

    try:
        process_clothing_item.delay(item_id)
    except Exception as error:
        raise ClothingTaskEnqueueError from error


def run_clothing_processing(
    session: Session,
    item_id: int,
    provider: ClothingVisionProvider,
    settings: Settings,
) -> str:
    """Process one claimed item and return a JSON-serializable outcome."""

    item = session.get(ClothingItem, item_id)
    if item is None:
        return "missing"

    # A redelivered task must not overwrite metadata that is already ready for
    # review. Failed items remain allowed so a user-triggered retry can reuse
    # this synchronous service after the API claims the item again.
    if item.analysis_completed:
        return "completed"
    if item.processing_status not in {
        ProcessingStatus.PROCESSING,
        ProcessingStatus.FAILED,
    }:
        return "skipped"
    if item.original_image_path is None:
        mark_item_failed(session, item)
        return "failed"

    image_path = (
        settings.resolved_upload_directory / item.original_image_path
    ).resolve()
    if (
        not image_path.is_relative_to(settings.resolved_upload_directory)
        or not image_path.is_file()
    ):
        mark_item_failed(session, item)
        return "failed"

    _, rejected_path = analyze_clothing_item(
        session,
        item,
        image_path,
        provider,
        settings,
    )
    if rejected_path is not None:
        try:
            delete_stored_image(settings.resolved_upload_directory, rejected_path)
        except OSError:
            # The database already detached the rejected content. Cleanup can
            # safely be best-effort without making the record inconsistent.
            pass
        return "rejected"
    return "completed"


@celery_app.task(bind=True, name="cobaju.process_clothing_item")
def process_clothing_item(task: Task, item_id: int) -> str:
    """Run analysis with a fresh worker session and limited retries."""

    settings = get_settings()
    provider = OpenRouterVisionProvider(settings)
    try:
        with Session(engine) as session:
            return run_clothing_processing(session, item_id, provider, settings)
    except ClothingAnalysisError as error:
        if task.request.retries >= settings.celery_task_max_retries:
            with Session(engine) as session:
                item = session.get(ClothingItem, item_id)
                if (
                    item is not None
                    and not item.analysis_completed
                    and item.processing_status == ProcessingStatus.PROCESSING
                ):
                    mark_item_failed(session, item)
            return "failed"
        raise task.retry(
            exc=error,
            countdown=settings.celery_task_retry_delay_seconds,
            max_retries=settings.celery_task_max_retries,
        )

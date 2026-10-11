from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ai_document_saas",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.document_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_always_eager=settings.celery_task_always_eager,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
)

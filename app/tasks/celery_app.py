import sys

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ai_document_saas",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.document_tasks"],
)

celery_conf = {
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "task_track_started": True,
    "task_always_eager": settings.celery_task_always_eager,
    "task_reject_on_worker_lost": True,
    "broker_connection_retry_on_startup": True,
}

# Windows does not support billiard prefork processes due to Win32 handle inheritance issues.
# Default to 'solo' pool on Windows unless overridden by CLI or settings.
if sys.platform == "win32":
    celery_conf["worker_pool"] = "solo"

celery_app.conf.update(**celery_conf)

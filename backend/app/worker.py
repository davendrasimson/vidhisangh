"""Celery application for background job processing.

Feature modules register tasks here (e.g. document OCR, AI drafting, email &
notification dispatch, digest generation, search indexing). Kept intentionally
thin — task implementations live with their owning module.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "vidhisangh",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="health.ping")
def ping() -> str:
    return "pong"

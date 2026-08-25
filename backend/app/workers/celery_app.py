from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "somalia_ai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks.notifications"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_routes={
        "app.workers.tasks.ingestion.*": {"queue": "ingestion"},
        "app.workers.tasks.ml.*": {"queue": "ml"},
        "app.workers.tasks.notifications.*": {"queue": "notifications"},
    },
    beat_schedule={
        "dispatch-due-notifications": {
            "task": "app.workers.tasks.notifications.dispatch_due_notifications",
            "schedule": 30.0,
        }
    },
)

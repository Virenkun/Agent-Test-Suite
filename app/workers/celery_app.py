from celery import Celery

from app.config import get_settings
from app.core.logging import configure_logging

configure_logging()
_settings = get_settings()

celery_app = Celery(
    "calling_test_suite",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=[
        "app.workers.tasks_calls",
        "app.workers.tasks_eval",
        "app.workers.tasks_recovery",
        "app.workers.tasks_insights",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_time_limit=900,          # 15 min hard cap per task
    task_soft_time_limit=780,
    result_expires=86400,
    beat_schedule={
        "recover-stuck-calls": {
            "task": "app.workers.tasks_recovery.recover_stuck_calls",
            "schedule": 120.0,  # every 2 minutes
        },
    },
)

from celery import Celery

from config import settings

celery = Celery(
    "axis_policy_sync",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Australia/Sydney",
    enable_utc=True,
    worker_concurrency=1,  # one job at a time per worker
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,
    task_max_retries=2,
)

# Auto-discover tasks in workers/
celery.autodiscover_tasks(["workers"])

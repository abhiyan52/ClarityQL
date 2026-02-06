"""Celery configuration for async task processing."""

import logging

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Create Celery app
celery_app = Celery(
    "clarityql",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Result backend settings
    result_backend_transport_options={
        "visibility_timeout": 3600,  # 1 hour
        "master_name": "mymaster",
    },
    result_expires=3600 * 24,  # Results expire after 24 hours
    # Task execution settings
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3000,  # 50 minutes soft limit
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Database result backend settings
    database_short_lived_sessions=True,
    database_engine_options={
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    },
)

# Task routes (optional - for task-specific queues)
celery_app.conf.task_routes = {
    "app.tasks.rag_tasks.ingest_document_task": {"queue": "rag_ingestion"},
    "app.tasks.rag_tasks.generate_embeddings_task": {"queue": "rag_embeddings"},
}


@worker_process_init.connect
def init_worker_process(**kwargs):
    """Initialize worker process."""
    logger.info("Celery worker process initialized")


# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])

logger.info("Celery app configured successfully")

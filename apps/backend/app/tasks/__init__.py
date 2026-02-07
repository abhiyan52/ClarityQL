"""Celery tasks package."""

# Import tasks so Celery can discover them
from app.tasks import nlq_tasks, rag_tasks  # noqa: F401

__all__ = ["nlq_tasks", "rag_tasks"]

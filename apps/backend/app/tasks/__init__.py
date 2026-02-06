"""Celery tasks package."""

# Import tasks so Celery can discover them
from app.tasks import rag_tasks  # noqa: F401

__all__ = ["rag_tasks"]

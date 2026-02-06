"""Task status model for tracking async operations."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SQLEnum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskStatus(str, Enum):
    """Status of an async task."""

    PENDING = "PENDING"
    STARTED = "STARTED"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    REVOKED = "REVOKED"
    RETRY = "RETRY"


class TaskType(str, Enum):
    """Type of async task."""

    DOCUMENT_INGESTION = "document_ingestion"
    EMBEDDING_GENERATION = "embedding_generation"
    DOCUMENT_DELETION = "document_deletion"


class Task(Base):
    """
    Track status of async tasks.

    Provides user-facing status updates for long-running operations.
    Complements Celery's internal result backend.
    """

    __tablename__ = "tasks"

    # ── Primary key ──────────────────────────
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # ── Task identification ──────────────────
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
        comment="Celery task ID for tracking",
    )
    task_type: Mapped[TaskType] = mapped_column(
        SQLEnum(TaskType, name="task_type", create_constraint=True),
        nullable=False,
        index=True,
    )

    # ── User & tenant context ────────────────
    tenant_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # ── Task status ──────────────────────────
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, name="task_status", create_constraint=True),
        nullable=False,
        default=TaskStatus.PENDING,
        index=True,
    )

    # ── Task metadata ────────────────────────
    task_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable task name",
    )
    task_args: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Task arguments (for debugging)",
    )

    # ── Progress tracking ────────────────────
    progress_current: Mapped[int | None] = mapped_column(
        nullable=True,
        default=0,
        comment="Current progress value",
    )
    progress_total: Mapped[int | None] = mapped_column(
        nullable=True,
        default=100,
        comment="Total progress value",
    )
    progress_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Human-readable progress message",
    )

    # ── Result ───────────────────────────────
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Task result (on success)",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error details (on failure)",
    )

    # ── Timestamps ───────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @property
    def progress_percentage(self) -> float:
        """Calculate progress as percentage."""
        if not self.progress_total or self.progress_total == 0:
            return 0.0

        return (self.progress_current or 0) / self.progress_total * 100

    @property
    def is_completed(self) -> bool:
        """Check if task has completed (success or failure)."""
        return self.status in (TaskStatus.SUCCESS, TaskStatus.FAILURE, TaskStatus.REVOKED)

    @property
    def duration_seconds(self) -> float | None:
        """Calculate task duration in seconds."""
        if not self.started_at or not self.completed_at:
            return None

        return (self.completed_at - self.started_at).total_seconds()

    def __repr__(self) -> str:
        return f"<Task {self.task_name} {self.status.value}>"

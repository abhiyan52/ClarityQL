"""Celery tasks for RAG document ingestion and processing."""

import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from celery import Task as CeleryTask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.models.task import Task, TaskStatus, TaskType
from app.schemas.rag import IngestionRequest
from app.services.rag.document_loader import DocumentLoadError
from app.services.rag.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)
settings = get_settings()

# Create sync engine for Celery tasks (workers can't use async)
sync_engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


class CallbackTask(CeleryTask):
    """Base task with database session and status tracking."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(f"Task {task_id} failed: {exc}")

        # Update task status in database
        with SessionLocal() as session:
            task = session.query(Task).filter(Task.celery_task_id == task_id).first()
            if task:
                task.status = TaskStatus.FAILURE
                task.error_message = str(exc)
                task.completed_at = datetime.utcnow()
                session.commit()

    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        logger.info(f"Task {task_id} completed successfully")

        # Update task status in database
        with SessionLocal() as session:
            task = session.query(Task).filter(Task.celery_task_id == task_id).first()
            if task:
                task.status = TaskStatus.SUCCESS
                task.result = retval
                task.completed_at = datetime.utcnow()
                session.commit()

    def update_progress(self, task_id: str, current: int, total: int, message: str):
        """Update task progress in database."""
        with SessionLocal() as session:
            task = session.query(Task).filter(Task.celery_task_id == task_id).first()
            if task:
                task.status = TaskStatus.PROGRESS
                task.progress_current = current
                task.progress_total = total
                task.progress_message = message
                session.commit()


@celery_app.task(
    bind=True,
    base=CallbackTask,
    name="app.tasks.rag_tasks.ingest_document_task",
    max_retries=3,
    default_retry_delay=60,  # Retry after 1 minute
)
def ingest_document_task(
    self,
    file_path: str,
    document_title: str | None,
    description: str | None,
    language: str | None,
    tenant_id: str,
    owner_user_id: str,
    max_chunk_tokens: int,
    chunk_overlap_tokens: int,
    task_db_id: str,
) -> dict:
    """
    Async task to ingest a document.

    Args:
        self: Celery task instance (injected).
        file_path: Path to uploaded file.
        document_title: Document title.
        description: Document description.
        language: Language override.
        tenant_id: Tenant UUID (string).
        owner_user_id: Owner user UUID (string).
        max_chunk_tokens: Max tokens per chunk.
        chunk_overlap_tokens: Overlap tokens.
        task_db_id: Task database record ID.

    Returns:
        Dict with ingestion results.

    Raises:
        Exception: If ingestion fails (will be retried).
    """
    task_id = self.request.id
    logger.info(f"Starting document ingestion task: {task_id}")

    try:
        # Update task status to STARTED
        with SessionLocal() as session:
            task = session.query(Task).filter(Task.celery_task_id == task_id).first()
            if task:
                task.status = TaskStatus.STARTED
                task.started_at = datetime.utcnow()
                task.progress_message = "Loading document..."
                session.commit()

        # Build ingestion request
        request = IngestionRequest(
            file_path=file_path,
            document_title=document_title,
            description=description,
            language=language,
            tenant_id=UUID(tenant_id),
            owner_user_id=UUID(owner_user_id),
            max_chunk_tokens=max_chunk_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens,
        )

        # Run ingestion pipeline with progress updates
        pipeline = IngestionPipeline()

        # Progress: Loading document
        self.update_progress(task_id, 10, 100, "Parsing document...")

        # Note: We need to refactor pipeline to accept sync session
        # For now, we'll use a workaround with sync session
        from sqlalchemy.orm import Session

        with SessionLocal() as db_session:
            # Refactor needed: Convert pipeline to use sync session
            # This is a placeholder - actual implementation needs async->sync conversion

            self.update_progress(task_id, 30, 100, "Extracting text...")

            # Load document
            from app.services.rag.document_loader import DoclingDocumentLoader

            loader = DoclingDocumentLoader()
            doc = loader.load(request.file_path)

            self.update_progress(task_id, 50, 100, "Chunking content...")

            # Extract elements and chunk
            elements = loader.extract_text_elements(doc)

            from app.services.rag.chunker import SemanticChunker
            from app.services.rag.language_detector import (
                detect_language_from_multiple_samples,
            )

            # Detect language
            if not request.language:
                sample_texts = [text for text, _ in elements[:5]]
                request.language = detect_language_from_multiple_samples(sample_texts)

            self.update_progress(task_id, 70, 100, "Creating chunks...")

            # Chunk
            chunker = SemanticChunker(
                max_tokens=request.max_chunk_tokens,
                overlap_tokens=request.chunk_overlap_tokens,
            )

            document_title = (
                request.document_title or loader.get_document_title(doc)
            )
            file_name = Path(request.file_path).name

            chunks = chunker.chunk_elements(
                elements=elements,
                document_title=document_title,
                file_name=file_name,
                language=request.language,
            )

            self.update_progress(task_id, 90, 100, "Saving to database...")

            # Persist to database (sync)
            import hashlib
            from app.models.document import (
                Document as DocumentModel,
                DocumentSourceType,
                DocumentVisibility,
            )
            from app.models.chunk import Chunk as ChunkModel

            # Calculate checksum
            sha256 = hashlib.sha256()
            with open(request.file_path, "rb") as f:
                for chunk_data in iter(lambda: f.read(4096), b""):
                    sha256.update(chunk_data)
            checksum = sha256.hexdigest()

            # Create document
            document = DocumentModel(
                tenant_id=request.tenant_id,
                owner_user_id=request.owner_user_id,
                title=document_title,
                description=request.description,
                source_type=DocumentSourceType.UPLOADED,
                visibility=DocumentVisibility.TENANT,
                storage_path=request.file_path,
                mime_type=None,
                checksum=checksum,
                file_size_bytes=Path(request.file_path).stat().st_size,
                version=1,
                language=request.language,
                is_active=True,
                chunk_count=len(chunks),
                extra_metadata={
                    "pages": loader.get_page_count(doc),
                    "chunking": {
                        "max_tokens": request.max_chunk_tokens,
                        "overlap_tokens": request.chunk_overlap_tokens,
                    },
                },
            )

            db_session.add(document)
            db_session.flush()

            # Create chunks
            for chunk in chunks:
                chunk_record = ChunkModel(
                    document_id=document.id,
                    tenant_id=request.tenant_id,
                    chunk_index=chunk.metadata.chunk_index,
                    page_number=chunk.metadata.page_number,
                    section=chunk.metadata.section_title,
                    language=chunk.metadata.language,
                    content=chunk.content,
                    token_count=chunk.metadata.token_count,
                    embedding=None,
                    extra_metadata=chunk.metadata.extra,
                )
                db_session.add(chunk_record)

            db_session.commit()

            # Calculate stats
            total_tokens = sum(chunk.metadata.token_count for chunk in chunks)
            avg_tokens = total_tokens / len(chunks) if chunks else 0

            result = {
                "document_id": str(document.id),
                "chunks_created": len(chunks),
                "stats": {
                    "total_chunks": len(chunks),
                    "total_tokens": total_tokens,
                    "avg_tokens_per_chunk": round(avg_tokens, 1),
                    "pages_processed": loader.get_page_count(doc),
                    "language_detected": request.language,
                },
            }

            logger.info(
                f"Document ingested successfully: {document.id} ({len(chunks)} chunks)"
            )

            return result

    except DocumentLoadError as e:
        logger.error(f"Document loading failed: {e}")
        raise self.retry(exc=e)

    except Exception as e:
        logger.error(f"Unexpected error during ingestion: {e}", exc_info=True)
        raise

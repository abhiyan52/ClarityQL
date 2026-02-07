"""Celery tasks for RAG document ingestion and processing."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from app.models.document import Document, DocumentProcessingStatus

from celery import Task as CeleryTask, group
from sqlalchemy import create_engine, select, update
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


def sanitize_text(text: str | None) -> str | None:
    """
    Remove null bytes from text to prevent PostgreSQL insertion errors.
    
    PostgreSQL text fields cannot contain NUL (0x00) bytes, which can appear
    in PDF extractions and other document sources.
    """
    if text is None:
        return None
    return text.replace('\x00', '')


class CallbackTask(CeleryTask):
    """Base task with database session and status tracking."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(f"Celery task {task_id} failed: {exc}")

        # Extract our Task model ID from kwargs
        our_task_id = kwargs.get("task_id")
        if not our_task_id and self.name == "app.tasks.rag_tasks.ingest_document_task":
            our_task_id = task_id
        
        # Only try to update Task record if we have a task_id
        # Some tasks (like generate_embeddings_task) don't use Task records
        if not our_task_id:
            logger.debug(f"No task_id in kwargs for Celery task {task_id} - skipping Task record update")
            return

        # Update task status in database using our Task model ID
        with SessionLocal() as session:
            task = session.query(Task).filter(Task.id == UUID(our_task_id)).first()
            if task:
                task.status = TaskStatus.FAILURE
                task.error_message = str(exc)
                task.completed_at = datetime.now(timezone.utc)
                session.commit()
            else:
                logger.error(f"Task {our_task_id} not found in database (on_failure)")

    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        logger.info(f"Celery task {task_id} completed successfully")

        # Extract our Task model ID from kwargs
        our_task_id = kwargs.get("task_id")
        if not our_task_id and self.name == "app.tasks.rag_tasks.ingest_document_task":
            our_task_id = task_id
        
        # Only try to update Task record if we have a task_id
        # Some tasks (like generate_embeddings_task) don't use Task records
        if not our_task_id:
            logger.debug(f"No task_id in kwargs for Celery task {task_id} - skipping Task record update")
            return

        # Update task status in database using our Task model ID
        with SessionLocal() as session:
            task = session.query(Task).filter(Task.id == UUID(our_task_id)).first()
            if task:
                task.status = TaskStatus.SUCCESS
                task.result = retval
                task.completed_at = datetime.now(timezone.utc)
                session.commit()
            else:
                logger.error(f"Task {our_task_id} not found in database (on_success)")

    def update_progress(self, task_id: str, current: int, total: int, message: str):
        """
        Update task progress in database.
        
        Args:
            task_id: Our Task model UUID (not Celery task ID).
            current: Current progress value.
            total: Total progress value.
            message: Progress message.
        """
        with SessionLocal() as session:
            task = session.query(Task).filter(Task.id == UUID(task_id)).first()
            if task:
                task.status = TaskStatus.PROGRESS
                task.progress_current = current
                task.progress_total = total
                task.progress_message = message
                session.commit()
            else:
                logger.error(f"Task {task_id} not found in database (update_progress)")


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
    task_id: str | None = None,
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
        task_id: Optional Task model UUID (defaults to Celery task ID).

    Returns:
        Dict with ingestion results.

    Raises:
        Exception: If ingestion fails (will be retried).
    """
    celery_task_id = self.request.id
    our_task_id = task_id or celery_task_id
    logger.info(
        f"Starting document ingestion task: {celery_task_id} (task_id={our_task_id})"
    )

    try:
        # Update task status to STARTED
        # Use Task model ID for state updates
        with SessionLocal() as session:
            task = session.query(Task).filter(Task.id == UUID(our_task_id)).first()
            if task:
                task.status = TaskStatus.STARTED
                task.started_at = datetime.now(timezone.utc)
                task.progress_message = "Loading document..."
                # Store celery_task_id if not already set
                if not task.celery_task_id:
                    task.celery_task_id = celery_task_id
                session.commit()
            else:
                logger.error(f"Task {our_task_id} not found in database!")
                raise ValueError(f"Task {our_task_id} not found")

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
        self.update_progress(our_task_id, 10, 100, "Parsing document...")

        # Note: We need to refactor pipeline to accept sync session
        # For now, we'll use a workaround with sync session
        from sqlalchemy.orm import Session

        with SessionLocal() as db_session:
            # Refactor needed: Convert pipeline to use sync session
            # This is a placeholder - actual implementation needs async->sync conversion

            self.update_progress(our_task_id, 30, 100, "Extracting text...")

            # Load document
            from app.services.rag.document_loader import DoclingDocumentLoader

            loader = DoclingDocumentLoader()
            doc = loader.load(request.file_path)

            self.update_progress(our_task_id, 50, 100, "Chunking content...")

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

            self.update_progress(our_task_id, 70, 100, "Creating chunks...")

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

            self.update_progress(our_task_id, 90, 100, "Saving to database...")

            # Persist to database (sync)
            import hashlib
            from app.models.document import (
                Document as DocumentModel,
                DocumentSourceType,
                DocumentVisibility,
                DocumentProcessingStatus,
            )
            from app.models.chunk import Chunk as ChunkModel

            # Calculate checksum
            sha256 = hashlib.sha256()
            with open(request.file_path, "rb") as f:
                for chunk_data in iter(lambda: f.read(4096), b""):
                    sha256.update(chunk_data)
            checksum = sha256.hexdigest()

            # Check if document with this checksum already exists
            existing_document = (
                db_session.query(DocumentModel)
                .filter(
                    DocumentModel.tenant_id == request.tenant_id,
                    DocumentModel.checksum == checksum,
                )
                .first()
            )

            if existing_document:
                # Document already exists - reprocess it
                logger.info(
                    f"Document already exists (checksum={checksum}), reprocessing: {existing_document.id}"
                )
                
                # Delete old chunks
                db_session.query(ChunkModel).filter(
                    ChunkModel.document_id == existing_document.id
                ).delete()
                
                # Update existing document
                document = existing_document
                document.title = sanitize_text(document_title) or document.title
                if request.description:
                    document.description = sanitize_text(request.description)
                document.storage_path = request.file_path
                document.file_size_bytes = Path(request.file_path).stat().st_size
                document.version += 1
                document.language = request.language
                document.is_active = True
                document.processing_status = DocumentProcessingStatus.CHUNKED
                document.processing_error = None
                document.chunk_count = len(chunks)
                document.extra_metadata = {
                    "pages": loader.get_page_count(doc),
                    "chunking": {
                        "max_tokens": request.max_chunk_tokens,
                        "overlap_tokens": request.chunk_overlap_tokens,
                    },
                    "reprocessed": True,
                }
                db_session.flush()
            else:
                # Create new document
                document = DocumentModel(
                    tenant_id=request.tenant_id,
                    owner_user_id=request.owner_user_id,
                    title=sanitize_text(document_title) or "Untitled Document",
                    description=sanitize_text(request.description),
                    source_type=DocumentSourceType.UPLOADED,
                    visibility=DocumentVisibility.TENANT,
                    storage_path=request.file_path,
                    mime_type=None,
                    checksum=checksum,
                    file_size_bytes=Path(request.file_path).stat().st_size,
                    version=1,
                    language=request.language,
                    is_active=True,
                    processing_status=DocumentProcessingStatus.CHUNKED,  # Set to CHUNKED, not READY
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
                    section=sanitize_text(chunk.metadata.section_title),
                    language=chunk.metadata.language,
                    content=sanitize_text(chunk.content),
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
                "reprocessed": existing_document is not None,
                "stats": {
                    "total_chunks": len(chunks),
                    "total_tokens": total_tokens,
                    "avg_tokens_per_chunk": round(avg_tokens, 1),
                    "pages_processed": loader.get_page_count(doc),
                    "language_detected": request.language,
                },
            }

            if existing_document:
                logger.info(
                    f"Document reprocessed successfully: {document.id} ({len(chunks)} chunks, version {document.version})"
                )
            else:
                logger.info(
                    f"Document ingested successfully: {document.id} ({len(chunks)} chunks)"
                )

            # Queue embedding generation task after successful ingestion
            # This runs separately to avoid Celery timeout issues
            try:
                logger.info(f"Queueing embedding task for document {document.id}")
                generate_embeddings_task.delay(document_id=str(document.id))
            except Exception as embed_err:
                logger.error(
                    f"Failed to queue embedding task for {document.id}: {embed_err}"
                )
                # Don't fail the ingestion task if embedding queueing fails
                # User can manually retry embeddings later

            return result

    except DocumentLoadError as e:
        logger.error(f"Document loading failed: {e}")
        raise self.retry(exc=e)

    except Exception as e:
        logger.error(f"Unexpected error during ingestion: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=CallbackTask,
    name="app.tasks.rag_tasks.generate_embeddings_task",
    max_retries=3,
    default_retry_delay=120,  # Retry after 2 minutes
    soft_time_limit=1800,  # 30 minutes soft limit
    time_limit=2400,  # 40 minutes hard limit
)
def generate_embeddings_task(
    self,
    document_id: str,
    batch_size: int = 32,
) -> dict:
    """
    Generate embeddings for all chunks of a document.

    This task runs separately from ingestion to avoid timeout issues.
    For large documents, embeddings are generated in batches.

    Args:
        self: Celery task instance (injected).
        document_id: Document UUID (string).
        batch_size: Number of chunks to embed at once (default: 32).

    Returns:
        Dict with embedding stats.

    Raises:
        Exception: If embedding generation fails (will be retried).
    """
    celery_task_id = self.request.id
    logger.info(
        f"Starting embedding generation task: {celery_task_id} (document_id={document_id})"
    )

    from app.models.document import Document, DocumentProcessingStatus
    from app.models.chunk import Chunk
    from app.services.rag.embedding_service import get_embedding_service

    try:
        with SessionLocal() as session:
            # Get document
            doc_uuid = UUID(document_id)
            document = session.query(Document).filter(Document.id == doc_uuid).first()

            if not document:
                raise ValueError(f"Document {document_id} not found")

            # Update status to EMBEDDING
            document.processing_status = DocumentProcessingStatus.EMBEDDING
            session.commit()

            logger.info(f"Document {document_id} status: EMBEDDING")

            # Get all chunks without embeddings
            chunks = (
                session.query(Chunk)
                .filter(Chunk.document_id == doc_uuid, Chunk.embedding.is_(None))
                .order_by(Chunk.chunk_index)
                .all()
            )

            if not chunks:
                logger.info(f"No chunks need embeddings for document {document_id}")
                # Mark as ready since all chunks already have embeddings
                document.processing_status = DocumentProcessingStatus.READY
                session.commit()
                return {
                    "chunks_processed": 0,
                    "status": "ready",
                    "message": "All chunks already have embeddings",
                }

            logger.info(
                f"Generating embeddings for {len(chunks)} chunks (batch_size={batch_size})"
            )

            # Get embedding service
            embedding_service = get_embedding_service()

            # Process chunks in batches to avoid memory issues
            total_chunks = len(chunks)
            processed_count = 0

            for i in range(0, total_chunks, batch_size):
                batch = chunks[i : i + batch_size]
                texts = [chunk.content for chunk in batch]

                logger.info(
                    f"Processing batch {i // batch_size + 1}/{(total_chunks + batch_size - 1) // batch_size} "
                    f"({len(batch)} chunks)"
                )

                # Generate embeddings for batch
                embeddings = embedding_service.encode_batch(
                    texts=texts,
                    batch_size=batch_size,
                )

                # Update chunks with embeddings
                for chunk, embedding in zip(batch, embeddings):
                    chunk.embedding = embedding.tolist()  # Convert numpy array to list
                    processed_count += 1

                # Commit after each batch to avoid long transactions
                session.commit()

                logger.info(
                    f"Committed batch: {processed_count}/{total_chunks} chunks processed"
                )

            # Update document status to READY
            document.processing_status = DocumentProcessingStatus.READY
            document.processing_error = None  # Clear any previous errors
            session.commit()

            logger.info(
                f"Successfully generated embeddings for {processed_count} chunks "
                f"of document {document_id}"
            )

            return {
                "document_id": document_id,
                "chunks_processed": processed_count,
                "status": "ready",
                "embedding_dimension": embedding_service.get_embedding_dimension(),
            }

    except Exception as e:
        # Mark document as failed
        logger.error(f"Failed to generate embeddings for document {document_id}: {e}")

        try:
            with SessionLocal() as session:
                document = (
                    session.query(Document).filter(Document.id == UUID(document_id)).first()
                )
                if document:
                    document.processing_status = DocumentProcessingStatus.FAILED
                    document.processing_error = f"Embedding generation failed: {str(e)}"
                    session.commit()
        except Exception as db_err:
            logger.error(f"Failed to update document status: {db_err}")

        raise


@celery_app.task(
    bind=True,
    name="app.tasks.rag_tasks.generate_embeddings_batch_task",
    max_retries=2,
    default_retry_delay=300,  # 5 minutes
    soft_time_limit=3600,  # 1 hour soft limit
    time_limit=4200,  # 70 minutes hard limit
)
def generate_embeddings_batch_task(
    self,
    document_ids: list[str],
    batch_size: int = 32,
) -> dict:
    """
    Generate embeddings for multiple documents in parallel.

    This task spawns parallel embedding tasks for each document.

    Args:
        self: Celery task instance (injected).
        document_ids: List of document UUIDs (strings).
        batch_size: Number of chunks to embed at once per document.

    Returns:
        Dict with batch processing stats.
    """
    celery_task_id = self.request.id
    logger.info(
        f"Starting batch embedding generation: {celery_task_id} "
        f"({len(document_ids)} documents)"
    )

    try:
        # Create a group of parallel embedding tasks
        job = group(
            generate_embeddings_task.s(document_id=doc_id, batch_size=batch_size)
            for doc_id in document_ids
        )

        # Execute tasks in parallel
        result = job.apply_async()

        logger.info(f"Spawned {len(document_ids)} parallel embedding tasks")

        return {
            "documents_queued": len(document_ids),
            "group_id": result.id,
            "status": "processing",
            "message": f"Embedding generation queued for {len(document_ids)} documents",
        }

    except Exception as e:
        logger.error(f"Failed to queue batch embedding tasks: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    name="app.tasks.rag_tasks.generate_embeddings_for_pending_documents_task",
    max_retries=1,
    default_retry_delay=600,  # 10 minutes
)
def generate_embeddings_for_pending_documents_task(self) -> dict:
    """
    Generate embeddings for all documents in CHUNKED status.

    This is a maintenance task that can be run periodically or manually
    to catch any documents that failed to get embeddings.

    Returns:
        Dict with processing stats.
    """
    celery_task_id = self.request.id
    logger.info(f"Starting pending documents embedding task: {celery_task_id}")

    try:
        with SessionLocal() as session:
            # Find all documents that are chunked but not yet embedded
            documents = (
                session.query(Document)
                .filter(
                    Document.processing_status == DocumentProcessingStatus.CHUNKED,
                    Document.is_active == True,
                )
                .all()
            )

            if not documents:
                logger.info("No pending documents found for embedding generation")
                return {
                    "total_documents": 0,
                    "message": "No pending documents",
                }

            logger.info(
                f"Found {len(documents)} documents pending embedding generation"
            )

            # Queue embedding tasks for each document
            document_ids = [str(doc.id) for doc in documents]

            # Use batch task to process in parallel
            generate_embeddings_batch_task.delay(
                document_ids=document_ids,
                batch_size=32,
            )

            return {
                "total_documents": len(documents),
                "status": "queued",
                "message": f"Embedding generation queued for {len(documents)} documents",
            }

    except Exception as e:
        logger.error(
            f"Failed to process pending documents: {e}", exc_info=True
        )
        raise

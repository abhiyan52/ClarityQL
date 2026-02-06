"""Embedding generation task for document chunks.

This task generates embeddings for chunks that don't have them yet,
and updates the document status to READY when complete.
"""

import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_embedding_settings
from app.db.session import get_async_session
from app.models.chunk import Chunk
from app.models.document import Document, DocumentProcessingStatus
from app.services.rag.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)


async def generate_embeddings_for_document(
    document_id: UUID,
    session: AsyncSession,
) -> dict:
    """
    Generate embeddings for all chunks of a document.

    Args:
        document_id: UUID of the document to process.
        session: Database session.

    Returns:
        Dict with processing stats.

    Raises:
        Exception: If embedding generation fails.
    """
    try:
        # Update document status to EMBEDDING
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(processing_status=DocumentProcessingStatus.EMBEDDING)
        )
        await session.commit()

        logger.info(f"Starting embedding generation for document {document_id}")

        # Get all chunks for this document that don't have embeddings
        result = await session.execute(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .where(Chunk.embedding.is_(None))
            .order_by(Chunk.chunk_index)
        )
        chunks = result.scalars().all()

        if not chunks:
            logger.info(f"No chunks need embeddings for document {document_id}")
            # Mark as ready since all chunks already have embeddings
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(processing_status=DocumentProcessingStatus.READY)
            )
            await session.commit()
            return {
                "chunks_processed": 0,
                "status": "ready",
            }

        logger.info(f"Generating embeddings for {len(chunks)} chunks")

        # Get embedding service
        embedding_service = get_embedding_service()

        # Prepare texts for batch encoding
        texts = [chunk.content for chunk in chunks]

        # Generate embeddings in batch
        embeddings = embedding_service.encode_batch(
            texts=texts,
            batch_size=32,
        )

        # Update chunks with embeddings
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding.tolist()  # Convert numpy array to list

        await session.commit()

        logger.info(
            f"Successfully generated embeddings for {len(chunks)} chunks "
            f"of document {document_id}"
        )

        # Update document status to READY
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                processing_status=DocumentProcessingStatus.READY,
                processing_error=None,  # Clear any previous errors
            )
        )
        await session.commit()

        return {
            "chunks_processed": len(chunks),
            "status": "ready",
            "embedding_dimension": embedding_service.get_embedding_dimension(),
        }

    except Exception as e:
        # Mark document as failed
        logger.error(f"Failed to generate embeddings for document {document_id}: {e}")
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                processing_status=DocumentProcessingStatus.FAILED,
                processing_error=f"Embedding generation failed: {str(e)}",
            )
        )
        await session.commit()
        raise


async def generate_embeddings_for_all_pending_documents(
    session: AsyncSession,
) -> dict:
    """
    Generate embeddings for all documents in CHUNKED status.

    This is useful for batch processing after documents are uploaded.

    Args:
        session: Database session.

    Returns:
        Dict with processing stats.
    """
    # Find all documents that are chunked but not yet embedded
    result = await session.execute(
        select(Document)
        .where(Document.processing_status == DocumentProcessingStatus.CHUNKED)
        .where(Document.is_active == True)
    )
    documents = result.scalars().all()

    logger.info(f"Found {len(documents)} documents pending embedding generation")

    success_count = 0
    failure_count = 0
    errors = []

    for doc in documents:
        try:
            stats = await generate_embeddings_for_document(doc.id, session)
            success_count += 1
            logger.info(f"Document {doc.id}: {stats}")
        except Exception as e:
            failure_count += 1
            errors.append({"document_id": str(doc.id), "error": str(e)})
            logger.error(f"Failed to process document {doc.id}: {e}")

    return {
        "total_documents": len(documents),
        "success": success_count,
        "failures": failure_count,
        "errors": errors,
    }


# Example usage in a Celery task
"""
from celery import shared_task
from app.db.session import get_async_session

@shared_task(name="generate_embeddings")
def generate_embeddings_task(document_id: str):
    '''Celery task to generate embeddings for a document.'''
    import asyncio
    from uuid import UUID
    
    async def run():
        async with get_async_session() as session:
            return await generate_embeddings_for_document(
                document_id=UUID(document_id),
                session=session,
            )
    
    return asyncio.run(run())
"""

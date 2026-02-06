"""RAG ingestion pipeline orchestrator.

Coordinates document loading, chunking, and preparation for embedding.
"""

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentSourceType, DocumentVisibility
from app.schemas.rag import (
    IngestionRequest,
    IngestionResponse,
    IngestionStats,
    ProcessedChunk,
)
from app.services.rag.chunker import SemanticChunker
from app.services.rag.document_loader import DoclingDocumentLoader, DocumentLoadError
from app.services.rag.language_detector import detect_language_from_multiple_samples
from app.services.rag.token_counter import count_tokens

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Enterprise-grade RAG ingestion pipeline.

    Orchestrates:
    1. Document loading (Docling)
    2. Language detection
    3. Semantic chunking
    4. Metadata enrichment
    5. Database persistence (without embeddings)

    Embeddings are generated separately in a follow-up step.
    """

    def __init__(self):
        """Initialize the ingestion pipeline."""
        self.loader = DoclingDocumentLoader()
        logger.info("IngestionPipeline initialized")

    async def ingest_document(
        self,
        request: IngestionRequest,
        session: AsyncSession,
    ) -> IngestionResponse:
        """
        Ingest a document into the RAG system.

        Args:
            request: Ingestion request with file path and parameters.
            session: Database session.

        Returns:
            IngestionResponse with document ID and stats.

        Raises:
            DocumentLoadError: If loading or processing fails.

        Workflow:
            1. Load and parse document (Docling)
            2. Extract structured elements
            3. Detect language
            4. Chunk content semantically
            5. Persist to database (Document + Chunks without embeddings)
            6. Return stats
        """
        start_time = time.time()

        logger.info(f"Starting ingestion pipeline for: {request.file_path}")

        # ── Step 1: Load document ─────────────────────────────────────
        doc = self.loader.load(request.file_path)

        # Extract metadata
        document_title = (
            request.document_title or self.loader.get_document_title(doc)
        )
        file_name = Path(request.file_path).name
        page_count = self.loader.get_page_count(doc)

        logger.info(
            f"Document loaded: {document_title} "
            f"({page_count or 'N/A'} pages)"
        )

        # ── Step 2: Extract text elements ─────────────────────────────
        elements = self.loader.extract_text_elements(doc)

        if not elements:
            raise DocumentLoadError("No text content extracted from document")

        logger.info(f"Extracted {len(elements)} text elements")

        # ── Step 3: Detect language ───────────────────────────────────
        language = request.language

        if not language:
            # Sample first few elements for language detection
            sample_texts = [text for text, _ in elements[:5]]
            language = detect_language_from_multiple_samples(sample_texts)

        logger.info(f"Document language: {language}")

        # ── Step 4: Chunk content ─────────────────────────────────────
        chunker = SemanticChunker(
            max_tokens=request.max_chunk_tokens,
            overlap_tokens=request.chunk_overlap_tokens,
        )

        chunks: list[ProcessedChunk] = chunker.chunk_elements(
            elements=elements,
            document_title=document_title,
            file_name=file_name,
            language=language,
        )

        if not chunks:
            raise DocumentLoadError("Failed to create chunks from document")

        logger.info(f"Created {len(chunks)} chunks")

        # ── Step 5: Calculate checksum ────────────────────────────────
        checksum = await self._calculate_file_checksum(request.file_path)

        # ── Step 6: Persist to database ───────────────────────────────
        document_record = await self._persist_document(
            session=session,
            request=request,
            document_title=document_title,
            file_name=file_name,
            language=language,
            page_count=page_count,
            chunk_count=len(chunks),
            checksum=checksum,
        )

        # Persist chunks (without embeddings for now)
        await self._persist_chunks(
            session=session,
            chunks=chunks,
            document_id=document_record.id,
            tenant_id=document_record.tenant_id,
        )

        await session.commit()

        logger.info(
            f"Document persisted: {document_record.id} with {len(chunks)} chunks"
        )

        # ── Step 7: Calculate stats ───────────────────────────────────
        total_tokens = sum(chunk.metadata.token_count for chunk in chunks)
        avg_tokens = total_tokens / len(chunks) if chunks else 0

        stats = IngestionStats(
            total_chunks=len(chunks),
            total_tokens=total_tokens,
            avg_tokens_per_chunk=round(avg_tokens, 1),
            pages_processed=page_count,
            language_detected=language,
        )

        # ── Step 8: Return response ───────────────────────────────────
        processing_time = (time.time() - start_time) * 1000  # ms

        response = IngestionResponse(
            document_id=document_record.id,
            chunks_created=len(chunks),
            stats=stats,
            processing_time_ms=round(processing_time, 2),
            created_at=document_record.created_at,
        )

        logger.info(
            f"Ingestion complete: {len(chunks)} chunks in {processing_time:.0f}ms"
        )

        return response

    async def _persist_document(
        self,
        session: AsyncSession,
        request: IngestionRequest,
        document_title: str,
        file_name: str,
        language: str,
        page_count: Optional[int],
        chunk_count: int,
        checksum: str,
    ) -> Document:
        """Persist document record to database."""
        from app.models.document import Document as DocumentModel

        # Map source type
        source_type_map = {
            "uploaded": DocumentSourceType.UPLOADED,
            "system": DocumentSourceType.SYSTEM,
            "web": DocumentSourceType.WEB,
        }
        source_type = source_type_map.get(
            request.source_type.lower(),
            DocumentSourceType.UPLOADED,
        )

        # Create document record
        document = DocumentModel(
            tenant_id=request.tenant_id,
            owner_user_id=request.owner_user_id,
            title=document_title,
            description=request.description,
            source_type=source_type,
            visibility=DocumentVisibility.TENANT,  # Default to tenant-wide
            storage_path=request.file_path,
            mime_type=self._detect_mime_type(file_name),
            checksum=checksum,
            file_size_bytes=Path(request.file_path).stat().st_size,
            version=1,
            language=language,
            is_active=True,
            chunk_count=chunk_count,
            extra_metadata={
                "pages": page_count,
                "chunking": {
                    "max_tokens": request.max_chunk_tokens,
                    "overlap_tokens": request.chunk_overlap_tokens,
                },
            },
        )

        session.add(document)
        await session.flush()
        await session.refresh(document)

        return document

    async def _persist_chunks(
        self,
        session: AsyncSession,
        chunks: list[ProcessedChunk],
        document_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """
        Persist chunks to database (without embeddings).

        Embeddings will be generated in a separate batch job.
        """
        from app.models.chunk import Chunk as ChunkModel

        for chunk in chunks:
            chunk_record = ChunkModel(
                document_id=document_id,
                tenant_id=tenant_id,
                chunk_index=chunk.metadata.chunk_index,
                page_number=chunk.metadata.page_number,
                section=chunk.metadata.section_title,
                language=chunk.metadata.language,
                content=chunk.content,
                token_count=chunk.metadata.token_count,
                embedding=None,  # To be generated later
                extra_metadata=chunk.metadata.extra,
            )
            session.add(chunk_record)

        await session.flush()

    async def _calculate_file_checksum(self, file_path: str) -> str:
        """Calculate SHA-256 checksum for file deduplication."""
        sha256 = hashlib.sha256()

        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)

        return sha256.hexdigest()

    def _detect_mime_type(self, file_name: str) -> Optional[str]:
        """Detect MIME type from file extension."""
        extension = Path(file_name).suffix.lower()

        mime_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".html": "text/html",
            ".htm": "text/html",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }

        return mime_map.get(extension)

    def get_chunks_for_embedding(
        self,
        chunks: list[ProcessedChunk],
    ) -> list[tuple[str, dict]]:
        """
        Prepare chunks for embedding generation.

        Returns a list of (text, metadata) tuples ready for embedding models.

        Args:
            chunks: List of ProcessedChunk objects.

        Returns:
            List of (text_for_embedding, metadata_dict) tuples.

        Note:
            This method prepares chunks but doesn't generate embeddings.
            Use a separate embedding service (OpenAI, BGE, etc.) to generate vectors.
        """
        embedding_inputs: list[tuple[str, dict]] = []

        for chunk in chunks:
            # Use context-enriched string for better retrieval
            text = chunk.context_string

            # Convert metadata to dict
            metadata = chunk.metadata.model_dump()

            embedding_inputs.append((text, metadata))

        return embedding_inputs

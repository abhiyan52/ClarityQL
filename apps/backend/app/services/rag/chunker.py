"""Semantic chunking strategy for RAG ingestion.

Balances semantic boundaries (section headers, paragraphs) with token limits.
Includes overlap for context preservation.
"""

import logging
from typing import Optional

from app.schemas.rag import ChunkMetadata, ProcessedChunk
from app.services.rag.token_counter import count_tokens

logger = logging.getLogger(__name__)


class SemanticChunker:
    """
    Chunk documents intelligently based on semantic boundaries and token limits.

    Strategy:
    1. Respect semantic boundaries (paragraphs, sections)
    2. Stay within token limits (~500 tokens per chunk)
    3. Add overlap between chunks for context (~10-15%)
    4. Preserve metadata for traceability
    """

    def __init__(
        self,
        max_tokens: int = 500,
        overlap_tokens: int = 50,
        min_tokens: int = 50,
    ):
        """
        Initialize the semantic chunker.

        Args:
            max_tokens: Maximum tokens per chunk (target size).
            overlap_tokens: Number of tokens to overlap between chunks.
            min_tokens: Minimum tokens for a valid chunk.
        """
        self.max_tokens = max_tokens
        self.overlap_tokens = min(overlap_tokens, max_tokens // 4)
        self.min_tokens = min_tokens

        logger.info(
            f"SemanticChunker initialized: "
            f"max={max_tokens}, overlap={self.overlap_tokens}, min={min_tokens}"
        )

    def chunk_elements(
        self,
        elements: list[tuple[str, dict]],
        document_title: str,
        file_name: str,
        language: str = "en",
    ) -> list[ProcessedChunk]:
        """
        Chunk a list of text elements into embedding-ready chunks.

        Args:
            elements: List of (text, metadata) tuples from document loader.
            document_title: Title of the source document.
            file_name: Original file name.
            language: Document language (ISO 639-1 code).

        Returns:
            List of ProcessedChunk objects ready for embedding.

        Strategy:
            1. Group elements by semantic boundaries (sections)
            2. Build chunks respecting token limits
            3. Add overlap between adjacent chunks
            4. Preserve metadata for each chunk
        """
        if not elements:
            logger.warning("No elements provided for chunking")
            return []

        chunks: list[ProcessedChunk] = []
        current_chunk_texts: list[str] = []
        current_chunk_metadata: Optional[dict] = None
        current_tokens = 0
        chunk_index = 0

        # Track for overlap
        previous_chunk_tail: list[str] = []

        for text, metadata in elements:
            text = text.strip()
            if not text:
                continue

            element_tokens = count_tokens(text)

            # Check if adding this element exceeds max tokens
            potential_tokens = current_tokens + element_tokens

            if potential_tokens > self.max_tokens and current_chunk_texts:
                # Finalize current chunk
                chunk = self._finalize_chunk(
                    texts=current_chunk_texts,
                    metadata=current_chunk_metadata or metadata,
                    chunk_index=chunk_index,
                    document_title=document_title,
                    file_name=file_name,
                    language=language,
                )

                if chunk:
                    chunks.append(chunk)
                    chunk_index += 1

                # Prepare overlap for next chunk
                previous_chunk_tail = self._get_overlap_texts(
                    current_chunk_texts,
                    self.overlap_tokens,
                )

                # Start new chunk with overlap
                current_chunk_texts = previous_chunk_tail.copy()
                current_tokens = sum(count_tokens(t) for t in current_chunk_texts)
                current_chunk_metadata = metadata

            # Add element to current chunk
            current_chunk_texts.append(text)
            current_tokens += element_tokens

            # Update metadata (use first element's metadata for chunk)
            if current_chunk_metadata is None:
                current_chunk_metadata = metadata

        # Finalize last chunk
        if current_chunk_texts:
            chunk = self._finalize_chunk(
                texts=current_chunk_texts,
                metadata=current_chunk_metadata or {},
                chunk_index=chunk_index,
                document_title=document_title,
                file_name=file_name,
                language=language,
            )
            if chunk:
                chunks.append(chunk)

        logger.info(
            f"Chunking complete: {len(chunks)} chunks created from {len(elements)} elements"
        )

        return chunks

    def _finalize_chunk(
        self,
        texts: list[str],
        metadata: dict,
        chunk_index: int,
        document_title: str,
        file_name: str,
        language: str,
    ) -> Optional[ProcessedChunk]:
        """
        Finalize a chunk and create ProcessedChunk object.

        Args:
            texts: List of text strings to combine.
            metadata: Metadata from elements.
            chunk_index: Index of this chunk.
            document_title: Source document title.
            file_name: Source file name.
            language: Document language.

        Returns:
            ProcessedChunk or None if chunk is too small.
        """
        if not texts:
            return None

        # Combine texts with double newline
        content = "\n\n".join(texts).strip()

        # Count tokens
        token_count = count_tokens(content)

        # Skip if too small
        if token_count < self.min_tokens:
            logger.debug(
                f"Skipping chunk {chunk_index}: too small ({token_count} tokens)"
            )
            return None

        # Build chunk metadata
        chunk_meta = ChunkMetadata(
            document_title=document_title,
            file_name=file_name,
            page_number=metadata.get("page_number"),
            section_title=metadata.get("section_title"),
            heading_level=metadata.get("heading_level"),
            chunk_index=chunk_index,
            token_count=token_count,
            language=language,
            element_type=metadata.get("element_type"),
            extra=metadata.get("extra", {}),
        )

        return ProcessedChunk(content=content, metadata=chunk_meta)

    def _get_overlap_texts(
        self,
        texts: list[str],
        target_overlap_tokens: int,
    ) -> list[str]:
        """
        Extract the last N tokens worth of text for overlap.

        Args:
            texts: List of text strings.
            target_overlap_tokens: Target number of overlap tokens.

        Returns:
            List of texts from the end that fit within overlap budget.
        """
        if not texts or target_overlap_tokens <= 0:
            return []

        overlap_texts: list[str] = []
        overlap_tokens = 0

        # Walk backwards through texts
        for text in reversed(texts):
            text_tokens = count_tokens(text)

            # Stop if adding this text exceeds overlap budget
            if overlap_tokens + text_tokens > target_overlap_tokens:
                break

            overlap_texts.insert(0, text)
            overlap_tokens += text_tokens

        return overlap_texts


class FixedSizeChunker:
    """
    Simple fixed-size chunker as fallback.

    Chunks text into fixed token-sized blocks with overlap.
    Less semantically aware but guarantees consistent chunk sizes.
    """

    def __init__(
        self,
        max_tokens: int = 500,
        overlap_tokens: int = 50,
    ):
        """
        Initialize fixed-size chunker.

        Args:
            max_tokens: Maximum tokens per chunk.
            overlap_tokens: Overlap tokens between chunks.
        """
        self.max_tokens = max_tokens
        self.overlap_tokens = min(overlap_tokens, max_tokens // 4)

    def chunk_text(
        self,
        text: str,
        document_title: str,
        file_name: str,
        language: str = "en",
    ) -> list[ProcessedChunk]:
        """
        Chunk text into fixed-size blocks.

        Args:
            text: Text to chunk.
            document_title: Source document title.
            file_name: Source file name.
            language: Document language.

        Returns:
            List of ProcessedChunk objects.
        """
        if not text or not text.strip():
            return []

        # Split into sentences (simple heuristic)
        sentences = self._split_sentences(text)

        chunks: list[ProcessedChunk] = []
        current_sentences: list[str] = []
        current_tokens = 0
        chunk_index = 0
        overlap_sentences: list[str] = []

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_tokens = count_tokens(sentence)

            if current_tokens + sentence_tokens > self.max_tokens and current_sentences:
                # Finalize chunk
                content = " ".join(current_sentences)
                chunk_meta = ChunkMetadata(
                    document_title=document_title,
                    file_name=file_name,
                    chunk_index=chunk_index,
                    token_count=count_tokens(content),
                    language=language,
                )
                chunks.append(ProcessedChunk(content=content, metadata=chunk_meta))
                chunk_index += 1

                # Calculate overlap
                overlap_sentences = self._get_overlap_sentences(
                    current_sentences,
                    self.overlap_tokens,
                )

                # Start new chunk with overlap
                current_sentences = overlap_sentences.copy()
                current_tokens = sum(count_tokens(s) for s in current_sentences)

            current_sentences.append(sentence)
            current_tokens += sentence_tokens

        # Finalize last chunk
        if current_sentences:
            content = " ".join(current_sentences)
            chunk_meta = ChunkMetadata(
                document_title=document_title,
                file_name=file_name,
                chunk_index=chunk_index,
                token_count=count_tokens(content),
                language=language,
            )
            chunks.append(ProcessedChunk(content=content, metadata=chunk_meta))

        return chunks

    def _split_sentences(self, text: str) -> list[str]:
        """Simple sentence splitter."""
        # Split on common sentence boundaries
        import re

        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _get_overlap_sentences(
        self,
        sentences: list[str],
        target_tokens: int,
    ) -> list[str]:
        """Get last N sentences that fit within token budget."""
        overlap: list[str] = []
        tokens = 0

        for sentence in reversed(sentences):
            sentence_tokens = count_tokens(sentence)
            if tokens + sentence_tokens > target_tokens:
                break
            overlap.insert(0, sentence)
            tokens += sentence_tokens

        return overlap

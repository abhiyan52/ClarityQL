"""Embedding service using Sentence Transformers.

Generates dense vector embeddings for text chunks to enable semantic search
and retrieval-augmented generation (RAG).
"""

import logging
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import get_embedding_settings

logger = logging.getLogger(__name__)


class EmbeddingServiceError(Exception):
    """Raised when embedding generation fails."""

    pass


class EmbeddingService:
    """
    Service for generating text embeddings using Sentence Transformers.

    Supports multilingual models like multilingual-e5-large-instruct for
    cross-lingual semantic similarity and retrieval.

    The service is designed to be singleton-like (one model instance per process)
    for efficiency, as loading the model is expensive.
    """

    def __init__(self, model_name: str | None = None):
        """
        Initialize the embedding service with a Sentence Transformer model.

        Args:
            model_name: Optional model name. If not provided, uses config default.

        Raises:
            EmbeddingServiceError: If model loading fails.

        Example:
            >>> service = EmbeddingService()
            >>> embedding = service.encode("Hello, world!")
            >>> print(embedding.shape)  # (1024,) for multilingual-e5-large-instruct
        """
        self.settings = get_embedding_settings()
        self.model_name = model_name or self.settings.embedding_model
        self.normalize = self.settings.embedding_normalize

        try:
            logger.info(f"Loading embedding model: {self.model_name}")
            
            # Load model with optional cache directory
            model_kwargs = {}
            if self.settings.embedding_cache_dir:
                model_kwargs["cache_folder"] = self.settings.embedding_cache_dir

            self.model = SentenceTransformer(
                self.model_name,
                **model_kwargs
            )
            
            # Verify embedding dimension matches config
            test_embedding = self.model.encode(
                "test",
                normalize_embeddings=self.normalize
            )
            actual_dim = len(test_embedding)
            
            if actual_dim != self.settings.embedding_dimension:
                logger.warning(
                    f"Model dimension ({actual_dim}) doesn't match config "
                    f"({self.settings.embedding_dimension}). Using actual dimension."
                )
            
            self.embedding_dimension = actual_dim
            
            logger.info(
                f"Successfully loaded model {self.model_name} "
                f"(dimension: {self.embedding_dimension})"
            )

        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise EmbeddingServiceError(f"Failed to load model: {e}")

    def encode(
        self,
        text: str,
        normalize: bool | None = None,
    ) -> np.ndarray:
        """
        Generate embedding for a single text string.

        Args:
            text: Input text to embed.
            normalize: Optional override for normalization. If None, uses config default.

        Returns:
            Embedding vector as numpy array.

        Raises:
            EmbeddingServiceError: If encoding fails.

        Example:
            >>> service = EmbeddingService()
            >>> embedding = service.encode("Machine learning is fascinating")
            >>> print(embedding.shape)  # (1024,)
        """
        if not text or not text.strip():
            raise EmbeddingServiceError("Cannot encode empty text")

        normalize_embeddings = normalize if normalize is not None else self.normalize

        try:
            embedding = self.model.encode(
                text,
                normalize_embeddings=normalize_embeddings,
                show_progress_bar=False,
            )
            return embedding

        except Exception as e:
            logger.error(f"Failed to encode text: {e}")
            raise EmbeddingServiceError(f"Encoding failed: {e}")

    def encode_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        normalize: bool | None = None,
    ) -> np.ndarray:
        """
        Generate embeddings for a batch of texts efficiently.

        Args:
            texts: List of input texts to embed.
            batch_size: Number of texts to process in each batch.
            normalize: Optional override for normalization. If None, uses config default.

        Returns:
            Array of embeddings with shape (len(texts), embedding_dimension).

        Raises:
            EmbeddingServiceError: If encoding fails.

        Example:
            >>> service = EmbeddingService()
            >>> texts = ["First chunk", "Second chunk", "Third chunk"]
            >>> embeddings = service.encode_batch(texts)
            >>> print(embeddings.shape)  # (3, 1024)
        """
        if not texts:
            raise EmbeddingServiceError("Cannot encode empty text list")

        # Filter out empty texts and track indices
        filtered_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                filtered_texts.append(text)
                valid_indices.append(i)

        if not filtered_texts:
            raise EmbeddingServiceError("All texts are empty")

        normalize_embeddings = normalize if normalize is not None else self.normalize

        try:
            logger.info(f"Encoding batch of {len(filtered_texts)} texts")
            
            embeddings = self.model.encode(
                filtered_texts,
                batch_size=batch_size,
                normalize_embeddings=normalize_embeddings,
                show_progress_bar=len(filtered_texts) > 100,  # Show progress for large batches
            )

            # If some texts were filtered out, create full array with zeros for empty texts
            if len(valid_indices) < len(texts):
                logger.warning(
                    f"Skipped {len(texts) - len(valid_indices)} empty texts in batch"
                )
                full_embeddings = np.zeros((len(texts), self.embedding_dimension))
                full_embeddings[valid_indices] = embeddings
                return full_embeddings

            return embeddings

        except Exception as e:
            logger.error(f"Failed to encode batch: {e}")
            raise EmbeddingServiceError(f"Batch encoding failed: {e}")

    def get_embedding_dimension(self) -> int:
        """
        Get the embedding dimension for the loaded model.

        Returns:
            Embedding vector dimension.
        """
        return self.embedding_dimension

    def get_model_name(self) -> str:
        """
        Get the name of the loaded model.

        Returns:
            Model name.
        """
        return self.model_name


# Global instance for reuse across the application
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """
    Get or create the global embedding service instance.

    This ensures we only load the model once per process, which is important
    for memory efficiency and performance.

    Returns:
        Shared EmbeddingService instance.

    Example:
        >>> service = get_embedding_service()
        >>> embedding = service.encode("Hello, world!")
    """
    global _embedding_service
    
    if _embedding_service is None:
        logger.info("Initializing global embedding service")
        _embedding_service = EmbeddingService()
    
    return _embedding_service


def reset_embedding_service():
    """
    Reset the global embedding service instance.

    Useful for testing or when you need to reload the model with different settings.
    """
    global _embedding_service
    _embedding_service = None
    logger.info("Embedding service reset")

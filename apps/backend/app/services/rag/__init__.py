"""RAG ingestion utilities package."""

# Optional imports to avoid dependency issues
__all__ = []

try:
    from .document_loader import DoclingDocumentLoader
    __all__.append("DoclingDocumentLoader")
except ImportError:
    pass

try:
    from .chunker import SemanticChunker
    __all__.append("SemanticChunker")
except ImportError:
    pass

try:
    from .embedding_service import EmbeddingService, get_embedding_service
    __all__.extend(["EmbeddingService", "get_embedding_service"])
except ImportError:
    pass


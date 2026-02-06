"""Document loader using Docling for enterprise document processing.

Supports: PDF, DOCX, PPTX, XLSX, HTML, and scanned images with OCR.
"""

import logging
from pathlib import Path
from typing import Optional

from docling.document_converter import DocumentConverter
from docling_core.types.doc import DoclingDocument, DocItem, TextItem, TableItem

from app.schemas.rag import SupportedFileType

logger = logging.getLogger(__name__)


# Mapping from file extensions to our enum
FILE_EXTENSION_MAP = {
    ".pdf": SupportedFileType.PDF,
    ".docx": SupportedFileType.DOCX,
    ".pptx": SupportedFileType.PPTX,
    ".xlsx": SupportedFileType.XLSX,
    ".html": SupportedFileType.HTML,
    ".htm": SupportedFileType.HTML,
    ".txt": SupportedFileType.TXT,
    ".md": SupportedFileType.MD,
    ".png": SupportedFileType.IMAGE,
    ".jpg": SupportedFileType.IMAGE,
    ".jpeg": SupportedFileType.IMAGE,
    ".tiff": SupportedFileType.IMAGE,
    ".tif": SupportedFileType.IMAGE,
}


class DocumentLoadError(Exception):
    """Raised when document loading fails."""

    pass


class DoclingDocumentLoader:
    """
    Load and parse documents using Docling.

    Docling is IBM's enterprise-grade document parser that handles:
    - PDFs (including scanned with OCR)
    - Office documents (DOCX, PPTX, XLSX)
    - HTML
    - Images (with OCR)

    It preserves semantic structure (headings, paragraphs, lists, tables).
    """

    def __init__(self):
        """Initialize the Docling document converter."""
        try:
            self.converter = DocumentConverter()
            logger.info("Docling DocumentConverter initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Docling: {e}")
            raise DocumentLoadError(f"Failed to initialize Docling: {e}")

    def detect_file_type(self, file_path: str | Path) -> SupportedFileType:
        """
        Detect file type from extension.

        Args:
            file_path: Path to the file.

        Returns:
            Detected file type.

        Raises:
            DocumentLoadError: If file type is not supported.
        """
        path = Path(file_path)
        extension = path.suffix.lower()

        file_type = FILE_EXTENSION_MAP.get(extension)
        if file_type is None:
            supported = ", ".join(FILE_EXTENSION_MAP.keys())
            raise DocumentLoadError(
                f"Unsupported file type: {extension}. "
                f"Supported types: {supported}"
            )

        return file_type

    def load(
        self,
        file_path: str | Path,
        file_name: Optional[str] = None,
    ) -> DoclingDocument:
        """
        Load and parse a document using Docling.

        Args:
            file_path: Path to the document file.
            file_name: Optional override for the document name.

        Returns:
            Parsed DoclingDocument with structured content.

        Raises:
            DocumentLoadError: If loading or parsing fails.

        Example:
            >>> loader = DoclingDocumentLoader()
            >>> doc = loader.load("report.pdf")
            >>> print(doc.name, len(doc.pages))
        """
        path = Path(file_path)

        # Validate file exists
        if not path.exists():
            raise DocumentLoadError(f"File not found: {file_path}")

        if not path.is_file():
            raise DocumentLoadError(f"Path is not a file: {file_path}")

        # Detect file type
        file_type = self.detect_file_type(path)
        logger.info(f"Loading {file_type.value} document: {path.name}")

        try:
            # Convert document using Docling
            result = self.converter.convert(str(path))

            if not result or not result.document:
                raise DocumentLoadError(
                    f"Docling failed to parse document: {file_path}"
                )

            doc: DoclingDocument = result.document

            # Override document name if provided
            if file_name:
                doc.name = file_name

            logger.info(
                f"Successfully loaded document: {doc.name} "
                f"({len(doc.pages) if hasattr(doc, 'pages') else 'N/A'} pages)"
            )

            return doc

        except Exception as e:
            logger.error(f"Failed to load document {file_path}: {e}")
            raise DocumentLoadError(f"Failed to load document: {e}")

    def extract_text_elements(
        self,
        doc: DoclingDocument,
    ) -> list[tuple[str, dict]]:
        """
        Extract text elements from DoclingDocument with metadata.

        Args:
            doc: Parsed DoclingDocument.

        Returns:
            List of (text, metadata) tuples where metadata includes:
                - element_type: Type of element (e.g., 'paragraph', 'heading')
                - page_number: Page number (1-indexed)
                - heading_level: For headings, the level (H1=1, H2=2, etc.)
                - section_title: Current section heading

        Example:
            >>> elements = loader.extract_text_elements(doc)
            >>> for text, meta in elements:
            ...     print(f"Page {meta['page_number']}: {text[:50]}...")
        """
        elements: list[tuple[str, dict]] = []
        current_section = None
        current_heading_level = None

        try:
            # iterate_items() yields (item, level) tuples in reading order
            for item, level in doc.iterate_items():
                # Extract text from TextItem instances (paragraphs, headings, etc.)
                if isinstance(item, TextItem):
                    text = item.text.strip() if item.text else ""
                elif isinstance(item, TableItem):
                    # Export table as markdown for downstream chunking
                    try:
                        text = item.export_to_markdown(doc=doc).strip()
                    except Exception:
                        text = str(item).strip()
                else:
                    continue

                if not text:
                    continue

                # Get the label as a string value
                label = item.label.value if hasattr(item.label, "value") else str(item.label)

                # Build metadata
                metadata = {
                    "element_type": label,
                    "page_number": self._get_page_number(item),
                    "heading_level": None,
                    "section_title": current_section,
                }

                # Track section headings
                if self._is_heading(item):
                    heading_level = self._get_heading_level(item)
                    metadata["heading_level"] = heading_level
                    current_section = text
                    current_heading_level = heading_level
                elif current_section:
                    metadata["section_title"] = current_section

                elements.append((text, metadata))

            logger.info(f"Extracted {len(elements)} text elements from document")
            return elements

        except Exception as e:
            logger.error(f"Failed to extract text elements: {e}", exc_info=True)
            raise DocumentLoadError(f"Failed to extract text: {e}")

    def _get_page_number(self, item: DocItem) -> Optional[int]:
        """Get page number from DocItem (1-indexed)."""
        if hasattr(item, "prov") and item.prov:
            for prov in item.prov:
                if hasattr(prov, "page_no"):
                    return int(prov.page_no) + 1  # Convert 0-indexed to 1-indexed

        return None

    def _is_heading(self, item: DocItem) -> bool:
        """Check if item is a heading."""
        if not hasattr(item, "label"):
            return False

        # label is a DocItemLabel enum; convert to string for matching
        label = item.label.value if hasattr(item.label, "value") else str(item.label)
        label_lower = label.lower()
        return "heading" in label_lower or "title" in label_lower

    def _get_heading_level(self, item: DocItem) -> Optional[int]:
        """Extract heading level from item label (e.g., 'section_header' -> 1)."""
        if not self._is_heading(item):
            return None

        label = item.label.value if hasattr(item.label, "value") else str(item.label)
        label_lower = label.lower()

        # Try to parse level from label like "heading-1", "heading_1", "h1"
        for delimiter in ["-", "_", " "]:
            if delimiter in label_lower:
                parts = label_lower.split(delimiter)
                for part in parts:
                    if part.isdigit():
                        return int(part)

        # Default to level 1 if can't determine
        return 1

    @staticmethod
    def get_document_title(doc: DoclingDocument) -> str:
        """
        Extract document title.

        Uses document name or falls back to first heading or filename.
        """
        if hasattr(doc, "name") and doc.name:
            return doc.name

        # Try to get first heading
        try:
            for item, level in doc.iterate_items():
                if isinstance(item, TextItem) and hasattr(item, "label"):
                    label = item.label.value if hasattr(item.label, "value") else str(item.label)
                    label_lower = label.lower()
                    if "title" in label_lower or "heading" in label_lower:
                        text = item.text.strip() if item.text else ""
                        if text:
                            return text
        except Exception:
            pass

        return "Untitled Document"

    @staticmethod
    def get_page_count(doc: DoclingDocument) -> Optional[int]:
        """Get total number of pages in the document."""
        if hasattr(doc, "pages") and doc.pages:
            return len(doc.pages)

        # Try to count from items
        try:
            max_page = 0
            for item, level in doc.iterate_items():
                if hasattr(item, "prov") and item.prov:
                    for prov in item.prov:
                        if hasattr(prov, "page_no"):
                            max_page = max(max_page, int(prov.page_no))
            return max_page + 1 if max_page > 0 else None
        except Exception:
            return None

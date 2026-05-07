"""Text acquisition protocol and error types for DocAI v2."""

from __future__ import annotations

from typing import Protocol

from docai_core.contracts.domain import Document, OCROutput


class UnsupportedDocumentTypeError(Exception):
    """Raised when a document's file type has no registered extractor."""


class TextExtractorProtocol(Protocol):
    """Structural protocol for all text/OCR acquisition sources.

    Every extractor — plain text, embedded PDF, image OCR — must satisfy
    this interface so downstream processing is source-agnostic.
    """

    def extract(self, document: Document) -> OCROutput:
        """Read *document.file_path* and return text evidence as OCROutput.

        Raises:
            FileNotFoundError: if the file does not exist.
            ValueError: if the file cannot be read (invalid format, directory, etc.).
            UnsupportedDocumentTypeError: if the extractor cannot handle this type.
        """
        ...

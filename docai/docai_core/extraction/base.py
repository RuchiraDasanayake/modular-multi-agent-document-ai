"""Extraction runner protocol for DocAI v2.

Defines the interface that KVOnlyExtractionRunner and future HybridExtractionRunner
must satisfy. StubExtractionRunner predates this protocol and uses an older signature
(ocr_text: str instead of ocr_output: OCROutput); it will be migrated in a later task.
"""

from __future__ import annotations

from typing import Protocol

from docai_core.contracts.domain import (
    Document,
    ExtractionSchema,
    ExtractedOutput,
    OCROutput,
    SelectedPolicy,
)


class ExtractionRunnerProtocol(Protocol):
    """Structural protocol for extraction runners.

    Runners satisfying this protocol can be injected into DocumentProcessor
    in place of StubExtractionRunner once that class is migrated.
    """

    def build_ocr_output(self, document: Document) -> OCROutput:
        """Return an OCROutput for the given document.

        Runners that do not own OCR should return an empty OCROutput to satisfy
        the protocol without fabricating content.
        """
        ...

    def build_extracted_output(
        self,
        schema: ExtractionSchema,
        document: Document,
        selected_policy: SelectedPolicy,
        ocr_output: OCROutput,
    ) -> ExtractedOutput:
        """Produce an ExtractedOutput from OCR text and schema definition."""
        ...

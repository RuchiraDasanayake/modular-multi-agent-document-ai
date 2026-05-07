from __future__ import annotations

from typing import Protocol

from docai_core.contracts.domain import ExtractedOutput, ExtractionSchema, OCROutput, ValidationReport


class ValidationRunnerProtocol(Protocol):
    """Structural protocol for validation runners.

    Runners satisfying this protocol can be injected into DocumentProcessor
    in place of StubValidationRunner. Receives both the extracted output and
    the cleaned OCR output so grounding-based validation is possible.
    """

    def build_validation_report(
        self,
        extracted_output: ExtractedOutput,
        ocr_output: OCROutput,
        schema: ExtractionSchema | None = None,
    ) -> ValidationReport:
        """Return a ValidationReport for the given extraction results."""
        ...

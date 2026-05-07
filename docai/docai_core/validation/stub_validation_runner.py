from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import ExtractedOutput, ExtractionSchema, OCROutput, ValidationReport


@dataclass(slots=True)
class StubValidationRunner:
    """Stub validation runner for runtime spine validation only. Do not add real validation logic here."""

    def build_validation_report(
        self,
        extracted_output: ExtractedOutput,
        ocr_output: OCROutput,
        schema: ExtractionSchema | None = None,
    ) -> ValidationReport:
        return ValidationReport(
            document_id=extracted_output.document_id,
            field_issues=[],
            table_issues=[],
            document_issues=[],
            pass_status=True,
            summary="stub validation passed",
        )

from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import (
    Document,
    ExtractionSchema,
    ExtractedOutput,
    FieldOutput,
    OCROutput,
    OCRPage,
    RowOutput,
    SelectedPolicy,
    TableOutput,
)


@dataclass(slots=True)
class StubExtractionRunner:
    """Stub extraction runner for runtime spine validation only. Do not add real OCR or LLM logic here."""

    def build_ocr_output(self, document: Document) -> OCROutput:
        text = f"Fake OCR output for {document.original_filename}"
        return OCROutput(
            document_id=document.document_id,
            engine_id="fake_ocr_v1",
            text=text,
            pages=[OCRPage(page_number=1, text=text)],
            blocks=[],
            tables_detected=[],
            confidence=0.9,
        )

    def build_extracted_output(
        self,
        schema: ExtractionSchema,
        document: Document,
        selected_policy: SelectedPolicy,
        ocr_output: OCROutput,
    ) -> ExtractedOutput:
        fields: list[FieldOutput] = []
        for field in schema.fields:
            fake_value = f"fake_{field.name}"
            fields.append(
                FieldOutput(
                    field_name=field.name,
                    value=fake_value,
                    normalized_value=fake_value,
                    confidence=0.90,
                    evidence_text=ocr_output.text,
                    evidence_location="page:1",
                    extraction_method="fake_extractor",
                    validation_status="valid",
                    issues=[],
                )
            )

        tables: list[TableOutput] = []
        for table in schema.tables:
            row_values = {column.name: f"fake_{column.name}" for column in table.columns}
            row = RowOutput(
                row_index=0,
                columns=row_values,
                evidence_text=ocr_output.text,
                evidence_location="page:1",
                confidence=0.90,
                validation_status="valid",
                issues=[],
            )
            tables.append(
                TableOutput(
                    table_name=table.name,
                    rows=[row],
                    confidence=0.90,
                    validation_status="valid",
                    issues=[],
                )
            )

        return ExtractedOutput(
            document_id=document.document_id,
            schema_id=schema.schema_id,
            policy_id=selected_policy.policy_id,
            fields=fields,
            tables=tables,
        )

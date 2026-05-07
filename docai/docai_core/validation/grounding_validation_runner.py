from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from docai_core.contracts.domain import ExtractedOutput, ExtractionSchema, OCROutput, ValidationReport
from docai_core.validation.grounding_validator import GroundingValidator


@dataclass(slots=True)
class GroundingValidationRunner:
    """Validation runner that derives ValidationReport from GroundingValidator results.

    Uses source text grounding to determine pass/fail and produces structured
    field_issues. Does not call OCR, extraction, or model code.
    """

    validator: GroundingValidator = dc_field(default_factory=GroundingValidator)

    def build_validation_report(
        self,
        extracted_output: ExtractedOutput,
        ocr_output: OCROutput,
        schema: ExtractionSchema | None = None,
    ) -> ValidationReport:
        result = self.validator.validate(extracted_output, ocr_output.text)

        field_issues = [
            f"{f.field_name}: not_found_in_source"
            for f in result.fields
            if f.reason == "not_found_in_source"
        ]
        missing_issues = [
            f"{f.field_name}: missing_value"
            for f in result.fields
            if f.reason == "missing_value"
        ]
        pass_status = result.ungrounded_count == 0
        summary = (
            f"{result.grounded_count} grounded, "
            f"{result.ungrounded_count} ungrounded, "
            f"{result.missing_count} missing"
        )

        # Check required fields if schema is provided
        required_field_issues = []
        if schema is not None:
            extracted_field_map = {f.field_name: f for f in extracted_output.fields}
            for schema_field in schema.fields:
                if schema_field.required:
                    extracted = extracted_field_map.get(schema_field.name)
                    has_value = extracted is not None and extracted.value and str(extracted.value).strip().lower() not in {"", "n/a", "none"}
                    if not has_value:
                        required_field_issues.append(f"{schema_field.name}: missing_required_field")
                        pass_status = False

        return ValidationReport(
            document_id=extracted_output.document_id,
            field_issues=field_issues + missing_issues + required_field_issues,
            table_issues=[],
            document_issues=[],
            pass_status=pass_status,
            summary=summary,
        )

"""Integration tests: ModelCenteredExtractionRunner → GroundingValidationRunner.

Proves that model confidence does not bypass grounding validation.
Fake model plugin — no real Qwen endpoint.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    OCROutput,
    SelectedPolicy,
)
from docai_core.extraction.model_centered_extraction_runner import ModelCenteredExtractionRunner
from docai_core.extraction.qwen_extraction_step import QwenExtractionStep
from docai_core.plugins.models.base import ModelRequest, ModelResponse
from docai_core.validation.grounding_validation_runner import GroundingValidationRunner


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

@dataclass
class _FakePlugin:
    plugin_id: str = "fake"
    provider_name: str = "fake"
    model_name: str = "fake-model"
    response_text: str = "{}"
    success: bool = True

    def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text=self.response_text,
            model_name=self.model_name,
            is_stub=False,
            success=self.success,
        )


def _step_returning(fields: dict[str, tuple[str, float]]) -> QwenExtractionStep:
    entities = [{"key": k, "value": v, "confidence": c} for k, (v, c) in fields.items()]
    payload = json.dumps({"entities": entities})
    return QwenExtractionStep(model_plugin=_FakePlugin(response_text=payload))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _schema() -> ExtractionSchema:
    return ExtractionSchema(
        schema_id="schema-invoice",
        project_id="proj-1",
        name="Invoice Schema",
        description=None,
        version="v1",
        fields=[
            Field(field_id="f1", name="invoice_number", type="str", description=None),
            Field(field_id="f2", name="total_amount",   type="str", description=None),
        ],
    )


def _policy() -> SelectedPolicy:
    return SelectedPolicy(
        policy_id="policy-1",
        policy_family="default",
        policy_version="v1",
        selected_by="test",
    )


def _document() -> Document:
    now = datetime.now(timezone.utc)
    return Document(
        document_id="doc-1",
        job_id="job-1",
        original_filename="invoice.txt",
        file_path="/tmp/invoice.txt",
        status="processing",
        uploaded_at=now,
        profile=DocumentProfile(document_id="doc-1"),
    )


def _ocr(text: str) -> OCROutput:
    return OCROutput(document_id="doc-1", engine_id="test", text=text)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_grounding_passes_for_model_value_present_in_source() -> None:
    source = "Invoice Number: INV-001\nTotal Amount: $100.00"
    ocr = _ocr(source)

    step = _step_returning({"invoice_number": ("INV-001", 0.95)})
    runner = ModelCenteredExtractionRunner(model_step=step)
    extracted = runner.build_extracted_output(_schema(), _document(), _policy(), ocr)

    report = GroundingValidationRunner().build_validation_report(extracted, ocr)

    assert report.pass_status is True, f"Expected pass; issues: {report.field_issues}"
    assert "grounded" in report.summary


def test_grounding_flags_model_hallucinated_value() -> None:
    """High model confidence must not bypass grounding.

    The model returns INV-999 with 0.99 confidence; the source only contains INV-001.
    The runner will select INV-999 (higher confidence than KV's INV-001).
    GroundingValidationRunner must then flag it as not_found_in_source.
    """
    source = "Invoice Number: INV-001\nTotal Amount: $100.00"
    ocr = _ocr(source)

    step = _step_returning({"invoice_number": ("INV-999", 0.99)})
    runner = ModelCenteredExtractionRunner(model_step=step)
    extracted = runner.build_extracted_output(_schema(), _document(), _policy(), ocr)

    report = GroundingValidationRunner().build_validation_report(extracted, ocr)

    assert report.pass_status is False
    assert any("invoice_number" in issue and "not_found_in_source" in issue
               for issue in report.field_issues), (
        f"Expected invoice_number grounding failure; got: {report.field_issues}"
    )


def test_grounding_passes_after_kv_fallback_fills_model_gap() -> None:
    """When model returns nothing, KV fills the field; grounding should pass."""
    source = "Invoice Number: INV-001\nTotal Amount: $100.00"
    ocr = _ocr(source)

    # Model returns nothing useful
    step = _step_returning({})
    runner = ModelCenteredExtractionRunner(model_step=step)
    extracted = runner.build_extracted_output(_schema(), _document(), _policy(), ocr)

    report = GroundingValidationRunner().build_validation_report(extracted, ocr)

    assert report.pass_status is True, f"Expected pass; issues: {report.field_issues}"


def test_grounding_detects_hallucinated_hybrid_when_only_model_lies() -> None:
    """If model wins a conflicting value and it isn't in source, grounding catches it."""
    source = "Invoice Number: INV-001"
    ocr = _ocr(source)

    # Only one field in schema for simplicity
    schema = ExtractionSchema(
        schema_id="schema-test",
        project_id="proj-1",
        name="Test",
        description=None,
        version="v1",
        fields=[Field(field_id="f1", name="invoice_number", type="str", description=None)],
    )

    step = _step_returning({"invoice_number": ("HALLUCINATED-VAL", 0.97)})
    runner = ModelCenteredExtractionRunner(model_step=step)
    extracted = runner.build_extracted_output(schema, _document(), _policy(), ocr)

    report = GroundingValidationRunner().build_validation_report(extracted, ocr)

    assert report.pass_status is False
    assert any("invoice_number" in i for i in report.field_issues)

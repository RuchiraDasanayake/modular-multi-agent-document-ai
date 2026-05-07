"""Unit tests: ModelCenteredExtractionRunner.

All model calls use a fake QwenExtractionStep. No real Qwen endpoint.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone

from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    ExtractionSchema,
    ExtractedOutput,
    Field,
    OCROutput,
    SelectedPolicy,
)
from docai_core.extraction.model_centered_extraction_runner import ModelCenteredExtractionRunner
from docai_core.extraction.qwen_extraction_step import QwenExtractionStep
from docai_core.plugins.models.base import ModelRequest, ModelResponse


# ---------------------------------------------------------------------------
# Fake model plugin and step helpers
# ---------------------------------------------------------------------------

@dataclass
class _FakeModelPlugin:
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
    """Return a QwenExtractionStep whose model returns the given {field: (value, conf)}."""
    entities = [
        {"key": k, "value": v, "confidence": c}
        for k, (v, c) in fields.items()
    ]
    payload = json.dumps({"entities": entities})
    plugin = _FakeModelPlugin(response_text=payload)
    return QwenExtractionStep(model_plugin=plugin)


def _step_empty() -> QwenExtractionStep:
    return QwenExtractionStep(model_plugin=_FakeModelPlugin(response_text="{}"))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_INVOICE_TEXT = (
    "Invoice Number: INV-001\n"
    "Invoice Date: 2026-03-15\n"
    "Total Amount: $100.00\n"
    "Status: Paid\n"
)


def _schema() -> ExtractionSchema:
    return ExtractionSchema(
        schema_id="schema-invoice",
        project_id="proj-1",
        name="Invoice Schema",
        description=None,
        version="v1",
        fields=[
            Field(field_id="f1", name="invoice_number", type="str", description=None),
            Field(field_id="f2", name="invoice_date",   type="str", description=None),
            Field(field_id="f3", name="total_amount",   type="str", description=None),
            Field(field_id="f4", name="status",         type="str", description=None),
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


def _ocr(text: str = _INVOICE_TEXT) -> OCROutput:
    return OCROutput(document_id="doc-1", engine_id="test", text=text)


def _runner(step: QwenExtractionStep) -> ModelCenteredExtractionRunner:
    return ModelCenteredExtractionRunner(model_step=step)


def _field_map(result: ExtractedOutput) -> dict[str, object]:
    return {f.field_name: f for f in result.fields}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_model_centered_runner_uses_model_candidate_when_kv_missing() -> None:
    ocr = _ocr("No structured date info here\nTotal Amount: $100.00\n")
    step = _step_returning({"invoice_date": ("2026-03-15", 0.88)})
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), ocr)

    fm = _field_map(result)
    date_fo = fm["invoice_date"]
    assert date_fo.value == "2026-03-15"
    assert date_fo.extraction_method == "model_extraction"


def test_model_centered_runner_uses_kv_when_model_missing() -> None:
    step = _step_empty()
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    fm = _field_map(result)
    total = fm["total_amount"]
    assert str(total.value) == "$100.00"
    assert total.extraction_method == "generic_kv"


def test_model_centered_runner_marks_hybrid_when_values_agree() -> None:
    step = _step_returning({"invoice_number": ("INV-001", 0.82)})
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    fm = _field_map(result)
    inv = fm["invoice_number"]
    assert inv.extraction_method == "hybrid_kv_model"
    assert inv.confidence is not None
    assert inv.confidence >= 0.82


def test_model_centered_runner_prefers_higher_confidence_when_values_conflict_model_wins() -> None:
    step = _step_returning({"invoice_number": ("INV-999", 0.95)})
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    fm = _field_map(result)
    inv = fm["invoice_number"]
    assert inv.value == "INV-999"
    assert inv.extraction_method == "model_extraction"


def test_model_centered_runner_prefers_kv_when_kv_confidence_higher() -> None:
    # 0.30 is exactly at the floor — model IS accepted, but KV wins on confidence.
    step = _step_returning({"invoice_number": ("INV-999", 0.30)})
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    fm = _field_map(result)
    inv = fm["invoice_number"]
    assert inv.value == "INV-001"
    assert inv.extraction_method == "generic_kv"


def test_model_na_does_not_override_valid_kv() -> None:
    step = _step_returning({"total_amount": ("N/A", 0.99)})
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    fm = _field_map(result)
    total = fm["total_amount"]
    assert str(total.value) == "$100.00"
    assert total.extraction_method == "generic_kv"


def test_model_missing_markers_treated_as_not_found() -> None:
    for marker in ("n/a", "N/A", "none", "None", "", "null", "unknown", "-"):
        step = _step_returning({"total_amount": (marker, 0.99)})
        result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())
        total = {f.field_name: f for f in result.fields}["total_amount"]
        assert str(total.value) == "$100.00", f"marker {marker!r} should not override KV"


def test_low_confidence_model_candidate_is_ignored_kv_wins() -> None:
    # Confidence 0.05 is below the 0.30 floor — model candidate is treated as not found.
    # KV has a valid value, so KV should win.
    step = _step_returning({"invoice_number": ("INV-GHOST", 0.05)})
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    fm = _field_map(result)
    inv = fm["invoice_number"]
    assert inv.value == "INV-001"
    assert inv.extraction_method == "generic_kv"


def test_low_confidence_model_candidate_is_ignored_field_missing_when_no_kv() -> None:
    # Confidence 0.05 is below floor; no KV line for invoice_date in this text.
    ocr = _ocr("No structured date info here\n")
    step = _step_returning({"invoice_date": ("2026-03-15", 0.05)})
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), ocr)

    fm = _field_map(result)
    date_fo = fm["invoice_date"]
    assert date_fo.value == "N/A"
    assert date_fo.extraction_method == "not_found"
    assert date_fo.validation_status == "missing"


def test_invalid_model_value_label_leak_is_ignored() -> None:
    # Value ending in ":" is a label-leakage artifact — must be ignored.
    # KV has valid invoice_number from text.
    step = _step_returning({"invoice_number": ("Invoice Number:", 0.90)})
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    fm = _field_map(result)
    inv = fm["invoice_number"]
    assert inv.value == "INV-001"
    assert inv.extraction_method == "generic_kv"


def test_invalid_model_value_too_short_is_ignored() -> None:
    # Single-character value is invalid — less than 2 chars.
    step = _step_returning({"invoice_number": ("X", 0.90)})
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    fm = _field_map(result)
    inv = fm["invoice_number"]
    assert inv.value == "INV-001"
    assert inv.extraction_method == "generic_kv"


def test_invalid_model_value_too_long_is_ignored() -> None:
    # Value over 180 chars is invalid.
    long_val = "X" * 181
    step = _step_returning({"invoice_number": (long_val, 0.90)})
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    fm = _field_map(result)
    inv = fm["invoice_number"]
    assert inv.value == "INV-001"
    assert inv.extraction_method == "generic_kv"


def test_missing_fields_are_marked_missing() -> None:
    ocr = _ocr("Invoice Number: INV-001\nTotal Amount: $100.00\n")
    step = _step_empty()
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), ocr)

    fm = _field_map(result)
    status = fm["status"]
    assert status.value == "N/A"
    assert status.confidence == 0.0
    assert status.extraction_method == "not_found"
    assert status.validation_status == "missing"


def test_schema_field_order_preserved() -> None:
    step = _step_empty()
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    names = [f.field_name for f in result.fields]
    assert names == ["invoice_number", "invoice_date", "total_amount", "status"]


def test_found_fields_have_needs_review_status() -> None:
    step = _step_returning({"invoice_number": ("INV-001", 0.9)})
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    for fo in result.fields:
        if fo.extraction_method != "not_found":
            assert fo.validation_status == "needs_review", fo.field_name


def test_build_ocr_output_delegates_to_kv_runner() -> None:
    runner = _runner(_step_empty())
    doc = _document()
    ocr_out = runner.build_ocr_output(doc)

    assert ocr_out.document_id == doc.document_id
    assert isinstance(ocr_out.text, str)


def test_extracted_output_has_correct_ids() -> None:
    step = _step_empty()
    result = _runner(step).build_extracted_output(_schema(), _document(), _policy(), _ocr())

    assert result.document_id == "doc-1"
    assert result.schema_id == "schema-invoice"
    assert result.policy_id == "policy-1"
    assert result.tables == []


def test_public_export_available() -> None:
    from docai_core.extraction import ModelCenteredExtractionRunner
    assert ModelCenteredExtractionRunner is not None

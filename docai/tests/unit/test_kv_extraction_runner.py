from __future__ import annotations

from datetime import datetime

from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    OCROutput,
    OCRPage,
    SelectedPolicy,
)
from docai_core.extraction.kv_extraction_runner import KVOnlyExtractionRunner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _doc(doc_id: str = "doc-1") -> Document:
    return Document(
        document_id=doc_id,
        job_id="job-1",
        original_filename="invoice.pdf",
        file_path="/tmp/invoice.pdf",
        status="processing",
        uploaded_at=datetime(2026, 3, 15),
        profile=DocumentProfile(document_id=doc_id),
    )


def _schema(include_descriptions: bool = False) -> ExtractionSchema:
    return ExtractionSchema(
        schema_id="schema-1",
        project_id="proj-1",
        name="Invoice Schema",
        description=None,
        version="v1",
        fields=[
            Field(
                field_id="f1", name="invoice_number", type="str",
                description="invoice number" if include_descriptions else None,
            ),
            Field(field_id="f2", name="invoice_date", type="str", description=None),
            Field(
                field_id="f3", name="total_amount", type="str",
                description="total amount due" if include_descriptions else None,
            ),
            Field(field_id="f4", name="status", type="str", description=None),
        ],
    )


def _policy(policy_id: str = "policy-1") -> SelectedPolicy:
    return SelectedPolicy(
        policy_id=policy_id,
        policy_family="default",
        policy_version="v1",
        selected_by="test",
    )


def _ocr(text: str, doc_id: str = "doc-1") -> OCROutput:
    return OCROutput(
        document_id=doc_id,
        engine_id="test_ocr",
        text=text,
        pages=[OCRPage(page_number=1, text=text)],
        blocks=[],
        tables_detected=[],
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_kv_only_runner_builds_empty_ocr_output_for_protocol_compatibility() -> None:
    runner = KVOnlyExtractionRunner()
    result = runner.build_ocr_output(_doc())
    assert result.document_id == "doc-1"
    assert result.text == ""
    assert result.confidence == 0.0
    assert result.pages == []


def test_kv_only_runner_extracts_schema_fields_from_ocr_text() -> None:
    runner = KVOnlyExtractionRunner()
    text = (
        "Invoice Number: INV-001\n"
        "Invoice Date: 2026-03-15\n"
        "Total Amount: $100.00\n"
        "Status: Paid\n"
    )
    result = runner.build_extracted_output(_schema(), _doc(), _policy(), _ocr(text))
    field_map = {f.field_name: f.value for f in result.fields}
    assert field_map["invoice_number"] == "INV-001"
    assert field_map["invoice_date"] == "2026-03-15"
    assert field_map["total_amount"] == "$100.00"
    assert field_map["status"] == "Paid"


def test_kv_only_runner_marks_missing_fields() -> None:
    runner = KVOnlyExtractionRunner()
    result = runner.build_extracted_output(
        _schema(), _doc(), _policy(), _ocr("Invoice Number: INV-001")
    )
    missing = {f.field_name: f for f in result.fields if f.field_name != "invoice_number"}
    for field_name, f in missing.items():
        assert f.value == "N/A", f"{field_name} should be N/A"
        assert f.confidence == 0.0
        assert f.extraction_method == "not_found"
        assert f.validation_status == "missing"


def test_kv_only_runner_canonicalizes_human_labels_to_schema_fields() -> None:
    # "Invoice Number" normalizes to "invoice_number" (exact match).
    # "Total Due" normalizes to "total_due", then canonicalizes to "total_amount"
    # via field description "total amount due" (containment score ≥ 0.62).
    runner = KVOnlyExtractionRunner()
    text = "Invoice Number: INV-001\nTotal Due: $100.00\n"
    result = runner.build_extracted_output(
        _schema(include_descriptions=True), _doc(), _policy(), _ocr(text)
    )
    field_map = {f.field_name: f for f in result.fields}
    assert field_map["invoice_number"].value == "INV-001"
    assert field_map["total_amount"].value == "$100.00"


def test_kv_only_runner_does_not_extract_tables() -> None:
    runner = KVOnlyExtractionRunner()
    result = runner.build_extracted_output(
        _schema(), _doc(), _policy(), _ocr("Invoice Number: INV-001")
    )
    assert result.tables == []


def test_kv_only_runner_uses_selected_policy_id() -> None:
    runner = KVOnlyExtractionRunner()
    result = runner.build_extracted_output(
        _schema(), _doc(), _policy("policy-xyz"), _ocr("Invoice Number: INV-001")
    )
    assert result.policy_id == "policy-xyz"


def test_kv_only_runner_handles_empty_ocr_text() -> None:
    runner = KVOnlyExtractionRunner()
    result = runner.build_extracted_output(_schema(), _doc(), _policy(), _ocr(""))
    assert len(result.fields) == len(_schema().fields)
    for f in result.fields:
        assert f.value == "N/A"
        assert f.validation_status == "missing"


def test_kv_only_runner_preserves_generic_kv_extraction_method() -> None:
    runner = KVOnlyExtractionRunner()
    text = "Invoice Number: INV-001\nInvoice Date: 2026-03-15\n"
    result = runner.build_extracted_output(_schema(), _doc(), _policy(), _ocr(text))
    found = [f for f in result.fields if f.value != "N/A"]
    assert len(found) >= 2
    assert all(f.extraction_method == "generic_kv" for f in found)


def test_public_exports_available() -> None:
    from docai_core.extraction import ExtractionRunnerProtocol, KVOnlyExtractionRunner

    assert ExtractionRunnerProtocol is not None
    assert KVOnlyExtractionRunner is not None
    runner = KVOnlyExtractionRunner()
    assert hasattr(runner, "build_ocr_output")
    assert hasattr(runner, "build_extracted_output")
    # Smoke round-trip
    result = runner.build_extracted_output(_schema(), _doc(), _policy(), _ocr(""))
    assert result.document_id == "doc-1"

"""Integration test: OCRPostProcessor → KVOnlyExtractionRunner composition.

Proves that raw OCR text can be cleaned and turned into a real ExtractedOutput
without stubs, model calls, or runtime orchestration.
"""

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
from docai_core.extraction.ocr_postprocessor import OCRPostProcessor


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _document() -> Document:
    return Document(
        document_id="doc-pipeline-1",
        job_id="job-1",
        original_filename="invoice.pdf",
        file_path="/tmp/invoice.pdf",
        status="processing",
        uploaded_at=datetime(2026, 3, 15),
        profile=DocumentProfile(document_id="doc-pipeline-1"),
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
        policy_id="policy-kv",
        policy_family="kv_only",
        policy_version="v1",
        selected_by="test",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_raw_ocr_text_to_extracted_output_pipeline() -> None:
    """Full composition: OCRPostProcessor → KVOnlyExtractionRunner.

    The raw OCROutput contains:
    - a stray control character (\x0c form-feed) between lines
    - extra consecutive blank lines
    - otherwise valid invoice KV pairs

    OCRPostProcessor should remove the control character and collapse blank lines.
    KVOnlyExtractionRunner should extract all four schema fields.
    """
    raw_page_text = (
        "Invoice Number: INV-001\n"
        "Invoice Date: 2026-03-15\n"
        "\x0c\n"                        # control character — postprocessor removes this
        "\n\n"                           # extra blank lines — collapsed to one
        "Total Amount: $100.00\n"
        "Status: Paid\n"
    )
    raw_ocr = OCROutput(
        document_id="doc-pipeline-1",
        engine_id="native_pdf_stub",
        text=raw_page_text,
        pages=[OCRPage(page_number=1, text=raw_page_text)],
        blocks=[],
        tables_detected=[],
        confidence=0.95,
    )

    # Step 1 — clean
    cleaned_ocr = OCRPostProcessor().process(raw_ocr)

    # Step 2 — extract
    extracted = KVOnlyExtractionRunner().build_extracted_output(
        schema=_schema(),
        document=_document(),
        selected_policy=_policy(),
        ocr_output=cleaned_ocr,
    )

    # Postprocessor assertions
    assert "\x0c" not in cleaned_ocr.text, "form-feed not stripped"
    assert "\n\n\n" not in cleaned_ocr.text, "extra blank lines not collapsed"

    # ExtractedOutput identity
    assert extracted.document_id == "doc-pipeline-1"
    assert extracted.schema_id == "schema-invoice"
    assert extracted.policy_id == "policy-kv"
    assert extracted.tables == []

    # Field values
    field_map = {f.field_name: f for f in extracted.fields}
    assert field_map["invoice_number"].value == "INV-001"
    assert field_map["invoice_date"].value == "2026-03-15"
    assert field_map["total_amount"].value == "$100.00"
    assert field_map["status"].value == "Paid"

    # Source and status
    found = [f for f in extracted.fields if f.value != "N/A"]
    assert all(f.extraction_method == "generic_kv" for f in found)
    assert all(f.validation_status == "needs_review" for f in found)


def test_pipeline_marks_missing_fields_when_text_lacks_values() -> None:
    """Fields absent from OCR text are marked missing after the full pipeline."""
    raw_ocr = OCROutput(
        document_id="doc-pipeline-1",
        engine_id="native_pdf_stub",
        text="Invoice Number: INV-002\n",
        pages=[OCRPage(page_number=1, text="Invoice Number: INV-002\n")],
        blocks=[],
        tables_detected=[],
        confidence=0.9,
    )

    cleaned_ocr = OCRPostProcessor().process(raw_ocr)
    extracted = KVOnlyExtractionRunner().build_extracted_output(
        schema=_schema(),
        document=_document(),
        selected_policy=_policy(),
        ocr_output=cleaned_ocr,
    )

    field_map = {f.field_name: f for f in extracted.fields}

    assert field_map["invoice_number"].value == "INV-002"
    assert field_map["invoice_number"].extraction_method == "generic_kv"

    for name in ("invoice_date", "total_amount", "status"):
        f = field_map[name]
        assert f.value == "N/A", f"{name} should be N/A"
        assert f.confidence == 0.0
        assert f.extraction_method == "not_found"
        assert f.validation_status == "missing"

"""Integration tests: GroundingValidator after real TXT acquisition + KV extraction.

Flow:
  TXT file → TextAcquisitionRouter → OCRPostProcessor → KVOnlyExtractionRunner
  → GroundingValidator

Does not use RuntimeOrchestrator, DocumentProcessor, or any model calls.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import replace
from datetime import datetime, timezone

from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    ExtractionSchema,
    ExtractedOutput,
    Field,
    FieldOutput,
    SelectedPolicy,
)
from docai_core.extraction.kv_extraction_runner import KVOnlyExtractionRunner
from docai_core.extraction.ocr_postprocessor import OCRPostProcessor
from docai_core.text_acquisition.router import TextAcquisitionRouter
from docai_core.validation import GroundingValidator

_INVOICE_TEXT = (
    "Invoice Number: INV-001\n"
    "Invoice Date: 2026-03-15\n"
    "Total Amount: $100.00\n"
    "Status: Paid\n"
)

_SCHEMA = ExtractionSchema(
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

_POLICY = SelectedPolicy(
    policy_id="test_policy_v1",
    policy_family="invoice_extraction",
    policy_version="v1",
    selected_by="test",
)


def _run_pipeline(txt_path: str) -> tuple[str, ExtractedOutput]:
    """Run TXT → OCR → postprocess → KV extraction. Returns (source_text, extracted_output)."""
    document = Document(
        document_id="doc-1",
        job_id="job-1",
        original_filename=os.path.basename(txt_path),
        file_path=txt_path,
        status="processing",
        uploaded_at=datetime.now(timezone.utc),
        profile=DocumentProfile(document_id="doc-1"),
    )

    raw_ocr = TextAcquisitionRouter().extract(document)
    clean_ocr = OCRPostProcessor().process(raw_ocr)
    extracted = KVOnlyExtractionRunner().build_extracted_output(
        _SCHEMA, document, _POLICY, clean_ocr
    )
    return clean_ocr.text, extracted


def test_grounding_validator_marks_kv_extracted_fields_as_grounded(tmp_path) -> None:
    fd, txt_path = tempfile.mkstemp(suffix=".txt", dir=tmp_path)
    os.write(fd, _INVOICE_TEXT.encode("utf-8"))
    os.close(fd)

    source_text, extracted = _run_pipeline(txt_path)
    result = GroundingValidator().validate(extracted, source_text)

    found_fields = [f for f in result.fields if f.reason != "missing_value"]
    assert len(found_fields) >= 4, f"Expected >=4 found fields, got {len(found_fields)}"
    assert result.ungrounded_count == 0, (
        f"Expected 0 ungrounded, got {result.ungrounded_count}: "
        + str([f for f in result.fields if not f.is_grounded and f.reason != "missing_value"])
    )
    assert result.grounded_count >= 4

    field_map = {f.field_name: f for f in result.fields}
    assert field_map["invoice_number"].is_grounded is True
    assert field_map["total_amount"].is_grounded is True


def test_grounding_validator_flags_hallucinated_field(tmp_path) -> None:
    fd, txt_path = tempfile.mkstemp(suffix=".txt", dir=tmp_path)
    os.write(fd, _INVOICE_TEXT.encode("utf-8"))
    os.close(fd)

    source_text, extracted = _run_pipeline(txt_path)

    invoice_field = next(
        f for f in extracted.fields if f.field_name == "invoice_number"
    )
    hallucinated_field = replace(invoice_field, value="INV-999")
    modified_fields = [
        hallucinated_field if f.field_name == "invoice_number" else f
        for f in extracted.fields
    ]
    modified_extracted = ExtractedOutput(
        document_id=extracted.document_id,
        schema_id=extracted.schema_id,
        policy_id=extracted.policy_id,
        fields=modified_fields,
        tables=extracted.tables,
    )

    result = GroundingValidator().validate(modified_extracted, source_text)

    inv_result = next(f for f in result.fields if f.field_name == "invoice_number")
    assert inv_result.is_grounded is False
    assert inv_result.reason == "not_found_in_source"

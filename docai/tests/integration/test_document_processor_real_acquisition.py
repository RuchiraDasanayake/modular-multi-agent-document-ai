"""Integration tests: DocumentProcessor with real text acquisition path.

Proves that injecting TextAcquisitionRouter + OCRPostProcessor + KVOnlyExtractionRunner
enables real file processing through DocumentProcessor without changing the default
stub behaviour or touching RuntimeOrchestrator.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from docai_core.contracts.domain import (
    AvailableTool,
    AvailableTools,
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
)
from docai_core.extraction.kv_extraction_runner import KVOnlyExtractionRunner
from docai_core.extraction.ocr_postprocessor import OCRPostProcessor
from docai_core.extraction.stub_extraction_runner import StubExtractionRunner
from docai_core.orchestration.document_processor import DocumentProcessor
from docai_core.planning.run_plan_builder import RunPlanBuilder
from docai_core.policies.assigner import StrategyAssigner
from docai_core.policies.registry import PolicyRegistry
from docai_core.recovery.stub_recovery_runner import StubRecoveryRunner
from docai_core.text_acquisition.base import UnsupportedDocumentTypeError
from docai_core.text_acquisition.image_ocr_extractor import ImageOCRExtractor
from docai_core.text_acquisition.router import TextAcquisitionRouter
from docai_core.validation.grounding_validation_runner import GroundingValidationRunner
from docai_core.validation.stub_validation_runner import StubValidationRunner

_POLICY_DIR = Path(__file__).resolve().parents[2] / "configs" / "policies"
_STUB_NOTE = "test stub note"
_INVOICE_TEXT = (
    "Invoice Number: INV-001\n"
    "Invoice Date: 2026-03-15\n"
    "Total Amount: $100.00\n"
    "Status: Paid\n"
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _available_tools() -> AvailableTools:
    tool = AvailableTool(
        tool_id="stub_tool",
        tool_type="ocr_parser_model",
        capabilities=["text_output", "bbox_output", "table_detection", "json_output"],
        enabled=True,
    )
    return AvailableTools(
        available_ocr_engines=[tool],
        available_parsers=[tool],
        available_models=[tool],
    )


def _schema() -> ExtractionSchema:
    now = datetime.now(timezone.utc)
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


def _document(file_path: str, doc_id: str = "doc-1") -> Document:
    return Document(
        document_id=doc_id,
        job_id="job-1",
        original_filename=os.path.basename(file_path),
        file_path=file_path,
        status="processing",
        uploaded_at=datetime.now(timezone.utc),
        profile=DocumentProfile(document_id=doc_id),
    )


def _make_processor(**kwargs) -> DocumentProcessor:
    return DocumentProcessor(
        strategy_assigner=StrategyAssigner(registry=PolicyRegistry(_POLICY_DIR)),
        run_plan_builder=RunPlanBuilder(),
        stub_extraction_runner=StubExtractionRunner(),
        stub_validation_runner=StubValidationRunner(),
        stub_recovery_runner=StubRecoveryRunner(),
        stub_note=_STUB_NOTE,
        **kwargs,
    )


def _make_pdf_bytes(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = b"BT\n/F1 12 Tf\n50 750 Td\n(" + escaped.encode() + b") Tj\nET\n"
    font_obj_id = 5

    def obj(n: int, content: bytes) -> bytes:
        return b"%d 0 obj\n" % n + content + b"\nendobj\n"

    objects = [
        obj(1, b"<<\n/Type /Catalog\n/Pages 2 0 R\n>>"),
        obj(2, b"<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>"),
        obj(3, b"<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n"
               b"/Contents 4 0 R\n/Resources <<\n/Font <<\n/F1 5 0 R\n>> >> >>"),
        obj(4, b"<<\n/Length %d\n>>\nstream\n" % len(stream) + stream + b"endstream"),
        obj(font_obj_id, b"<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>"),
    ]
    body = b"%PDF-1.4\n"
    offsets: list[int] = []
    for o in objects:
        offsets.append(len(body))
        body += o
    xref_offset = len(body)
    xref = b"xref\n0 %d\n" % (len(objects) + 1)
    xref += b"0000000000 65535 f \n"
    for off in offsets:
        xref += b"%010d 00000 n \n" % off
    body += xref
    body += (
        b"trailer\n<<\n/Size %d\n/Root 1 0 R\n>>\n" % (len(objects) + 1) +
        b"startxref\n%d\n%%%%EOF\n" % xref_offset
    )
    return body


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_document_processor_with_txt_file() -> None:
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.write(fd, _INVOICE_TEXT.encode("utf-8"))
    os.close(fd)
    try:
        processor = _make_processor(
            text_acquisition_router=TextAcquisitionRouter(),
            ocr_postprocessor=OCRPostProcessor(),
            extraction_runner=KVOnlyExtractionRunner(),
        )
        result = processor.process_document(_schema(), _document(path), _available_tools())

        assert result.ocr_output.engine_id == "plain_text_extractor"
        field_map = {f.field_name: f.value for f in result.extracted_output.fields}
        assert field_map["invoice_number"] == "INV-001"
        assert field_map["invoice_date"] == "2026-03-15"
        assert field_map["total_amount"] == "$100.00"
        assert field_map["status"] == "Paid"
        assert not any(str(v).startswith("fake_") for v in field_map.values())
    finally:
        os.unlink(path)


def test_document_processor_with_pdf_file() -> None:
    page_text = "Invoice Number: INV-001  Invoice Date: 2026-03-15  Total Amount: $100.00  Status: Paid"
    data = _make_pdf_bytes(page_text)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.write(fd, data)
    os.close(fd)
    try:
        processor = _make_processor(
            text_acquisition_router=TextAcquisitionRouter(),
            ocr_postprocessor=OCRPostProcessor(),
            extraction_runner=KVOnlyExtractionRunner(),
        )
        result = processor.process_document(_schema(), _document(path), _available_tools())

        assert result.ocr_output.engine_id == "native_pdf_text_extractor"
        field_map = {f.field_name: f.value for f in result.extracted_output.fields}
        assert field_map["invoice_number"] == "INV-001"
        assert field_map["total_amount"] == "$100.00"
        assert not any(str(v).startswith("fake_") for v in field_map.values())
    finally:
        os.unlink(path)


def test_document_processor_with_image_fake_ocr() -> None:
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        image_extractor = ImageOCRExtractor(ocr_callable=lambda _: _INVOICE_TEXT)
        router = TextAcquisitionRouter(image_ocr_extractor=image_extractor)
        processor = _make_processor(
            text_acquisition_router=router,
            ocr_postprocessor=OCRPostProcessor(),
            extraction_runner=KVOnlyExtractionRunner(),
        )
        result = processor.process_document(_schema(), _document(path), _available_tools())

        assert result.ocr_output.engine_id == "tesseract_image_ocr"
        field_map = {f.field_name: f.value for f in result.extracted_output.fields}
        assert field_map["invoice_number"] == "INV-001"
        assert field_map["status"] == "Paid"
        assert not any(str(v).startswith("fake_") for v in field_map.values())
    finally:
        os.unlink(path)


def test_document_processor_unsupported_extension_raises() -> None:
    processor = _make_processor(
        text_acquisition_router=TextAcquisitionRouter(),
    )
    with pytest.raises(UnsupportedDocumentTypeError):
        processor.process_document(
            _schema(),
            _document("/tmp/report.xyz"),
            _available_tools(),
        )


def test_document_processor_stub_path_unchanged() -> None:
    processor = _make_processor()  # no optional fields
    doc = _document("invoice_001.pdf")
    result = processor.process_document(_schema(), doc, _available_tools())

    assert "Fake OCR" in result.ocr_output.text
    assert all(
        str(f.value).startswith("fake_") for f in result.extracted_output.fields
    )


def test_real_acquisition_with_grounding_validation(tmp_path) -> None:
    import tempfile as _tempfile
    fd, path = _tempfile.mkstemp(suffix=".txt", dir=str(tmp_path))
    os.write(fd, _INVOICE_TEXT.encode("utf-8"))
    os.close(fd)

    processor = _make_processor(
        text_acquisition_router=TextAcquisitionRouter(),
        ocr_postprocessor=OCRPostProcessor(),
        extraction_runner=KVOnlyExtractionRunner(),
        validation_runner=GroundingValidationRunner(),
    )
    result = processor.process_document(_schema(), _document(path), _available_tools())

    assert result.validation_report.pass_status is True
    assert result.validation_report.summary is not None
    assert "grounded" in result.validation_report.summary
    assert result.validation_report.summary != "stub validation passed"
    assert result.validation_report.field_issues == []

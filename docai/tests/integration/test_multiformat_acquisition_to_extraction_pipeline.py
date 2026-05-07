"""Multi-format acquisition-to-extraction integration matrix.

Confirms that TXT, embedded-text PDF, and image (fake OCR) inputs each produce
a structurally identical ExtractedOutput through the common source-agnostic pipeline:

    TextAcquisitionRouter
    → OCROutput
    → OCRPostProcessor
    → KVOnlyExtractionRunner
    → ExtractedOutput
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    ExtractionSchema,
    ExtractedOutput,
    Field,
    OCROutput,
    SelectedPolicy,
)
from docai_core.extraction.kv_extraction_runner import KVOnlyExtractionRunner
from docai_core.extraction.ocr_postprocessor import OCRPostProcessor
from docai_core.text_acquisition.image_ocr_extractor import ImageOCRExtractor
from docai_core.text_acquisition.router import TextAcquisitionRouter

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_INVOICE_TEXT = (
    "Invoice Number: INV-001\n"
    "Invoice Date: 2026-03-15\n"
    "Total Amount: $100.00\n"
    "Status: Paid\n"
)

_EXPECTED = {
    "invoice_number": "INV-001",
    "invoice_date":   "2026-03-15",
    "total_amount":   "$100.00",
    "status":         "Paid",
}


def _document(file_path: str, doc_id: str = "doc-matrix-1") -> Document:
    return Document(
        document_id=doc_id,
        job_id="job-1",
        original_filename=os.path.basename(file_path),
        file_path=file_path,
        status="processing",
        uploaded_at=datetime(2026, 3, 15),
        profile=DocumentProfile(document_id=doc_id),
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
# Shared pipeline runner
# ---------------------------------------------------------------------------

def _run_pipeline(
    router: TextAcquisitionRouter,
    document: Document,
) -> tuple[OCROutput, ExtractedOutput]:
    """Run the full source-agnostic acquisition-to-extraction pipeline."""
    ocr_output  = router.extract(document)
    cleaned     = OCRPostProcessor().process(ocr_output)
    extracted   = KVOnlyExtractionRunner().build_extracted_output(
        schema=_schema(),
        document=document,
        selected_policy=_policy(),
        ocr_output=cleaned,
    )
    return ocr_output, extracted


def _assert_invoice_fields(extracted: ExtractedOutput) -> None:
    field_map = {f.field_name: f for f in extracted.fields}
    for name, expected_value in _EXPECTED.items():
        assert field_map[name].value == expected_value, (
            f"Field {name!r}: expected {expected_value!r}, got {field_map[name].value!r}"
        )
    found = [f for f in extracted.fields if f.value != "N/A"]
    assert all(f.extraction_method == "generic_kv" for f in found)
    assert all(f.validation_status == "needs_review" for f in found)


# ---------------------------------------------------------------------------
# PDF helper (minimal raw-byte PDF — same pattern as test_pdf_to_extracted_output_pipeline.py)
# ---------------------------------------------------------------------------

def _make_pdf_bytes(pages: list[str]) -> bytes:
    streams: list[bytes] = []
    for text in pages:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = (
            b"BT\n/F1 12 Tf\n50 750 Td\n("
            + escaped.encode()
            + b") Tj\nET\n"
        )
        streams.append(stream)

    n = len(pages)
    page_obj_ids   = list(range(3, 3 + n))
    stream_obj_ids = list(range(3 + n, 3 + 2 * n))
    font_obj_id    = 3 + 2 * n

    def obj(num: int, content: bytes) -> bytes:
        return b"%d 0 obj\n" % num + content + b"\nendobj\n"

    page_refs = b" ".join(b"%d 0 R" % i for i in page_obj_ids)
    objects: list[bytes] = [
        obj(1, b"<<\n/Type /Catalog\n/Pages 2 0 R\n>>"),
        obj(2, b"<<\n/Type /Pages\n/Kids [" + page_refs + b"]\n/Count %d\n>>" % n),
    ]
    for pid, sid in zip(page_obj_ids, stream_obj_ids):
        objects.append(obj(pid,
            b"<<\n/Type /Page\n/Parent 2 0 R\n"
            b"/MediaBox [0 0 612 792]\n"
            b"/Contents %d 0 R\n" % sid +
            b"/Resources <<\n/Font <<\n/F1 %d 0 R\n>> >> >>" % font_obj_id
        ))
    for sid, stream in zip(stream_obj_ids, streams):
        objects.append(obj(sid,
            b"<<\n/Length %d\n>>\nstream\n" % len(stream) + stream + b"endstream"
        ))
    objects.append(obj(font_obj_id,
        b"<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>"
    ))

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


def _pdf_file(text: str) -> str:
    data = _make_pdf_bytes([text])
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.write(fd, data)
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_txt_pipeline() -> None:
    """TXT file → TextAcquisitionRouter → OCROutput(plain_text_extractor) → ExtractedOutput."""
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.write(fd, _INVOICE_TEXT.encode("utf-8"))
    os.close(fd)
    try:
        router = TextAcquisitionRouter()
        ocr_output, extracted = _run_pipeline(router, _document(path))

        assert ocr_output.engine_id == "plain_text_extractor"
        _assert_invoice_fields(extracted)
    finally:
        os.unlink(path)


def test_pdf_pipeline() -> None:
    """Embedded-text PDF → TextAcquisitionRouter → OCROutput(native_pdf_text_extractor) → ExtractedOutput."""
    page_text = "Invoice Number: INV-001  Invoice Date: 2026-03-15  Total Amount: $100.00  Status: Paid"
    path = _pdf_file(page_text)
    try:
        router = TextAcquisitionRouter()
        ocr_output, extracted = _run_pipeline(router, _document(path))

        assert ocr_output.engine_id == "native_pdf_text_extractor"
        _assert_invoice_fields(extracted)
    finally:
        os.unlink(path)


def test_image_pipeline_with_fake_ocr() -> None:
    """Image file → TextAcquisitionRouter(fake OCR) → OCROutput(tesseract_image_ocr) → ExtractedOutput."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        image_extractor = ImageOCRExtractor(ocr_callable=lambda _: _INVOICE_TEXT)
        router = TextAcquisitionRouter(image_ocr_extractor=image_extractor)
        ocr_output, extracted = _run_pipeline(router, _document(path))

        assert ocr_output.engine_id == "tesseract_image_ocr"
        _assert_invoice_fields(extracted)
    finally:
        os.unlink(path)

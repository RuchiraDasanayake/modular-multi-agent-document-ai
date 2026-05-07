"""Integration test: NativePdfTextExtractor → OCRPostProcessor → KVOnlyExtractionRunner.

Proves that a real PDF file can be read and turned into a structured ExtractedOutput
without stubs, model calls, or runtime orchestration.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    SelectedPolicy,
)
from docai_core.extraction.kv_extraction_runner import KVOnlyExtractionRunner
from docai_core.extraction.ocr_postprocessor import OCRPostProcessor
from docai_core.ocr.native_pdf_text_extractor import NativePdfTextExtractor


# ---------------------------------------------------------------------------
# PDF helper (same minimal raw-byte approach as unit tests)
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


def _pdf_file(pages: list[str]) -> str:
    data = _make_pdf_bytes(pages)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.write(fd, data)
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _document(file_path: str) -> Document:
    return Document(
        document_id="doc-pdf-1",
        job_id="job-1",
        original_filename="invoice.pdf",
        file_path=file_path,
        status="processing",
        uploaded_at=datetime(2026, 3, 15),
        profile=DocumentProfile(document_id="doc-pdf-1"),
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

def test_single_page_pdf_to_extracted_output() -> None:
    """Full pipeline: PDF file → NativePdfTextExtractor → OCRPostProcessor → KVOnlyExtractionRunner."""
    page_text = "Invoice Number: INV-010  Invoice Date: 2026-04-01  Total Amount: $500.00"
    path = _pdf_file([page_text])
    try:
        ocr_raw   = NativePdfTextExtractor().extract(_document(path))
        ocr_clean = OCRPostProcessor().process(ocr_raw)
        extracted = KVOnlyExtractionRunner().build_extracted_output(
            schema=_schema(),
            document=_document(path),
            selected_policy=_policy(),
            ocr_output=ocr_clean,
        )

        assert extracted.document_id == "doc-pdf-1"
        field_map = {f.field_name: f for f in extracted.fields}
        assert field_map["invoice_number"].value == "INV-010"
        assert field_map["invoice_date"].value == "2026-04-01"
        assert field_map["total_amount"].value == "$500.00"
        assert all(f.extraction_method == "generic_kv" for f in extracted.fields)
    finally:
        os.unlink(path)


def test_multi_page_pdf_aggregates_text_across_pages() -> None:
    """Text from all pages is combined so fields split across pages are extracted."""
    path = _pdf_file([
        "Invoice Number: INV-020",
        "Total Amount: $750.00",
    ])
    try:
        ocr_raw   = NativePdfTextExtractor().extract(_document(path))
        ocr_clean = OCRPostProcessor().process(ocr_raw)
        extracted = KVOnlyExtractionRunner().build_extracted_output(
            schema=_schema(),
            document=_document(path),
            selected_policy=_policy(),
            ocr_output=ocr_clean,
        )

        field_map = {f.field_name: f for f in extracted.fields}
        assert field_map["invoice_number"].value == "INV-020"
        assert field_map["total_amount"].value == "$750.00"
        assert ocr_raw.confidence == 1.0
        assert len(ocr_raw.pages) == 2
    finally:
        os.unlink(path)

"""Unit tests for NativePdfTextExtractor."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest

from docai_core.contracts.domain import Document, DocumentProfile
from docai_core.ocr.native_pdf_text_extractor import NativePdfTextExtractor


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------

def _make_pdf_bytes(pages: list[str]) -> bytes:
    """Build a minimal valid PDF with one text line per page entry.

    Each string in *pages* is embedded as a single text object at the top of
    the page. pypdf's extract_text() recovers the text from these BT/ET blocks.
    """
    streams: list[bytes] = []
    for text in pages:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = (
            b"BT\n"
            b"/F1 12 Tf\n"
            b"50 750 Td\n"
            b"(" + escaped.encode() + b") Tj\n"
            b"ET\n"
        )
        streams.append(stream)

    objects: list[bytes] = []

    def obj(n: int, content: bytes) -> bytes:
        return b"%d 0 obj\n" % n + content + b"\nendobj\n"

    # Object layout:
    # 1 = catalog
    # 2 = pages dict
    # 3..2+N = page objects  (each page references stream obj 3+N+k)
    # 3+N..3+2N-1 = content streams
    n = len(pages)
    page_obj_ids   = list(range(3, 3 + n))
    stream_obj_ids = list(range(3 + n, 3 + 2 * n))

    font_obj_id = 3 + 2 * n

    page_refs = b" ".join(b"%d 0 R" % i for i in page_obj_ids)
    objects.append(obj(1, b"<<\n/Type /Catalog\n/Pages 2 0 R\n>>"))
    objects.append(obj(2, b"<<\n/Type /Pages\n/Kids [" + page_refs + b"]\n/Count %d\n>>" % n))

    for k, (pid, sid) in enumerate(zip(page_obj_ids, stream_obj_ids)):
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
    """Write a PDF to a temp file and return its path."""
    data = _make_pdf_bytes(pages)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.write(fd, data)
    os.close(fd)
    return path


def _doc(file_path: str, doc_id: str = "doc-1") -> Document:
    return Document(
        document_id=doc_id,
        job_id="job-1",
        original_filename="test.pdf",
        file_path=file_path,
        status="processing",
        uploaded_at=datetime(2026, 3, 15),
        profile=DocumentProfile(document_id=doc_id),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_extracts_text_from_single_page_pdf() -> None:
    path = _pdf_file(["Invoice Number: INV-001"])
    try:
        extractor = NativePdfTextExtractor()
        result = extractor.extract(_doc(path))
        assert "INV-001" in result.text
        assert result.document_id == "doc-1"
        assert result.engine_id == "native_pdf_text_extractor"
        assert result.confidence == 1.0
        assert len(result.pages) == 1
        assert result.pages[0].page_number == 1
        assert "INV-001" in result.pages[0].text
    finally:
        os.unlink(path)


def test_extracts_text_from_multi_page_pdf() -> None:
    path = _pdf_file(["Invoice Number: INV-002", "Total Amount: $200.00"])
    try:
        extractor = NativePdfTextExtractor()
        result = extractor.extract(_doc(path))
        assert len(result.pages) == 2
        assert result.pages[0].page_number == 1
        assert result.pages[1].page_number == 2
        assert "INV-002" in result.pages[0].text
        assert "$200.00" in result.pages[1].text
        assert "INV-002" in result.text
        assert "$200.00" in result.text
        assert result.confidence == 1.0
    finally:
        os.unlink(path)


def test_raises_file_not_found_for_missing_file() -> None:
    extractor = NativePdfTextExtractor()
    doc = _doc("/nonexistent/path/missing.pdf")
    with pytest.raises(FileNotFoundError):
        extractor.extract(doc)


def test_raises_value_error_for_invalid_pdf() -> None:
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.write(fd, b"this is not a pdf")
    os.close(fd)
    try:
        extractor = NativePdfTextExtractor()
        with pytest.raises(ValueError):
            extractor.extract(_doc(path))
    finally:
        os.unlink(path)

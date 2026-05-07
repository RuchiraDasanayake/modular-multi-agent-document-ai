"""Unit tests for ImageOCRExtractor."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime

import pytest

from docai_core.contracts.domain import Document, DocumentProfile
from docai_core.text_acquisition.image_ocr_extractor import (
    ImageOCRDependencyError,
    ImageOCRExtractor,
)

_INVOICE_TEXT = "Invoice Number: INV-001\nInvoice Date: 2026-03-15\n"


def _doc(file_path: str, doc_id: str = "doc-1") -> Document:
    return Document(
        document_id=doc_id,
        job_id="job-1",
        original_filename="scan.png",
        file_path=file_path,
        status="processing",
        uploaded_at=datetime(2026, 3, 15),
        profile=DocumentProfile(document_id=doc_id),
    )


def _png_file() -> str:
    """Write a minimal 1×1 white PNG to a temp file and return its path."""
    from PIL import Image as PILImage
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    PILImage.new("RGB", (1, 1), color=255).save(path)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_image_ocr_extractor_returns_ocr_output_with_fake_ocr() -> None:
    path = _png_file()
    try:
        extractor = ImageOCRExtractor(ocr_callable=lambda _: _INVOICE_TEXT)
        result = extractor.extract(_doc(path))
        assert "INV-001" in result.text
        assert result.engine_id == "tesseract_image_ocr"
        assert result.confidence == 1.0
        assert result.document_id == "doc-1"
        assert len(result.pages) == 1
        assert result.pages[0].page_number == 1
    finally:
        os.unlink(path)


def test_image_ocr_extractor_empty_ocr_returns_zero_confidence() -> None:
    path = _png_file()
    try:
        extractor = ImageOCRExtractor(ocr_callable=lambda _: "")
        result = extractor.extract(_doc(path))
        assert result.confidence == 0.0
        assert result.text == ""
    finally:
        os.unlink(path)


def test_image_ocr_extractor_missing_file_raises_file_not_found() -> None:
    extractor = ImageOCRExtractor(ocr_callable=lambda _: "text")
    with pytest.raises(FileNotFoundError):
        extractor.extract(_doc("/nonexistent/path/scan.png"))


def test_image_ocr_extractor_directory_raises_value_error() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        extractor = ImageOCRExtractor(ocr_callable=lambda _: "text")
        with pytest.raises(ValueError):
            extractor.extract(_doc(tmpdir))


def test_image_ocr_extractor_unreadable_image_raises_value_error() -> None:
    """A file with invalid image bytes raises ValueError when read by Pillow."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.write(fd, b"not an image")
    os.close(fd)
    try:
        extractor = ImageOCRExtractor()  # no fake callable — uses real Pillow
        # File validation passes (file exists); Pillow raises on open
        with pytest.raises((ValueError, ImageOCRDependencyError)):
            extractor.extract(_doc(path))
    finally:
        os.unlink(path)


def test_image_ocr_extractor_dependency_error_when_pytesseract_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate missing pytesseract by removing it from sys.modules."""
    path = _png_file()
    try:
        monkeypatch.setitem(sys.modules, "pytesseract", None)  # type: ignore[arg-type]
        extractor = ImageOCRExtractor()  # no ocr_callable → will try real Tesseract
        with pytest.raises(ImageOCRDependencyError):
            extractor.extract(_doc(path))
    finally:
        os.unlink(path)


def test_public_export_available() -> None:
    from docai_core.text_acquisition import ImageOCRDependencyError as ExportedError
    from docai_core.text_acquisition import ImageOCRExtractor as ExportedExtractor

    assert ExportedExtractor is not None
    assert ExportedError is not None
    extractor = ExportedExtractor(ocr_callable=lambda _: "smoke")
    assert hasattr(extractor, "extract")

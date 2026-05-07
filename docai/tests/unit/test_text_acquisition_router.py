"""Unit tests for TextAcquisitionRouter."""

from __future__ import annotations

from datetime import datetime

import pytest

from docai_core.contracts.domain import Document, DocumentProfile, OCROutput, OCRPage
from docai_core.text_acquisition.base import UnsupportedDocumentTypeError
from docai_core.text_acquisition.router import TextAcquisitionRouter


# ---------------------------------------------------------------------------
# Fake extractors — avoid real file I/O in router unit tests
# ---------------------------------------------------------------------------

class _FakeExtractor:
    """Returns a canned OCROutput regardless of document content."""

    def __init__(self, engine_id: str = "fake", text: str = "fake text") -> None:
        self.engine_id = engine_id
        self.text = text
        self.called_with: Document | None = None

    def extract(self, document: Document) -> OCROutput:
        self.called_with = document
        return OCROutput(
            document_id=document.document_id,
            engine_id=self.engine_id,
            text=self.text,
            pages=[OCRPage(page_number=1, text=self.text)],
            blocks=[],
            tables_detected=[],
            confidence=1.0,
        )


def _doc(file_path: str) -> Document:
    return Document(
        document_id="doc-1",
        job_id="job-1",
        original_filename="test",
        file_path=file_path,
        status="processing",
        uploaded_at=datetime(2026, 3, 15),
        profile=DocumentProfile(document_id="doc-1"),
    )


def _router(
    txt_engine: str = "txt_fake",
    pdf_engine: str = "pdf_fake",
    img_engine: str = "img_fake",
    pdf_text: str = "This PDF has enough embedded text to skip OCR fallback.",
) -> tuple[TextAcquisitionRouter, _FakeExtractor, _FakeExtractor, _FakeExtractor]:
    txt = _FakeExtractor(txt_engine)
    pdf = _FakeExtractor(pdf_engine, text=pdf_text)
    img = _FakeExtractor(img_engine)
    router = TextAcquisitionRouter(
        plain_text_extractor=txt,        # type: ignore[arg-type]
        native_pdf_text_extractor=pdf,   # type: ignore[arg-type]
        image_ocr_extractor=img,         # type: ignore[arg-type]
    )
    return router, txt, pdf, img


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_txt_routes_to_plain_text_extractor() -> None:
    router, txt_fake, _, _ = _router()
    result = router.extract(_doc("/tmp/invoice.txt"))
    assert result.engine_id == "txt_fake"
    assert txt_fake.called_with is not None


def test_extension_matching_is_case_insensitive() -> None:
    router, txt_fake, _, _ = _router()
    router.extract(_doc("/tmp/invoice.TXT"))
    assert txt_fake.called_with is not None


def test_pdf_routes_to_native_pdf_text_extractor() -> None:
    router, _, pdf_fake, _ = _router()
    result = router.extract(_doc("/tmp/invoice.pdf"))
    assert result.engine_id == "pdf_fake"
    assert pdf_fake.called_with is not None


def test_png_routes_to_image_ocr_extractor() -> None:
    router, _, _, img_fake = _router()
    result = router.extract(_doc("/tmp/scan.png"))
    assert result.engine_id == "img_fake"
    assert img_fake.called_with is not None


@pytest.mark.parametrize("ext", [".jpg", ".jpeg", ".tif", ".tiff"])
def test_image_extensions_route_to_image_ocr_extractor(ext: str) -> None:
    router, _, _, img_fake = _router()
    result = router.extract(_doc(f"/tmp/scan{ext}"))
    assert result.engine_id == "img_fake"
    assert img_fake.called_with is not None


def test_image_extension_matching_is_case_insensitive() -> None:
    router, _, _, img_fake = _router()
    router.extract(_doc("/tmp/scan.PNG"))
    assert img_fake.called_with is not None


def test_docx_raises_unsupported_error_with_docx_message() -> None:
    router, _, _, _ = _router()
    with pytest.raises(UnsupportedDocumentTypeError) as exc_info:
        router.extract(_doc("/tmp/contract.docx"))
    assert "docx" in str(exc_info.value).lower()


def test_unknown_extension_raises_unsupported_error() -> None:
    router, _, _, _ = _router()
    with pytest.raises(UnsupportedDocumentTypeError):
        router.extract(_doc("/tmp/data.xyz"))


def test_router_delegates_to_extractor_not_reads_file_directly() -> None:
    router, txt_fake, _, _ = _router()
    doc = _doc("/nonexistent/path/invoice.txt")
    result = router.extract(doc)
    assert txt_fake.called_with is doc
    assert result.engine_id == "txt_fake"

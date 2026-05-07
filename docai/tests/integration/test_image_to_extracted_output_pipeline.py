"""Integration test: TextAcquisitionRouter(fake OCR) → OCRPostProcessor → KVOnlyExtractionRunner.

Proves image files can flow through the full acquisition layer to structured extraction
without real Tesseract — OCR is injected via ocr_callable.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest

from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    SelectedPolicy,
)
from docai_core.extraction.kv_extraction_runner import KVOnlyExtractionRunner
from docai_core.extraction.ocr_postprocessor import OCRPostProcessor
from docai_core.text_acquisition.image_ocr_extractor import (
    ImageOCRDependencyError,
    ImageOCRExtractor,
)
from docai_core.text_acquisition.router import TextAcquisitionRouter

_INVOICE_TEXT = (
    "Invoice Number: INV-001\n"
    "Invoice Date: 2026-03-15\n"
    "Total Amount: $100.00\n"
    "Status: Paid\n"
)


def _png_file() -> str:
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    return path


def _document(file_path: str) -> Document:
    return Document(
        document_id="doc-img-1",
        job_id="job-1",
        original_filename=os.path.basename(file_path),
        file_path=file_path,
        status="processing",
        uploaded_at=datetime(2026, 3, 15),
        profile=DocumentProfile(document_id="doc-img-1"),
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

def test_image_file_to_extracted_output_with_fake_ocr() -> None:
    """Full pipeline: .png → TextAcquisitionRouter(fake OCR) → OCRPostProcessor → KVOnlyExtractionRunner."""
    path = _png_file()
    try:
        image_extractor = ImageOCRExtractor(ocr_callable=lambda _: _INVOICE_TEXT)
        router = TextAcquisitionRouter(image_ocr_extractor=image_extractor)

        ocr_raw   = router.extract(_document(path))
        ocr_clean = OCRPostProcessor().process(ocr_raw)
        extracted = KVOnlyExtractionRunner().build_extracted_output(
            schema=_schema(),
            document=_document(path),
            selected_policy=_policy(),
            ocr_output=ocr_clean,
        )

        assert "INV-001" in ocr_raw.text

        field_map = {f.field_name: f for f in extracted.fields}
        assert field_map["invoice_number"].value == "INV-001"
        assert field_map["invoice_date"].value == "2026-03-15"
        assert field_map["total_amount"].value == "$100.00"
        assert field_map["status"].value == "Paid"

        found = [f for f in extracted.fields if f.value != "N/A"]
        assert all(f.extraction_method == "generic_kv" for f in found)
        assert all(f.validation_status == "needs_review" for f in found)
    finally:
        os.unlink(path)


def test_image_ocr_dependency_error_propagates_through_router() -> None:
    """Real ImageOCRExtractor without callable raises ImageOCRDependencyError if Tesseract absent."""
    path = _png_file()
    try:
        import sys
        # Simulate missing pytesseract by hiding it from sys.modules.
        saved = sys.modules.get("pytesseract", ...)
        sys.modules["pytesseract"] = None  # type: ignore[assignment]
        try:
            router = TextAcquisitionRouter()  # default extractor, no fake callable
            with pytest.raises(ImageOCRDependencyError):
                router.extract(_document(path))
        finally:
            if saved is ...:
                del sys.modules["pytesseract"]
            else:
                sys.modules["pytesseract"] = saved
    finally:
        os.unlink(path)

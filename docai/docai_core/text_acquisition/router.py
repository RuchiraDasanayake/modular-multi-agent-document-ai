"""Text acquisition router - dispatches documents to the correct extractor."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from docai_core.contracts.domain import Document, OCROutput, OCRPage
from docai_core.ocr.native_pdf_text_extractor import NativePdfTextExtractor
from docai_core.text_acquisition.base import UnsupportedDocumentTypeError
from docai_core.text_acquisition.image_ocr_extractor import (
    ImageOCRDependencyError,
    ImageOCRExtractor,
)
from docai_core.text_acquisition.plain_text_extractor import PlainTextExtractor

_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff"})
_DOCX_MESSAGE = "DOCX text extraction is not implemented yet."
_MIN_NATIVE_PDF_CHARS = 24


@dataclass(slots=True)
class TextAcquisitionRouter:
    """Routes a Document to the appropriate text extractor by file extension.

    Supported now:
        .txt                               -> PlainTextExtractor
        .pdf                               -> NativePdfTextExtractor, then OCR fallback when needed
        .png / .jpg / .jpeg / .tif / .tiff -> ImageOCRExtractor (Tesseract)

    Recognized but not implemented:
        .docx -> UnsupportedDocumentTypeError
    """

    plain_text_extractor: PlainTextExtractor = field(
        default_factory=PlainTextExtractor
    )
    native_pdf_text_extractor: NativePdfTextExtractor = field(
        default_factory=NativePdfTextExtractor
    )
    image_ocr_extractor: ImageOCRExtractor = field(
        default_factory=ImageOCRExtractor
    )

    def extract(self, document: Document) -> OCROutput:
        """Dispatch *document* to the correct extractor and return an OCROutput.

        Raises:
            UnsupportedDocumentTypeError: for unrecognized or not-yet-implemented types.
            FileNotFoundError: propagated from the underlying extractor.
            ValueError: propagated from the underlying extractor.
            ImageOCRDependencyError: when scanned-PDF OCR dependencies are unavailable.
        """
        ext = os.path.splitext(document.file_path)[1].lower()

        if ext == ".txt":
            return self.plain_text_extractor.extract(document)

        if ext == ".pdf":
            native = self.native_pdf_text_extractor.extract(document)
            if self._is_scanned_pdf(native):
                return self._extract_scanned_pdf_via_ocr(document)
            return native

        if ext in _IMAGE_EXTENSIONS:
            return self.image_ocr_extractor.extract(document)

        if ext == ".docx":
            raise UnsupportedDocumentTypeError(_DOCX_MESSAGE)

        raise UnsupportedDocumentTypeError(
            f"No extractor registered for file type {ext!r}."
        )

    @staticmethod
    def _is_scanned_pdf(native_pdf_output: OCROutput) -> bool:
        text = native_pdf_output.text or ""
        compact = "".join(ch for ch in text if not ch.isspace())
        return len(compact) < _MIN_NATIVE_PDF_CHARS

    def _extract_scanned_pdf_via_ocr(self, document: Document) -> OCROutput:
        with tempfile.TemporaryDirectory(prefix="docai_pdf_pages_") as tmp_dir:
            rendered_pages = self._render_pdf_pages_to_images(document.file_path, Path(tmp_dir))
            if not rendered_pages:
                raise ValueError(f"Scanned PDF has no renderable pages: {document.file_path!r}")

            merged_parts: list[str] = []
            pages: list[OCRPage] = []
            confidences: list[float] = []
            ocr_content_parts: list[str] = []
            for page_number, image_path in enumerate(rendered_pages, start=1):
                page_doc = Document(
                    document_id=document.document_id,
                    job_id=document.job_id,
                    original_filename=f"{document.original_filename}.page_{page_number}.png",
                    file_path=image_path,
                    status=document.status,
                    uploaded_at=document.uploaded_at,
                    profile=document.profile,
                    page_count=document.page_count,
                )
                page_ocr = self.image_ocr_extractor.extract(page_doc)
                page_text = (page_ocr.text or "").strip()
                marker = f"--- page {page_number} ---"
                marked_page_text = f"{marker}:\n{page_text}".strip()
                pages.append(OCRPage(page_number=page_number, text=marked_page_text))
                merged_parts.append(marked_page_text)
                ocr_content_parts.append(page_text)
                confidences.append(float(page_ocr.confidence or 0.0))

            merged_text = "\n\n".join(part for part in merged_parts if part).strip()
            compact = "".join(ch for ch in "\n".join(ocr_content_parts) if not ch.isspace())
            if len(compact) < _MIN_NATIVE_PDF_CHARS:
                raise ValueError("Scanned PDF OCR produced insufficient text for extraction.")

            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            return OCROutput(
                document_id=document.document_id,
                engine_id="pdf_scanned_ocr_fallback",
                text=merged_text,
                pages=pages,
                blocks=[],
                tables_detected=[],
                confidence=avg_confidence,
            )

    @staticmethod
    def _render_pdf_pages_to_images(pdf_path: str, out_dir: Path) -> list[str]:
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            try:
                import pymupdf as fitz
            except ImportError:
                raise ImageOCRDependencyError(
                    "PyMuPDF is required for scanned PDF OCR fallback. Install with: pip install pymupdf"
                ) from exc

        paths: list[str] = []
        try:
            with fitz.open(pdf_path) as pdf:
                if pdf.page_count <= 0:
                    return []
                for idx, page in enumerate(pdf, start=1):
                    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
                    out_path = out_dir / f"page_{idx}.png"
                    pix.save(str(out_path))
                    paths.append(str(out_path))
        except Exception as exc:
            raise ValueError(f"Failed to render PDF pages for OCR: {exc}") from exc

        return paths

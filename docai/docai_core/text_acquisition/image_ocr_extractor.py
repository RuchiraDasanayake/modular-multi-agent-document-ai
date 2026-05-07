"""Tesseract-based OCR extractor for image files."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field

from docai_core.contracts.domain import Document, OCROutput, OCRPage
from docai_core.text_acquisition.image_preprocessor import ImagePreprocessor


class ImageOCRDependencyError(Exception):
    """Raised when a required OCR dependency (Pillow, pytesseract, or Tesseract binary) is absent."""


@dataclass(slots=True)
class ImageOCRExtractor:
    """Extract text from image files using Tesseract OCR via pytesseract.

    Implements TextExtractorProtocol; returns OCROutput for any image file.

    Tesseract and pytesseract are optional system-level dependencies. Importing
    this module does NOT require them to be installed — the check is deferred
    to the first real OCR call (i.e. when ocr_callable is None).

    For tests, inject an ocr_callable to bypass Tesseract entirely.
    """

    engine_id: str = "tesseract_image_ocr"
    language: str = "eng"
    tesseract_config: str = ""
    preprocessor: ImagePreprocessor = field(default_factory=ImagePreprocessor)
    ocr_callable: Callable[[str], str] | None = None

    def extract(self, document: Document) -> OCROutput:
        """Return OCROutput from an image file at *document.file_path*.

        Raises:
            FileNotFoundError: if the file does not exist.
            ValueError: if the path is a directory or the image cannot be read.
            ImageOCRDependencyError: if Pillow, pytesseract, or Tesseract binary is absent.
        """
        path = document.file_path

        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path!r}")
        if os.path.isdir(path):
            raise ValueError(f"Path is a directory, not a file: {path!r}")

        if self.ocr_callable is not None:
            text = self.ocr_callable(path)
        else:
            text = self._run_tesseract(path)

        page = OCRPage(page_number=1, text=text)
        confidence = 1.0 if text.strip() else 0.0

        return OCROutput(
            document_id=document.document_id,
            engine_id=self.engine_id,
            text=text,
            pages=[page],
            blocks=[],
            tables_detected=[],
            confidence=confidence,
        )

    def _run_tesseract(self, path: str) -> str:
        """Open *path*, preprocess, and run Tesseract OCR. All imports are lazy."""
        try:
            from PIL import Image
        except ImportError as exc:
            raise ImageOCRDependencyError(
                "Pillow is required for image OCR. Install it with: pip install Pillow"
            ) from exc

        try:
            import pytesseract
        except ImportError as exc:
            raise ImageOCRDependencyError(
                "pytesseract is required for image OCR. Install it with: pip install pytesseract"
            ) from exc

        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError as exc:
            raise ImageOCRDependencyError(
                "Tesseract binary not found. Install Tesseract: "
                "https://github.com/tesseract-ocr/tesseract"
            ) from exc
        except Exception as exc:
            raise ImageOCRDependencyError(
                f"Tesseract is not available: {exc}"
            ) from exc

        try:
            with Image.open(path) as img:
                processed = self.preprocessor.normalize(img)
        except Exception as exc:
            raise ValueError(f"Cannot read image at {path!r}: {exc}") from exc

        return pytesseract.image_to_string(
            processed,
            lang=self.language,
            config=self.tesseract_config,
        )

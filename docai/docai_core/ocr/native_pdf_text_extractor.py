"""Native PDF text extractor using pypdf for embedded-text PDFs."""

from __future__ import annotations

from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from docai_core.contracts.domain import Document, OCROutput, OCRPage

_ENGINE_ID = "native_pdf_text_extractor"


@dataclass(slots=True)
class NativePdfTextExtractor:
    """Extracts embedded text from PDF files without OCR."""

    engine_id: str = _ENGINE_ID

    def extract(self, document: Document) -> OCROutput:
        """Read embedded text from *document.file_path* and return an OCROutput.

        Raises:
            FileNotFoundError: if the file does not exist.
            ValueError: if the file is not a valid or readable PDF.
        """
        path = document.file_path
        try:
            reader = PdfReader(path)
        except FileNotFoundError:
            raise
        except (PdfReadError, Exception) as exc:
            raise ValueError(f"Cannot read PDF at {path!r}: {exc}") from exc

        pages: list[OCRPage] = []
        for i, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            pages.append(OCRPage(page_number=i, text=raw.strip()))

        non_empty = [p.text for p in pages if p.text]
        aggregate = "\n\n".join(non_empty)
        confidence = 1.0 if non_empty else 0.0

        return OCROutput(
            document_id=document.document_id,
            engine_id=self.engine_id,
            text=aggregate,
            pages=pages,
            blocks=[],
            tables_detected=[],
            confidence=confidence,
        )

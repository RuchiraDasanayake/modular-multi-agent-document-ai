"""Plain text extractor for .txt files."""

from __future__ import annotations

import os
from dataclasses import dataclass

from docai_core.contracts.domain import Document, OCROutput, OCRPage

_ENGINE_ID = "plain_text_extractor"


@dataclass(slots=True)
class PlainTextExtractor:
    """Reads a UTF-8 (or Latin-1 fallback) .txt file and returns an OCROutput."""

    engine_id: str = _ENGINE_ID

    def extract(self, document: Document) -> OCROutput:
        """Return an OCROutput from *document.file_path*.

        Raises:
            FileNotFoundError: if the file does not exist.
            ValueError: if the path is a directory or the file cannot be read.
        """
        path = document.file_path

        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path!r}")

        if os.path.isdir(path):
            raise ValueError(f"Path is a directory, not a file: {path!r}")

        try:
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except UnicodeDecodeError:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
        except OSError as exc:
            raise ValueError(f"Cannot read file at {path!r}: {exc}") from exc

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

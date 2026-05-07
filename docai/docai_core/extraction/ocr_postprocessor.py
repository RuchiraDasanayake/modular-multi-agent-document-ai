"""OCR/native-text post-processing for DocAI v2.

Cleans raw OCROutput before it reaches extraction runners:
degarble, hyphen-break joining, control-character removal, whitespace normalization.
No external dependencies — stdlib re and existing extraction utilities only.
Not yet wired into runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from docai_core.contracts.domain import OCROutput, OCRPage
from docai_core.extraction.degarble import degarble, garbled_ratio

_RE_HYPHEN_BREAK = re.compile(r"-\s*\n\s*")
_RE_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RE_MULTI_BLANK = re.compile(r"\n{3,}")


@dataclass(slots=True)
class OCRPostProcessor:
    """Deterministic cleaner for raw OCR or native-extracted text.

    Applies degarble when the page garbled ratio meets the threshold,
    then always applies line-level cleanup and whitespace normalization.
    Returns a new OCROutput — does not mutate the input.
    """

    garble_threshold: float = 0.15

    def process(self, ocr_output: OCROutput) -> OCROutput:
        """Clean all pages and rebuild the aggregate text."""
        cleaned_pages = [self._clean_page(page) for page in ocr_output.pages]
        aggregate_text = "\n\n".join(p.text for p in cleaned_pages if p.text)
        return OCROutput(
            document_id=ocr_output.document_id,
            engine_id=ocr_output.engine_id,
            text=aggregate_text,
            pages=cleaned_pages,
            blocks=list(ocr_output.blocks),
            tables_detected=list(ocr_output.tables_detected),
            confidence=ocr_output.confidence,
        )

    def _clean_page(self, page: OCRPage) -> OCRPage:
        text = page.text
        if garbled_ratio(text) >= self.garble_threshold:
            text = degarble(text)
        text = _RE_HYPHEN_BREAK.sub("", text)
        text = _RE_CTRL.sub("", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = "\n".join(line.rstrip() for line in text.split("\n"))
        text = _RE_MULTI_BLANK.sub("\n\n", text)
        text = text.strip()
        return OCRPage(
            page_number=page.page_number,
            text=text,
            blocks=list(page.blocks),
        )

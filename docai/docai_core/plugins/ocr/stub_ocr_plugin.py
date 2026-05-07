from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import Document, OCROutput, OCRPage, RunPlan
from docai_core.plugins.ocr.base import OCRPlugin


@dataclass(slots=True)
class StubOCRPlugin(OCRPlugin):
    plugin_id: str = "stub_ocr_plugin"
    engine_name: str = "Stub OCR"

    def run_ocr(self, document: Document, run_plan: RunPlan) -> OCROutput:
        text = f"Fake OCR output for {document.original_filename}"
        return OCROutput(
            document_id=document.document_id,
            engine_id=self.plugin_id,
            text=text,
            pages=[OCRPage(page_number=1, text=text)],
            blocks=[],
            tables_detected=[],
            confidence=0.9,
        )

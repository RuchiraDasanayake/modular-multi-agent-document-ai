from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Protocol

from docai_core.contracts.domain import Document, OCROutput, RunPlan, ScalarValue


@dataclass(slots=True)
class OCRPluginConfig:
    plugin_id: str
    engine_name: str
    enabled: bool = True
    settings: dict[str, ScalarValue] = dc_field(default_factory=dict)


class OCRPlugin(Protocol):
    plugin_id: str
    engine_name: str

    def run_ocr(self, document: Document, run_plan: RunPlan) -> OCROutput:
        ...

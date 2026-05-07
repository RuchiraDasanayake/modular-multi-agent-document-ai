from __future__ import annotations

from dataclasses import dataclass

from docai_core.orchestration.document_processor import DocumentProcessor


@dataclass(slots=True)
class RuntimePipelineConfig:
    """Carries all mode-specific configuration for a single runtime execution.

    Decouples RuntimeOrchestrator from knowing how to build DocumentProcessor
    for each mode. Construct via pipeline_factory functions, not directly.
    """

    document_processor: DocumentProcessor
    generated_by: str
    is_stub: bool
    note: str

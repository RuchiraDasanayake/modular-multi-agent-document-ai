"""
Guardrails — Hallucination Detection & Validation Ensemble
5-layer guardrail system for RAG output validation.

Component Owner: Wijetunga W.L.A.T. (Thenuka)
"""

__version__ = "1.0.0"

from .models import (
    DocumentType,
    GuardrailDocumentContext,
    RAGInput,
    GuardrailOutput,
    ValidationMetric,
    SCHEMA_MAP,
)
from .core.ensemble import run_validation_ensemble

__all__ = [
    "DocumentType",
    "GuardrailDocumentContext",
    "RAGInput",
    "GuardrailOutput",
    "ValidationMetric",
    "SCHEMA_MAP",
    "run_validation_ensemble",
]

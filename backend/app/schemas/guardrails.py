"""Guardrails schemas — request/response models for the /api/guardrails endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GuardrailDocumentContextRequest(BaseModel):
    """Document metadata for validation."""
    doc_type: str = Field(..., description="One of: ClinicalSummary, MedicationDosage, Invoice, InsuranceClaim, BankStatement, PurchaseOrder, Receipt")
    vendor: Optional[str] = None
    quality_bin: Optional[str] = None


class ValidateRequest(BaseModel):
    """Request body for /api/guardrails/validate."""
    document_context: GuardrailDocumentContextRequest
    query: str
    answer_json: str = Field(..., description="Extracted data as JSON string to validate.")
    source_contexts: List[str] = Field(..., description="Source text chunks for faithfulness check.")
    document_id: Optional[str] = None


class ValidationMetricResponse(BaseModel):
    name: str
    score: float
    is_pass: bool
    details: str
    timestamp: datetime


class ValidateResponse(BaseModel):
    """Response from /api/guardrails/validate."""
    overall_passes: bool
    audit_log_id: str
    processing_time_ms: float
    timestamp: datetime
    validation_results: List[ValidationMetricResponse]
    metrics: Dict[str, Any]


class GuardrailStatsResponse(BaseModel):
    total_validations: int
    total_passed: int
    total_failed: int
    pass_rate: float
    avg_processing_time_ms: float
    checks_breakdown: Dict[str, Dict[str, int]]

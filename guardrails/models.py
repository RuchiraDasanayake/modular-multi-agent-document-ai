"""
Guardrail data models — document types, validation metrics, and I/O contracts.

Defines the 7 supported document types and their Pydantic schemas for schema-adherence
validation. Also defines RAGInput (from IDPO) and GuardrailOutput (response to IDPO).

Author: Wijetunga W.L.A.T.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════
# Document Types
# ═══════════════════════════════════════════════════════════════

class DocumentType(str, Enum):
    """Supported document types in the modular multi-agent system."""
    CLINICAL_SUMMARY = "ClinicalSummary"
    MEDICATION_DOSAGE = "MedicationDosage"
    INVOICE = "Invoice"
    INSURANCE_CLAIM = "InsuranceClaim"
    BANK_STATEMENT = "BankStatement"
    PURCHASE_ORDER = "PurchaseOrder"
    RECEIPT = "Receipt"
    GENERIC = "Generic"

# ═══════════════════════════════════════════════════════════════
# Document-Type Pydantic Schemas (for Schema Adherence check)
# ═══════════════════════════════════════════════════════════════

class ClinicalSummary(BaseModel):
    patient_name: str
    condition: str
    summary: str
    next_steps: str

class MedicationDosage(BaseModel):
    medication: str
    dosage_mg: int
    frequency: str
    reason: str

class Invoice(BaseModel):
    """Flexible invoice schema — extracted fields may use varying names and string values."""
    model_config = {"extra": "allow"}
    invoice_number: str | None = None
    customer_name: str | None = None
    date: str | None = None
    subtotal: Any | None = None
    tax: Any | None = None
    total: Any | None = None
    total_due: Any | None = None
    total_amount: Any | None = None

class BankStatement(BaseModel):
    model_config = {"extra": "allow"}
    account_holder: str | None = None
    bank_name: str | None = None
    account_number: str | None = None
    balance: Any | None = None

class PurchaseOrder(BaseModel):
    model_config = {"extra": "allow"}
    po_number: str | None = None
    supplier: str | None = None
    total_amount: Any | None = None

class Receipt(BaseModel):
    model_config = {"extra": "allow"}
    merchant: str | None = None
    total: Any | None = None
    date: str | None = None

class InsuranceClaim(BaseModel):
    model_config = {"extra": "allow"}
    policy_number: str | None = None
    claimant_name: str | None = None
    claim_amount: Any | None = None
    status: str | None = None

class Generic(BaseModel):
    """Generic catch-all document type — allows any fields."""
    model_config = {"extra": "allow"}

SCHEMA_MAP: dict[str, type[BaseModel]] = {
    "ClinicalSummary": ClinicalSummary,
    "MedicationDosage": MedicationDosage,
    "Invoice": Invoice,
    "BankStatement": BankStatement,
    "PurchaseOrder": PurchaseOrder,
    "Receipt": Receipt,
    "InsuranceClaim": InsuranceClaim,
    "Generic": Generic,
}

# ═══════════════════════════════════════════════════════════════
# Input / Output Contracts
# ═══════════════════════════════════════════════════════════════

class GuardrailDocumentContext(BaseModel):
    """Metadata from IDPO about the document being validated."""
    doc_type: DocumentType = Field(..., description="The type of document.")
    vendor: str | None = Field(None, description="Vendor or source name for domain-rule matching.")
    quality_bin: str | None = Field(None, description="OCR quality hint (high/medium/low).")

class RAGInput(BaseModel):
    """Input contract from IDPO — the payload we validate."""
    document_context: GuardrailDocumentContext
    query: str = Field(..., description="The original user query or prompt.")
    answer_json: str = Field(..., description="Extracted data as JSON string (this is what we validate).")
    source_contexts: list[str] = Field(..., description="Retrieved source text chunks (for faithfulness check).")
    document_id: str | None = Field(None, description="Unique document identifier for traceability.")

class ValidationMetric(BaseModel):
    """Result of a single guardrail check."""
    name: str = Field(..., description="Check name (e.g. 'pii_leakage').")
    score: float = Field(..., description="Numeric score (0.0 = fail, 1.0 = pass, 0.5 = suspicious).")
    is_pass: bool = Field(..., description="Whether the check passed.")
    details: str = Field(..., description="Human-readable explanation.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GuardrailOutput(BaseModel):
    """Final response — sent back to IDPO / dashboard."""
    rag_input: RAGInput
    validation_results: list[ValidationMetric]
    overall_passes: bool = Field(..., description="True only if ALL checks passed.")
    audit_log_id: str
    processing_time_ms: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    advice_id: str
    metrics: dict[str, Any] = Field(default_factory=dict)

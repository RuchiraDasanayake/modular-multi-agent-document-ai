"""
Guardrail data models — document types, validation metrics, and I/O contracts.

Defines the 7 supported document types and their Pydantic schemas for schema-adherence
validation. Also defines RAGInput (from IDPO) and GuardrailOutput (response to IDPO).

Author: Wijetunga W.L.A.T.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

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
    customer_name: str
    subtotal: float
    tax: float
    total: float


class BankStatement(BaseModel):
    account_holder: str
    bank_name: str
    account_number: str
    balance: float
    transactions: List[Dict[str, Any]]


class PurchaseOrder(BaseModel):
    po_number: str
    supplier: str
    total_amount: float
    items: List[Dict[str, Any]]


class Receipt(BaseModel):
    merchant: str
    total: float
    date: str
    items: List[str]


class InsuranceClaim(BaseModel):
    policy_number: str
    claimant_name: str
    claim_amount: float
    status: str


SCHEMA_MAP: Dict[str, type[BaseModel]] = {
    "ClinicalSummary": ClinicalSummary,
    "MedicationDosage": MedicationDosage,
    "Invoice": Invoice,
    "BankStatement": BankStatement,
    "PurchaseOrder": PurchaseOrder,
    "Receipt": Receipt,
    "InsuranceClaim": InsuranceClaim,
}


# ═══════════════════════════════════════════════════════════════
# Input / Output Contracts
# ═══════════════════════════════════════════════════════════════

class GuardrailDocumentContext(BaseModel):
    """Metadata from IDPO about the document being validated."""
    doc_type: DocumentType = Field(..., description="The type of document.")
    vendor: Optional[str] = Field(None, description="Vendor or source name for domain-rule matching.")
    quality_bin: Optional[str] = Field(None, description="OCR quality hint (high/medium/low).")


class RAGInput(BaseModel):
    """Input contract from IDPO — the payload we validate."""
    document_context: GuardrailDocumentContext
    query: str = Field(..., description="The original user query or prompt.")
    answer_json: str = Field(..., description="Extracted data as JSON string (this is what we validate).")
    source_contexts: List[str] = Field(..., description="Retrieved source text chunks (for faithfulness check).")
    document_id: Optional[str] = Field(None, description="Unique document identifier for traceability.")


class ValidationMetric(BaseModel):
    """Result of a single guardrail check."""
    name: str = Field(..., description="Check name (e.g. 'pii_leakage').")
    score: float = Field(..., description="Numeric score (0.0 = fail, 1.0 = pass, 0.5 = suspicious).")
    is_pass: bool = Field(..., description="Whether the check passed.")
    details: str = Field(..., description="Human-readable explanation.")
    timestamp: datetime = Field(default_factory=datetime.now)


class GuardrailOutput(BaseModel):
    """Final response — sent back to IDPO / dashboard."""
    rag_input: RAGInput
    validation_results: List[ValidationMetric]
    overall_passes: bool = Field(..., description="True only if ALL checks passed.")
    audit_log_id: str
    processing_time_ms: float
    timestamp: datetime = Field(default_factory=datetime.now)
    advice_id: str
    metrics: Dict[str, Any] = Field(default_factory=dict)

"""
PEAK UPGRADE – February 2026
- Strictly financial documents only (no medical)
- All schemas allow extra fields (dynamic IDPO support)
- Required fields centralized for easy maintenance
"""

from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Type, Any
from datetime import datetime
from enum import Enum


class DocumentType(str, Enum):
    """Only financial document types are supported."""
    INVOICE          = "Invoice"
    RECEIPT          = "Receipt"
    PURCHASE_ORDER   = "PurchaseOrder"
    BANK_STATEMENT   = "BankStatement"
    INSURANCE_CLAIM  = "InsuranceClaim"


class DocumentContext(BaseModel):
    doc_type: DocumentType = Field(..., description="Document category from IDPO")
    vendor: Optional[str] = Field(None, description="Vendor/supplier name – used for mismatch checks")
    quality_bin: Optional[str] = Field(None, description="OCR quality hint (future use)")


class RAGInput(BaseModel):
    """Input contract from IDPO – must match this structure."""
    document_context: DocumentContext
    query: str
    answer_json: str                        # JSON string from extraction
    source_contexts: List[str]              # Ground truth chunks
    document_id: Optional[str] = None

    model_config = ConfigDict(extra='allow', protected_namespaces=())


class ValidationMetric(BaseModel):
    """Single check result – used in ensemble output."""
    name: str
    score: float                # 0.0–1.0
    is_pass: bool
    details: str
    timestamp: datetime = Field(default_factory=datetime.now)


class GuardrailOutput(BaseModel):
    """Final API response shape – rich for XAI/dashboard."""
    rag_input: RAGInput
    validation_results: List[ValidationMetric]
    overall_passes: bool
    hallucination_detected: bool = False
    risk_level: str                         # LOW / MEDIUM / HIGH
    audit_log_id: str
    processing_time_ms: float
    timestamp: datetime = Field(default_factory=datetime.now)
    advice_id: str
    metrics: Dict[str, Any] = Field(default_factory=dict)


# ────────────────────────────────────────────────
# Per-type minimal schemas – extras always allowed
# ────────────────────────────────────────────────
class Invoice(BaseModel):
    model_config = ConfigDict(extra='allow')
    customer_name: str
    subtotal: float
    tax: Optional[float] = None
    total: float


class Receipt(BaseModel):
    model_config = ConfigDict(extra='allow')
    merchant: str
    total: float
    date: str


class PurchaseOrder(BaseModel):
    model_config = ConfigDict(extra='allow')
    po_number: str
    supplier: str
    total_amount: float


class BankStatement(BaseModel):
    model_config = ConfigDict(extra='allow')
    account_holder: str
    bank_name: str
    balance: float


class InsuranceClaim(BaseModel):
    model_config = ConfigDict(extra='allow')
    policy_number: str
    claimant_name: str
    claim_amount: float


SCHEMA_MAP: Dict[str, Type[BaseModel]] = {
    DocumentType.INVOICE.value:         Invoice,
    DocumentType.RECEIPT.value:         Receipt,
    DocumentType.PURCHASE_ORDER.value:  PurchaseOrder,
    DocumentType.BANK_STATEMENT.value:  BankStatement,
    DocumentType.INSURANCE_CLAIM.value: InsuranceClaim,
}


# Used in schema_adherence check
REQUIRED_FIELDS: Dict[str, List[str]] = {
    DocumentType.INVOICE.value:         ["customer_name", "subtotal", "total"],
    DocumentType.RECEIPT.value:         ["merchant", "total", "date"],
    DocumentType.PURCHASE_ORDER.value:  ["po_number", "supplier", "total_amount"],
    DocumentType.BANK_STATEMENT.value:  ["account_holder", "bank_name", "balance"],
    DocumentType.INSURANCE_CLAIM.value: ["policy_number", "claimant_name", "claim_amount"],
}
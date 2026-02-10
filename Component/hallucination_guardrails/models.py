from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

# Enum for supported document types (from project proposal)
# These match the 7 document types in the modular multi-agent system
class DocumentType(str, Enum):
    CLINICAL_SUMMARY = "ClinicalSummary"
    MEDICATION_DOSAGE = "MedicationDosage"
    INVOICE = "Invoice"
    INSURANCE_CLAIM = "InsuranceClaim"
    BANK_STATEMENT = "BankStatement"
    PURCHASE_ORDER = "PurchaseOrder"
    RECEIPT = "Receipt"

# Metadata from IDPO about the document
# vendor: optional seller/supplier name for domain rule matching
# quality_bin: optional OCR quality hint (high/medium/low) for future suspicion adjustment
class DocumentContext(BaseModel):
    doc_type: DocumentType = Field(..., description="The type of document.")
    vendor: Optional[str] = Field(None, description="The vendor or source (e.g. seller/supplier name).")
    quality_bin: Optional[str] = Field(None, description="The quality of the scan (high/medium/low).")

# Input model from IDPO – this is the contract for integration
class RAGInput(BaseModel):
    document_context: DocumentContext = Field(..., description="The IDPO's analysis of the document.")
    query: str = Field(..., description="The original user query or prompt (for logging/audit).")
    answer_json: str = Field(..., description="The final extracted data as JSON string (this is what we validate).")
    source_contexts: List[str] = Field(..., description="Retrieved source text chunks from the document (used for faithfulness check).")
    document_id: Optional[str] = Field(None, description="Unique identifier for the document (for traceability).")

    class Config:
        # These examples appear as a dropdown in Swagger UI (/docs) – great for demo/testing
        schema_extra = {
            "examples": [
                {
                    "summary": "1. Good Clinical Summary (mostly passes)",
                    "description": "Clean medical summary - should pass most checks",
                    "value": {
                        "document_context": {
                            "doc_type": "ClinicalSummary",
                            "vendor": None,
                            "quality_bin": None
                        },
                        "query": "Summarize patient condition",
                        "answer_json": "{\"patient_name\": \"John Doe\", \"condition\": \"Stable\", \"summary\": \"Routine checkup, no issues\", \"next_steps\": \"Follow-up in 6 months\"}",
                        "source_contexts": ["Patient John Doe is stable with no issues noted."],
                        "document_id": "good_clinical_1"
                    }
                },
                {
                    "summary": "2. Suspicious Tax & Keyword (Invoice)",
                    "description": "Triggers implausible tax rate (40%) + suspicious keyword 'Test'",
                    "value": {
                        "document_context": {
                            "doc_type": "Invoice",
                            "vendor": "Expected Vendor Ltd",
                            "quality_bin": "high"
                        },
                        "query": "Extract invoice details",
                        "answer_json": "{\"customer_name\": \"Test Customer\", \"subtotal\": 100.0, \"tax\": 40.0, \"total\": 140.0}",
                        "source_contexts": ["Invoice to Test Customer ... Subtotal: 100.00 ... Tax: 40.00 ... Total: 140.00 ..."],
                        "document_id": "suspicious_tax_test"
                    }
                },
                # Add more examples here as needed
            ]
        }

# Individual check result – returned as list in GuardrailOutput
class ValidationMetric(BaseModel):
    name: str = Field(..., description="Name of the metric/check (e.g. 'pii_leakage').")
    score: float = Field(..., description="Numeric score (0.0 = fail, 1.0 = pass, 0.5 = partial/suspicious).")
    is_pass: bool = Field(..., description="Whether the check passed (true/false).")
    details: str = Field(..., description="Human-readable explanation of the result.")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the check was performed.")

# Final response model sent back to IDPO/dashboard
class GuardrailOutput(BaseModel):
    rag_input: RAGInput = Field(..., description="Echo of the input received (for audit trail).")
    validation_results: List[ValidationMetric] = Field(..., description="Detailed results from all 5 checks.")
    overall_passes: bool = Field(..., description="True only if ALL checks passed (main decision flag).")
    audit_log_id: str = Field(..., description="Unique ID for this validation run (for logging/tracing).")
    processing_time_ms: float = Field(..., description="How long the validation took (performance metric).")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the response was generated.")
    advice_id: str = Field(..., description="Same as audit_log_id – used for evaluation/advice context.")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Summary scores for monitoring/reporting.")

# Pydantic schemas for each document type – used for schema_adherence check
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

# Map doc_type string → Pydantic model class
SCHEMA_MAP: Dict[str, Any] = {
    "ClinicalSummary": ClinicalSummary,
    "MedicationDosage": MedicationDosage,
    "Invoice": Invoice,
    "BankStatement": BankStatement,
    "PurchaseOrder": PurchaseOrder,
    "Receipt": Receipt,
    "InsuranceClaim": InsuranceClaim,
}
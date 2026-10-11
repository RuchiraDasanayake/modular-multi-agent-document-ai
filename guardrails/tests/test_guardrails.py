"""
Tests for the guardrails validation ensemble.

Covers all 5 layers:
  1. Schema Adherence
  2. Internal Consistency
  3. Domain Rules
  4. PII Leakage
  5. Faithfulness
"""

import json
import pytest

from guardrails.models import (
    DocumentType,
    GuardrailDocumentContext,
    RAGInput,
    ValidationMetric,
    SCHEMA_MAP,
)
from guardrails.core.ensemble import run_validation_ensemble
from guardrails.core.validation import (
    check_schema_adherence,
    check_internal_consistency,
    check_domain_rules,
    check_pii_leakage,
    check_faithfulness,
)

# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _ctx(doc_type: str = "Invoice", vendor: str | None = None) -> GuardrailDocumentContext:
    return GuardrailDocumentContext(doc_type=DocumentType(doc_type), vendor=vendor, quality_bin=None)  # type: ignore[call-arg]

def _rag(doc_type: str, answer: dict, sources: list[str] | None = None, vendor: str | None = None) -> RAGInput:
    return RAGInput(
        document_context=_ctx(doc_type, vendor),
        query="test query",
        answer_json=json.dumps(answer),
        source_contexts=sources or ["source text"],
        document_id="test-001",
    )

# ═══════════════════════════════════════════════════════════════
# 1. Schema Adherence
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_schema_adherence_valid_invoice():
    result = await check_schema_adherence(
        json.dumps({"customer_name": "Jane", "subtotal": 100, "tax": 10, "total": 110}),
        "Invoice",
    )
    assert result.is_pass
    assert result.score == 1.0

@pytest.mark.asyncio
async def test_schema_adherence_partial_invoice_is_allowed():
    result = await check_schema_adherence(
        json.dumps({"customer_name": "Jane", "subtotal": 100}),
        "Invoice",
    )
    assert result.is_pass

@pytest.mark.asyncio
async def test_schema_adherence_malformed_json_fails():
    result = await check_schema_adherence('{"customer_name": "Jane", ', "Invoice")
    assert not result.is_pass
    assert result.score == 0.0

@pytest.mark.asyncio
async def test_schema_adherence_unknown_type_is_skipped():
    result = await check_schema_adherence('{"key": "val"}', "UnknownType")
    assert result.score == 0.5
    assert "No schema defined" in result.details

# ═══════════════════════════════════════════════════════════════
# 2. Internal Consistency
# ═══════════════════════════════════════════════════════════════

def test_consistency_invoice_math_correct():
    from guardrails.models import Invoice
    data = Invoice(customer_name="A", subtotal=100, tax=10, total=110)
    result = check_internal_consistency(data, _ctx("Invoice"))
    assert result.is_pass

def test_consistency_invoice_math_wrong():
    from guardrails.models import Invoice
    data = Invoice(customer_name="A", subtotal=100, tax=10, total=120)
    result = check_internal_consistency(data, _ctx("Invoice"))
    assert not result.is_pass
    assert "does not match" in result.details

def test_consistency_invoice_negative_total():
    from guardrails.models import Invoice
    data = Invoice(customer_name="A", subtotal=100, tax=10, total=-5)
    result = check_internal_consistency(data, _ctx("Invoice"))
    assert not result.is_pass

def test_consistency_medication_zero_dosage():
    from guardrails.models import MedicationDosage
    data = MedicationDosage(medication="Drug", dosage_mg=0, frequency="daily", reason="test")
    result = check_internal_consistency(data, _ctx("MedicationDosage"))
    assert not result.is_pass
    assert "dosage_mg" in result.details

def test_consistency_receipt_empty_merchant():
    from guardrails.models import Receipt
    data = Receipt(merchant="   ", total=50, date="2025-01-01", items=["ItemA"])
    result = check_internal_consistency(data, _ctx("Receipt"))
    assert not result.is_pass
    assert "merchant" in result.details

# ═══════════════════════════════════════════════════════════════
# 3. Domain Rules
# ═══════════════════════════════════════════════════════════════

def test_domain_rules_implausible_tax():
    from guardrails.models import Invoice
    data = Invoice(customer_name="Jane", subtotal=100, tax=40, total=140)
    result = check_domain_rules(data, _ctx("Invoice"))
    assert not result.is_pass
    assert "tax rate" in result.details.lower()

def test_domain_rules_suspicious_keyword():
    from guardrails.models import Invoice
    data = Invoice(customer_name="Dummy Customer", subtotal=100, tax=10, total=110)
    result = check_domain_rules(data, _ctx("Invoice"))
    assert not result.is_pass
    assert "Suspicious keyword" in result.details

def test_domain_rules_clean_invoice():
    from guardrails.models import Invoice
    data = Invoice(customer_name="Real Corp", subtotal=100, tax=15, total=115)
    result = check_domain_rules(data, _ctx("Invoice"))
    assert result.is_pass

def test_domain_rules_vendor_in_customer():
    from guardrails.models import Invoice
    data = Invoice(customer_name="ABC Supplies Ltd", subtotal=100, tax=10, total=110)
    result = check_domain_rules(data, _ctx("Invoice", vendor="ABC Supplies"))
    assert not result.is_pass

# ═══════════════════════════════════════════════════════════════
# 4. PII Leakage
# ═══════════════════════════════════════════════════════════════

def test_pii_no_leakage():
    result = check_pii_leakage('{"total": 100, "tax": 10}', "Invoice")
    assert result.is_pass

def test_pii_medical_allowed():
    result = check_pii_leakage('{"patient_name": "John Doe", "condition": "Stable"}', "ClinicalSummary")
    assert result.is_pass

# ═══════════════════════════════════════════════════════════════
# 5. Ensemble Integration
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ensemble_good_clinical():
    rag = _rag(
        "ClinicalSummary",
        {"patient_name": "John Doe", "condition": "Stable", "summary": "Routine checkup", "next_steps": "Follow-up"},
        ["Patient John Doe is stable with no issues noted."],
    )
    results = await run_validation_ensemble(rag)
    assert len(results) >= 3
    schema = next(r for r in results if r.name == "schema_adherence")
    assert schema.is_pass

@pytest.mark.asyncio
async def test_ensemble_bad_invoice_math():
    rag = _rag(
        "Invoice",
        {"customer_name": "Real Corp", "subtotal": 100, "tax": 10, "total": 120},
        ["Subtotal 100, tax 10, total 110"],
    )
    results = await run_validation_ensemble(rag)
    consistency = next((r for r in results if r.name == "internal_consistency"), None)
    assert consistency is not None
    assert not consistency.is_pass

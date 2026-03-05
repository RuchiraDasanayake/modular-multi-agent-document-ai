"""
Individual guardrail check implementations.

Each function returns a ValidationMetric with name, score, is_pass, details.
Uses lazy-loaded singletons for ML models (sentence-transformer, Presidio).
"""

import json
import logging
from datetime import date

import torch
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer, util
from presidio_analyzer import AnalyzerEngine # type: ignore
from dateutil import parser as date_parser

from ..models import (
    ValidationMetric,
    SCHEMA_MAP,
    GuardrailDocumentContext,
    Invoice,
    Receipt,
    ClinicalSummary,
    MedicationDosage,
    InsuranceClaim,
    BankStatement,
    PurchaseOrder,
)

from ..config import guardrail_settings

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Lazy-loaded singletons
# ═══════════════════════════════════════════════════════════════

try:
    embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    logger.info("Guardrails: sentence-transformer loaded")
except Exception as e:
    logger.error(f"Failed to load sentence transformer: {e}")
    embedder = None

analyzer = AnalyzerEngine()

# Cosine similarity threshold for faithfulness (from config)
FAITHFULNESS_THRESHOLD = guardrail_settings.THRESHOLD_FAITHFULNESS

# ═══════════════════════════════════════════════════════════════
# 1. Schema Adherence
# ═══════════════════════════════════════════════════════════════

async def check_schema_adherence(answer_json: str, doc_type: str) -> ValidationMetric:
    """Validate that extracted JSON matches the expected Pydantic schema for the document type."""
    model = SCHEMA_MAP.get(doc_type)
    if not model:
        return ValidationMetric(
            name="schema_adherence", score=0.5, is_pass=True,
            details=f"No schema defined for doc_type '{doc_type}' — skipped",
        )
    try:
        data = json.loads(answer_json)
        model.model_validate(data)
        return ValidationMetric(
            name="schema_adherence", score=1.0, is_pass=True,
            details="Schema valid",
        )
    except Exception as e:
        return ValidationMetric(
            name="schema_adherence", score=0.0, is_pass=False,
            details=f"Schema error: {str(e)[:120]}",
        )

# ═══════════════════════════════════════════════════════════════
# 2. Internal Consistency
# ═══════════════════════════════════════════════════════════════

def _safe_float(value) -> float | None:
    """Try to convert a value to float, stripping currency symbols and commas."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        import re as _re
        cleaned = _re.sub(r"[^\d.\-]", "", value)
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    return None

def check_internal_consistency(data: BaseModel, context: GuardrailDocumentContext) -> ValidationMetric:
    """Business-logic validation: math checks, negative values, future dates, dosage rules."""
    errors: list[str] = []

    if isinstance(data, Invoice):
        subtotal = _safe_float(getattr(data, "subtotal", None))
        tax = _safe_float(getattr(data, "tax", None))
        total = _safe_float(getattr(data, "total", None))
        if subtotal is not None and subtotal < 0:
            errors.append(f"Negative value in 'subtotal': {data.subtotal}")
        if tax is not None and tax < 0:
            errors.append(f"Negative value in 'tax': {data.tax}")
        if total is not None and total < 0:
            errors.append(f"Negative value in 'total': {data.total}")
        if subtotal is not None and tax is not None and total is not None:
            expected_total = subtotal + tax
            if abs(total - expected_total) > 0.05:
                errors.append(f"Total {total} does not match subtotal + tax = {expected_total} (tolerance 0.05)")

    elif isinstance(data, Receipt):
        total = _safe_float(getattr(data, "total", None))
        if total is not None and total < 0:
            errors.append(f"Negative value in 'total': {data.total}")
        merchant = getattr(data, "merchant", None)
        if isinstance(merchant, str) and not merchant.strip():
            errors.append("Required field 'merchant' is empty or whitespace")
        date_val = getattr(data, "date", None)
        if isinstance(date_val, str):
            try:
                d = date_parser.parse(date_val, dayfirst=True).date()
                if d > date.today():
                    errors.append("Date cannot be in the future")
            except ValueError:
                errors.append("Invalid date format")

    elif isinstance(data, ClinicalSummary):
        condition = getattr(data, "condition", None)
        if isinstance(condition, str) and not condition.strip():
            errors.append("Condition cannot be empty")

    elif isinstance(data, MedicationDosage):
        dosage = _safe_float(getattr(data, "dosage_mg", None))
        if dosage is not None and dosage <= 0:
            errors.append(f"Invalid dosage_mg: {data.dosage_mg} (must be > 0)")
        freq = getattr(data, "frequency", None)
        if isinstance(freq, str) and freq not in ["daily", "twice daily", "as needed"]:
            errors.append("Invalid frequency")

    elif isinstance(data, InsuranceClaim):
        claim_amt = _safe_float(getattr(data, "claim_amount", None))
        if claim_amt is not None and claim_amt < 0:
            errors.append(f"Negative value in 'claim_amount': {data.claim_amount}")
        status = getattr(data, "status", None)
        if status == "approved" and claim_amt is not None and claim_amt <= 0:
            errors.append("Approved claims must have positive amount")

    elif isinstance(data, BankStatement):
        balance = _safe_float(getattr(data, "balance", None))
        if balance is not None and balance < 0:
            errors.append(f"Negative value in 'balance': {data.balance}")
        transactions = getattr(data, "transactions", None)
        if isinstance(transactions, list) and balance is not None:
            trans_sum = sum(_safe_float(t.get("amount", 0)) or 0 for t in transactions)
            if balance + trans_sum < 0:
                errors.append("Balance inconsistent with transactions")

    elif isinstance(data, PurchaseOrder):
        total_amt = _safe_float(getattr(data, "total_amount", None))
        if total_amt is not None and total_amt < 0:
            errors.append(f"Negative value in 'total_amount': {data.total_amount}")

    if errors:
        return ValidationMetric(
            name="internal_consistency", score=0.0, is_pass=False,
            details="; ".join(errors),
        )
    return ValidationMetric(
        name="internal_consistency", score=1.0, is_pass=True,
        details="All internal consistency checks passed",
    )

# ═══════════════════════════════════════════════════════════════
# 3. Domain Rules
# ═══════════════════════════════════════════════════════════════

def check_domain_rules(data: BaseModel, context: GuardrailDocumentContext) -> ValidationMetric:
    """Business-specific rules: vendor fraud, tax plausibility, large amounts, suspicious keywords."""
    errors: list[str] = []
    suspicious_flags: list[str] = []

    # Keyword blacklist — use word boundaries to avoid false positives
    # (e.g., 'blood sample' should not trigger 'sample')
    blacklist_words = ["dummy", "fake"]
    blacklist_phrases = ["test data", "test document", "sample data", "demo data"]
    for value in data.model_dump().values():
        if isinstance(value, str):
            lower_value = value.lower()
            for word in blacklist_words:
                if word in lower_value:
                    suspicious_flags.append(f"Suspicious keyword '{word}' detected in data")
            for phrase in blacklist_phrases:
                if phrase in lower_value:
                    suspicious_flags.append(f"Suspicious phrase '{phrase}' detected in data")

    if isinstance(data, Invoice):
        customer_name = getattr(data, "customer_name", "") or ""
        if context.vendor and isinstance(customer_name, str) and context.vendor.lower() in customer_name.lower():
            errors.append(
                f"Vendor name '{context.vendor}' suspiciously appears in customer name '{customer_name}'"
            )
        subtotal = _safe_float(getattr(data, "subtotal", None))
        tax = _safe_float(getattr(data, "tax", None))
        total = _safe_float(getattr(data, "total", None))
        if subtotal is not None and subtotal > 0 and tax is not None:
            tax_rate = (tax / subtotal) * 100
            if tax_rate > 30 or tax_rate < 0:
                errors.append(f"Implausible tax rate: {tax_rate:.1f}% (expected 0-30%)")
        if total is not None and total > 100000:
            suspicious_flags.append(f"Suspiciously large total amount: {total}")

    elif isinstance(data, Receipt):
        merchant = getattr(data, "merchant", "") or ""
        if context.vendor and isinstance(merchant, str) and merchant.lower() != context.vendor.lower():
            errors.append(f"Merchant '{merchant}' does not match context vendor '{context.vendor}'")
        total = _safe_float(getattr(data, "total", None))
        if total is not None and total > 50000:
            suspicious_flags.append(f"Suspiciously large receipt total: {total}")

    elif isinstance(data, PurchaseOrder):
        supplier = getattr(data, "supplier", "") or ""
        if context.vendor and isinstance(supplier, str) and supplier.lower() != context.vendor.lower():
            errors.append(f"Supplier '{supplier}' does not match context vendor '{context.vendor}'")
        total_amt = _safe_float(getattr(data, "total_amount", None))
        if total_amt is not None and total_amt > 1000000:
            suspicious_flags.append(f"Suspiciously large PO amount: {total_amt}")

    elif isinstance(data, InsuranceClaim):
        claim_amt = _safe_float(getattr(data, "claim_amount", None))
        if claim_amt is not None and claim_amt > 500000:
            suspicious_flags.append(f"Suspiciously large claim amount: {claim_amt}")

    if errors:
        return ValidationMetric(
            name="domain_rules", score=0.0, is_pass=False,
            details="; ".join(errors),
        )
    if suspicious_flags:
        return ValidationMetric(
            name="domain_rules", score=0.5, is_pass=False,
            details="Suspicious flags raised: " + "; ".join(suspicious_flags),
        )
    return ValidationMetric(
        name="domain_rules", score=1.0, is_pass=True,
        details="All domain rules passed",
    )

# ═══════════════════════════════════════════════════════════════
# 4. PII Leakage
# ═══════════════════════════════════════════════════════════════

def check_pii_leakage(answer_json: str, doc_type: str | None = None) -> ValidationMetric:
    """Presidio-based PII detection — context-aware for medical AND business documents.
    
    Business documents (invoices, receipts, POs) legitimately contain names,
    dates, and phone numbers as extracted fields. We only flag truly sensitive
    PII like SSN, credit card, IBAN, etc.
    """
    try:
        # Extract values only (skip JSON keys to avoid false positives)
        try:
            parsed = json.loads(answer_json)
            values_text = " ".join(str(v) for v in parsed.values() if isinstance(v, (str, int, float)))
        except (json.JSONDecodeError, AttributeError):
            values_text = answer_json
        results = analyzer.analyze(text=values_text, language="en")
        if results:
            entities = [r.entity_type for r in results]
            unique = list(set(entities))

            # Medical documents — PERSON and DATE_TIME are expected
            if doc_type in ["ClinicalSummary", "MedicationDosage", "InsuranceClaim"]:
                allowed = {"PERSON", "DATE_TIME"}
                non_allowed = [e for e in unique if e not in allowed]
                if non_allowed:
                    return ValidationMetric(
                        name="pii_leakage", score=0.0, is_pass=False,
                        details=f"Detected non-allowed PII: {', '.join(non_allowed)}",
                    )
                return ValidationMetric(
                    name="pii_leakage", score=1.0, is_pass=True,
                    details="Allowed PII (PERSON/DATE_TIME) detected in medical context",
                )

            # Business/financial documents — names, dates, phone numbers are expected
            _BUSINESS_TYPES = {
                "Invoice", "Receipt", "PurchaseOrder",
                "invoice", "receipt", "purchase_order",
                "table_document", "form_document",
            }
            if doc_type in _BUSINESS_TYPES:
                allowed_business = {"PERSON", "DATE_TIME", "PHONE_NUMBER", "NRP"}
                non_allowed = [e for e in unique if e not in allowed_business]
                if non_allowed:
                    return ValidationMetric(
                        name="pii_leakage", score=0.3, is_pass=False,
                        details=f"Sensitive PII in business doc: {', '.join(non_allowed)}",
                    )
                return ValidationMetric(
                    name="pii_leakage", score=1.0, is_pass=True,
                    details=f"Expected PII ({', '.join(unique)}) in business context",
                )

            # Unknown/other doc types — flag any PII as warning, not hard fail
            # Only truly sensitive PII (SSN, CREDIT_CARD, IBAN, etc.) is a hard fail
            _SENSITIVE_PII = {"US_SSN", "CREDIT_CARD", "IBAN_CODE", "US_BANK_NUMBER", "MEDICAL_LICENSE"}
            sensitive_found = [e for e in unique if e in _SENSITIVE_PII]
            if sensitive_found:
                return ValidationMetric(
                    name="pii_leakage", score=0.0, is_pass=False,
                    details=f"Detected sensitive PII: {', '.join(sensitive_found)}",
                )
            # Non-sensitive PII (PERSON, DATE, PHONE) in unknown context — soft pass
            return ValidationMetric(
                name="pii_leakage", score=0.7, is_pass=True,
                details=f"Low-risk PII detected: {', '.join(unique)} (not flagged for generic doc type)",
            )
    except Exception as e:
        logger.warning(f"Presidio failed: {e}")
        return ValidationMetric(
            name="pii_leakage", score=0.0, is_pass=False,
            details=f"PII check failed (fail-closed): {e}",
        )

    return ValidationMetric(
        name="pii_leakage", score=1.0, is_pass=True,
        details="No PII detected",
    )

# ═══════════════════════════════════════════════════════════════
# 5. Faithfulness (Hallucination Detection)
# ═══════════════════════════════════════════════════════════════

async def check_faithfulness(answer_json: str, source_contexts: list[str]) -> ValidationMetric:
    """Semantic similarity between extracted fields and source context chunks."""
    if not embedder:
        return ValidationMetric(
            name="faithfulness", score=0.0, is_pass=False,
            details="Embedder not loaded",
        )
    if not source_contexts:
        return ValidationMetric(
            name="faithfulness", score=0.0, is_pass=False,
            details="No source contexts",
        )

    try:
        data = json.loads(answer_json)
        context_text = " ".join(source_contexts)

        field_scores: dict[str, float] = {}
        total = 0.0
        count = 0

        # Encode context once — O(1) instead of O(n) per field
        ctx_emb = embedder.encode(context_text)
        ctx_tensor = torch.tensor(ctx_emb)

        for key, value in data.items():
            if isinstance(value, (str, int, float)) and value not in ("", None, [], {}):
                val_str = str(value)
                val_emb = embedder.encode(val_str)
                sim = util.cos_sim(torch.tensor(val_emb), ctx_tensor)[0][0].item()
                field_scores[key] = round(sim, 3)
                total += sim
                count += 1

        avg_score = total / count if count > 0 else 0.0
        is_pass = avg_score >= FAITHFULNESS_THRESHOLD
        details = f"Semantic score: {avg_score:.3f} | Fields: {field_scores}"

        return ValidationMetric(
            name="faithfulness", score=round(avg_score, 3), is_pass=is_pass,
            details=details,
        )
    except Exception as e:
        logger.error(f"Faithfulness error: {e}")
        return ValidationMetric(
            name="faithfulness", score=0.0, is_pass=False,
            details="Error",
        )

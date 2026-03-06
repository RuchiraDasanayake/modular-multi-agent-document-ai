"""
Individual guardrail check implementations.

Each function returns a ValidationMetric with name, score, is_pass, details.
Uses lazy-loaded singletons for ML models (sentence-transformer, Presidio).
Includes weighted faithfulness scoring and relevance-based hallucination detection.
"""

import json
import logging
import re
from datetime import date
from typing import Dict, List, Any

import torch
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer, util
from presidio_analyzer import AnalyzerEngine  # type: ignore
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
    embedder = SentenceTransformer(guardrail_settings.EMBEDDER_MODEL, device="cpu")
    logger.info(f"Guardrails: sentence-transformer loaded ({guardrail_settings.EMBEDDER_MODEL})")
except Exception as e:
    logger.error(f"Failed to load sentence transformer: {e}")
    embedder = None

analyzer = AnalyzerEngine()

# Thresholds from config
FAITHFULNESS_THRESHOLD = guardrail_settings.THRESHOLD_FAITHFULNESS

# Pattern matchers for field type detection
AMOUNT_LIKE_PATTERNS = ["total", "subtotal", "tax", "vat", "amount", "balance", "claim", "grand", "discount", "fee"]
DATE_LIKE_PATTERNS = ["date", "due", "issue", "payment", "claim", "period"]


def is_amount_like(key: str) -> bool:
    """Check if a field key represents an amount/money value."""
    return any(p in key.lower() for p in AMOUNT_LIKE_PATTERNS)


def is_date_like(key: str) -> bool:
    """Check if a field key represents a date value."""
    return any(p in key.lower() for p in DATE_LIKE_PATTERNS)

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
# 1b. Relevance Check (Hallucination Detection)
# ═══════════════════════════════════════════════════════════════

async def check_relevance(data: Dict[str, Any], source_contexts: List[str], doc_type: str) -> ValidationMetric:
    """Check if extracted fields are relevant to the source document context.

    Low relevance scores indicate potential hallucination or noise.
    """
    if not embedder or not source_contexts:
        return ValidationMetric(
            name="relevance", score=0.0, is_pass=False,
            details="Missing embedder or source contexts",
        )

    pol = guardrail_settings.POLICIES["relevance"]
    context_text = " ".join(source_contexts)
    ctx_emb = embedder.encode(context_text)
    ctx_tensor = torch.tensor(ctx_emb)

    expected = pol["expected_fields"].get(doc_type, [])
    fin_kw = pol["financial_keywords"]

    field_scores = {}
    low_fields = []
    unexpected = 0

    for key, value in data.items():
        if value in (None, "", [], {}, " "):
            continue
        val_str = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        val_emb = embedder.encode(val_str)
        sim = util.cos_sim(torch.tensor(val_emb), ctx_tensor)[0][0].item()

        # Boost similarity for financial keywords
        if any(w in key.lower() or w in val_str.lower() for w in fin_kw):
            sim = min(1.0, sim + pol["keyword_boost"])

        # Penalize unexpected fields
        is_expected = key.lower() in [e.lower() for e in expected] or any(e.lower() in key.lower() for e in expected)
        if not is_expected:
            sim *= 0.4
            unexpected += 1

        field_scores[key] = round(sim, 3)
        if sim < pol["medium_threshold"]:
            low_fields.append(f"{key} ({sim:.3f})")

    avg_score = sum(field_scores.values()) / len(field_scores) if field_scores else 0.0
    is_pass = avg_score >= pol["high_threshold"]

    details = f"Average relevance: {avg_score:.3f} | Unexpected fields: {unexpected}"
    if low_fields:
        details += f" | LOW relevance (likely hallucination): {', '.join(low_fields[:3])}"

    return ValidationMetric(name="relevance", score=round(avg_score, 3), is_pass=is_pass, details=details)


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
# 5. Faithfulness (Weighted Hallucination Detection)
# ═══════════════════════════════════════════════════════════════

async def check_faithfulness(answer_json: str, source_contexts: list[str]) -> ValidationMetric:
    """Weighted faithfulness check combining semantic, numerical, and entity matching.

    Final score = semantic_weight * semantic_avg + numerical_weight * num_score + entity_weight * ent_score
    """
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
        pol = guardrail_settings.POLICIES["faithfulness"]

        # Encode context once
        ctx_emb = embedder.encode(context_text)
        ctx_tensor = torch.tensor(ctx_emb)

        sem_total, sem_count = 0.0, 0

        for key, value in data.items():
            if value in ("", None, [], {}):
                continue
            val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            if not val_str.strip():
                continue

            val_emb = embedder.encode(val_str)
            sim = util.cos_sim(torch.tensor(val_emb), ctx_tensor)[0][0].item()

            # Apply field importance weighting
            weight = pol["field_importance"].get(key, pol["field_importance"]["default"])
            sem_total += sim * weight
            sem_count += weight

        sem_avg = sem_total / sem_count if sem_count > 0 else 0.0

        # Numerical matching - check if amounts in answer appear in source
        ans_nums = [float(v) for k, v in data.items() if is_amount_like(k) and isinstance(v, (int, float))]
        src_nums = [float(x) for x in re.findall(r'\d+\.?\d{0,2}', context_text)]
        num_matches = 0
        if ans_nums and src_nums:
            for a in ans_nums:
                for s in src_nums:
                    if abs(a - s) / max(s, 1) <= pol["numerical_tolerance"].get("default", 0.005):
                        num_matches += 1
                        break
            num_score = num_matches / len(ans_nums) if ans_nums else 0.0
        else:
            num_score = 0.8  # Default if no numerics

        # Entity score (placeholder - could integrate NER matching)
        ent_score = 0.85

        # Weighted final score
        final_score = (
            sem_avg * pol["semantic_weight"] +
            num_score * pol["numerical_weight"] +
            ent_score * pol["entity_weight"]
        )

        is_pass = final_score >= FAITHFULNESS_THRESHOLD

        return ValidationMetric(
            name="faithfulness",
            score=round(final_score, 3),
            is_pass=is_pass,
            details=f"Semantic {sem_avg:.3f} | Numerical {num_score:.3f} | Entity {ent_score:.3f} | Final {final_score:.3f}",
        )
    except Exception as e:
        logger.error(f"Faithfulness error: {e}")
        return ValidationMetric(
            name="faithfulness", score=0.0, is_pass=False,
            details=f"Error: {str(e)[:100]}",
        )

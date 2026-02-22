"""
Individual guardrail check implementations.

Each function returns a ValidationMetric with name, score, is_pass, details.
Uses lazy-loaded singletons for ML models (sentence-transformer, Presidio).
"""

import json
import logging
from datetime import date
from typing import Dict, List

import torch
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer, util
from presidio_analyzer import AnalyzerEngine
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
            name="schema_adherence", score=0.0, is_pass=False,
            details=f"Unknown doc_type '{doc_type}'",
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

def check_internal_consistency(data: BaseModel, context: GuardrailDocumentContext) -> ValidationMetric:
    """Business-logic validation: math checks, negative values, future dates, dosage rules."""
    errors: list[str] = []

    if isinstance(data, Invoice):
        if data.subtotal < 0:
            errors.append(f"Negative value in 'subtotal': {data.subtotal}")
        if data.tax < 0:
            errors.append(f"Negative value in 'tax': {data.tax}")
        if data.total < 0:
            errors.append(f"Negative value in 'total': {data.total}")
        expected_total = data.subtotal + data.tax
        if abs(data.total - expected_total) > 0.05:
            errors.append(f"Total {data.total} does not match subtotal + tax = {expected_total} (tolerance 0.05)")

    elif isinstance(data, Receipt):
        if data.total < 0:
            errors.append(f"Negative value in 'total': {data.total}")
        if not data.merchant.strip():
            errors.append("Required field 'merchant' is empty or whitespace")
        try:
            d = date_parser.parse(data.date, dayfirst=True).date()
            if d > date.today():
                errors.append("Date cannot be in the future")
        except ValueError:
            errors.append("Invalid date format")

    elif isinstance(data, ClinicalSummary):
        if not data.condition.strip():
            errors.append("Condition cannot be empty")

    elif isinstance(data, MedicationDosage):
        if data.dosage_mg <= 0:
            errors.append(f"Invalid dosage_mg: {data.dosage_mg} (must be > 0)")
        if data.frequency not in ["daily", "twice daily", "as needed"]:
            errors.append("Invalid frequency")

    elif isinstance(data, InsuranceClaim):
        if data.claim_amount < 0:
            errors.append(f"Negative value in 'claim_amount': {data.claim_amount}")
        if data.status == "approved" and data.claim_amount <= 0:
            errors.append("Approved claims must have positive amount")

    elif isinstance(data, BankStatement):
        if data.balance < 0:
            errors.append(f"Negative value in 'balance': {data.balance}")
        trans_sum = sum(t.get("amount", 0) for t in data.transactions)
        if data.balance + trans_sum < 0:
            errors.append("Balance inconsistent with transactions")

    elif isinstance(data, PurchaseOrder):
        if data.total_amount < 0:
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

    # Keyword blacklist
    blacklist_words = ["test", "sample", "dummy", "fake", "demo"]
    for value in data.model_dump().values():
        if isinstance(value, str):
            lower_value = value.lower()
            for word in blacklist_words:
                if word in lower_value:
                    suspicious_flags.append(f"Suspicious keyword '{word}' detected in data")

    if isinstance(data, Invoice):
        if context.vendor and context.vendor.lower() in data.customer_name.lower():
            errors.append(
                f"Vendor name '{context.vendor}' suspiciously appears in customer name '{data.customer_name}'"
            )
        if data.subtotal > 0:
            tax_rate = (data.tax / data.subtotal) * 100
            if tax_rate > 30 or tax_rate < 0:
                errors.append(f"Implausible tax rate: {tax_rate:.1f}% (expected 0-30%)")
        if data.total > 100000:
            suspicious_flags.append(f"Suspiciously large total amount: {data.total}")

    elif isinstance(data, Receipt):
        if context.vendor and data.merchant.lower() != context.vendor.lower():
            errors.append(f"Merchant '{data.merchant}' does not match context vendor '{context.vendor}'")
        if data.total > 50000:
            suspicious_flags.append(f"Suspiciously large receipt total: {data.total}")

    elif isinstance(data, PurchaseOrder):
        if context.vendor and data.supplier.lower() != context.vendor.lower():
            errors.append(f"Supplier '{data.supplier}' does not match context vendor '{context.vendor}'")
        if data.total_amount > 1000000:
            suspicious_flags.append(f"Suspiciously large PO amount: {data.total_amount}")

    elif isinstance(data, InsuranceClaim):
        if data.claim_amount > 500000:
            suspicious_flags.append(f"Suspiciously large claim amount: {data.claim_amount}")

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
    """Presidio-based PII detection — context-aware for medical vs business documents."""
    try:
        results = analyzer.analyze(text=answer_json, language="en")
        if results:
            entities = [r.entity_type for r in results]
            unique = list(set(entities))

            # Allow PERSON and DATE_TIME in medical documents
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

            # Business/finance docs — fail on any PII
            return ValidationMetric(
                name="pii_leakage", score=0.0, is_pass=False,
                details=f"Detected PII: {', '.join(unique)}",
            )
    except Exception as e:
        logger.warning(f"Presidio failed: {e}")

    return ValidationMetric(
        name="pii_leakage", score=1.0, is_pass=True,
        details="No PII detected",
    )


# ═══════════════════════════════════════════════════════════════
# 5. Faithfulness (Hallucination Detection)
# ═══════════════════════════════════════════════════════════════

async def check_faithfulness(answer_json: str, source_contexts: List[str]) -> ValidationMetric:
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

        field_scores: Dict[str, float] = {}
        total = 0.0
        count = 0

        for key, value in data.items():
            if isinstance(value, (str, int, float)) and value not in ("", None, [], {}):
                val_str = str(value)
                val_emb = embedder.encode(val_str)
                ctx_emb = embedder.encode(context_text)
                sim = util.cos_sim(torch.tensor(val_emb), torch.tensor(ctx_emb))[0][0].item()
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

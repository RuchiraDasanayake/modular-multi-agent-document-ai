import json
import logging
from typing import List, Dict
from datetime import date

import torch
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer, util
from presidio_analyzer import AnalyzerEngine
from dateutil import parser as date_parser

from ..models import ValidationMetric, SCHEMA_MAP, DocumentContext, Invoice, Receipt, ClinicalSummary, MedicationDosage, InsuranceClaim, BankStatement, PurchaseOrder

logger = logging.getLogger(__name__)

# Global embedder for faithfulness check (loaded once at startup)
try:
    embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    logger.info("✓ Sentence-Transformer model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load sentence transformer: {e}")
    embedder = None

# Presidio analyzer for PII detection (loaded once)
analyzer = AnalyzerEngine()

# Threshold for faithfulness (cosine similarity average)
# > 0.78 = grounded, < 0.78 = potential hallucination
FAITHFULNESS_THRESHOLD = 0.78

# 1. Schema Adherence Check
# Ensures the extracted JSON matches the expected structure/types for the doc_type
async def check_schema_adherence(answer_json: str, doc_type: str) -> ValidationMetric:
    model = SCHEMA_MAP.get(doc_type)
    if not model:
        return ValidationMetric(
            name="schema_adherence",
            score=0.0,
            is_pass=False,
            details=f"Unknown doc_type '{doc_type}'"
        )
    try:
        data = json.loads(answer_json)
        model.model_validate(data)  # Pydantic validation
        return ValidationMetric(
            name="schema_adherence",
            score=1.0,
            is_pass=True,
            details="Schema valid"
        )
    except Exception as e:
        return ValidationMetric(
            name="schema_adherence",
            score=0.0,
            is_pass=False,
            details=f"Schema error: {str(e)[:120]}"
        )

# 2. Internal Consistency Check
# Business/logical rules (math, negatives, empty fields, future dates, dosage > 0, etc.)
def check_internal_consistency(data: BaseModel, context: DocumentContext) -> ValidationMetric:
    errors = []
    
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
        if data.frequency not in ['daily', 'twice daily', 'as needed']:
            errors.append("Invalid frequency")
    
    elif isinstance(data, InsuranceClaim):
        if data.claim_amount < 0:
            errors.append(f"Negative value in 'claim_amount': {data.claim_amount}")
        if data.status == 'approved' and data.claim_amount <= 0:
            errors.append("Approved claims must have positive amount")
    
    elif isinstance(data, BankStatement):
        if data.balance < 0:
            errors.append(f"Negative value in 'balance': {data.balance}")
        trans_sum = sum(t.get('amount', 0) for t in data.transactions)
        if data.balance + trans_sum < 0:
            errors.append("Balance inconsistent with transactions")
    
    elif isinstance(data, PurchaseOrder):
        if data.total_amount < 0:
            errors.append(f"Negative value in 'total_amount': {data.total_amount}")
    
    if errors:
        return ValidationMetric(
            name="internal_consistency",
            score=0.0,
            is_pass=False,
            details="; ".join(errors)
        )
    return ValidationMetric(
        name="internal_consistency",
        score=1.0,
        is_pass=True,
        details="All internal consistency checks passed"
    )

# 3. Domain Rules Check
# Business-specific rules (vendor overlap/fraud, tax plausibility, large amounts, keyword suspicion)
def check_domain_rules(data: BaseModel, context: DocumentContext) -> ValidationMetric:
    errors = []
    suspicious_flags = []

    # Keyword blacklist – flags possible test/fake data
    blacklist_words = ["test", "sample", "dummy", "fake", "demo"]
    for value in data.model_dump().values():
        if isinstance(value, str):
            lower_value = value.lower()
            for word in blacklist_words:
                if word in lower_value:
                    suspicious_flags.append(f"Suspicious keyword '{word}' detected in data")

    if isinstance(data, Invoice):
        # Vendor logic – flag only if vendor name appears inside customer_name (possible fraud/test)
        # Normal invoices have vendor ≠ customer → no flag
        if context.vendor and context.vendor.lower() in data.customer_name.lower():
            errors.append(f"Vendor name '{context.vendor}' suspiciously appears in customer name '{data.customer_name}'")

        # Tax rate plausibility – 0–30% is realistic for VAT/GST in Sri Lanka
        if data.subtotal > 0:
            tax_rate = (data.tax / data.subtotal) * 100
            if tax_rate > 30 or tax_rate < 0:
                errors.append(f"Implausible tax rate: {tax_rate:.1f}% (expected 0–30%)")

        # Suspicious large total – flag very high amounts (possible fraud/error)
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
            name="domain_rules",
            score=0.0,
            is_pass=False,
            details="; ".join(errors)
        )
    
    if suspicious_flags:
        return ValidationMetric(
            name="domain_rules",
            score=0.5,
            is_pass=False,
            details="Suspicious flags raised: " + "; ".join(suspicious_flags)
        )
    
    return ValidationMetric(
        name="domain_rules",
        score=1.0,
        is_pass=True,
        details="All domain rules passed"
    )

# 4. PII Leakage Check
# Privacy guardrail using Presidio – context-aware for medical vs business docs
def check_pii_leakage(answer_json: str, doc_type: str | None = None) -> ValidationMetric:
    try:
        results = analyzer.analyze(text=answer_json, language="en")
        if results:
            entities = [r.entity_type for r in results]
            unique = list(set(entities))

            # Allow PERSON and DATE_TIME in medical documents (patient name/date expected)
            if doc_type in ["ClinicalSummary", "MedicationDosage", "InsuranceClaim"]:
                allowed = {"PERSON", "DATE_TIME"}
                non_allowed = [e for e in unique if e not in allowed]
                if non_allowed:
                    return ValidationMetric(
                        name="pii_leakage",
                        score=0.0,
                        is_pass=False,
                        details=f"Detected non-allowed PII: {', '.join(non_allowed)}"
                    )
                return ValidationMetric(
                    name="pii_leakage",
                    score=1.0,
                    is_pass=True,
                    details="Allowed PII (PERSON/DATE_TIME) detected in medical context"
                )

            # For business/finance docs (Invoice, Receipt, etc.) – fail on any PII
            return ValidationMetric(
                name="pii_leakage",
                score=0.0,
                is_pass=False,
                details=f"Detected PII: {', '.join(unique)}"
            )
    except Exception as e:
        logger.warning(f"Presidio failed: {e}")
    return ValidationMetric(name="pii_leakage", score=1.0, is_pass=True, details="No PII detected")

# 5. Faithfulness Check
# Hallucination detection – compares extracted fields to source text chunks
async def check_faithfulness(answer_json: str, source_contexts: List[str]) -> ValidationMetric:
    if not embedder:
        return ValidationMetric(name="faithfulness", score=0.0, is_pass=False, details="Embedder not loaded")
    if not source_contexts:
        return ValidationMetric(name="faithfulness", score=0.0, is_pass=False, details="No source contexts")

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
            name="faithfulness",
            score=round(avg_score, 3),
            is_pass=is_pass,
            details=details
        )
    except Exception as e:
        logger.error(f"Faithfulness error: {e}")
        return ValidationMetric(name="faithfulness", score=0.0, is_pass=False, details="Error")
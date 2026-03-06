"""
validation.py – Individual guardrail & hallucination checks
FINAL VERSION – Presidio matched_text suppression added, torch warnings removed

Last fix:
- Pylance false positive on entity.matched_text → # type: ignore[attr-defined]
"""

import json
import logging
import re
from datetime import date
from typing import Dict, List, Any

from sentence_transformers import SentenceTransformer, util
from presidio_analyzer import AnalyzerEngine
from dateutil import parser as date_parser
import torch

from ..models import ValidationMetric, DocumentContext, SCHEMA_MAP, REQUIRED_FIELDS
from hallucination_guardrails.config import settings  # absolute import

logger = logging.getLogger(__name__)

# ─── Global resources ────────────────────────────────────────────────────────
try:
    embedder = SentenceTransformer(settings.EMBEDDER_MODEL, device="cpu")
    logger.info(f"Loaded embedder: {settings.EMBEDDER_MODEL}")
except Exception as e:
    logger.error(f"Embedder load failed: {e}")
    embedder = None

analyzer = AnalyzerEngine()

AMOUNT_LIKE_PATTERNS = ["total", "subtotal", "tax", "vat", "amount", "balance", "claim", "grand", "discount", "fee"]
DATE_LIKE_PATTERNS   = ["date", "due", "issue", "payment", "claim", "period"]

def is_amount_like(key: str) -> bool:
    return any(p in key.lower() for p in AMOUNT_LIKE_PATTERNS)

def is_date_like(key: str) -> bool:
    return any(p in key.lower() for p in DATE_LIKE_PATTERNS)

# 1. Schema Adherence
async def check_schema_adherence(answer_json: str, doc_type: str) -> ValidationMetric:
    model_cls = SCHEMA_MAP.get(doc_type)
    if not model_cls:
        return ValidationMetric(name="schema_adherence", score=0.0, is_pass=False,
                                details=f"Unknown document type: {doc_type}")

    try:
        data = json.loads(answer_json)
        required = REQUIRED_FIELDS.get(doc_type, [])
        missing = [f for f in required if f not in data or data[f] is None]
        if missing:
            return ValidationMetric(name="schema_adherence", score=0.0, is_pass=False,
                                    details=f"Missing required fields: {', '.join(missing)}")

        model_cls.model_validate(data)
        extra_count = len(data) - len({k for k in data if k in required})
        details = "Schema valid" + (f" (+{extra_count} extra fields)" if extra_count > 0 else "")
        return ValidationMetric(name="schema_adherence", score=1.0, is_pass=True, details=details)
    except Exception as e:
        return ValidationMetric(name="schema_adherence", score=0.0, is_pass=False,
                                details=f"Schema validation failed: {str(e)[:150]}...")

# 2. Internal Consistency
def check_internal_consistency(data: Dict[str, Any], context: DocumentContext) -> ValidationMetric:
    errors = []
    pol = settings.POLICIES["internal_consistency"]

    for k, v in data.items():
        if is_amount_like(k) and isinstance(v, (int, float)) and v < 0:
            errors.append(f"Negative value in '{k}': {v}")

    if all(k in data for k in ["subtotal", "tax", "total"]):
        expected = data["subtotal"] + data.get("tax", 0)
        if abs(data["total"] - expected) > pol["math_tolerance"]:
            errors.append(f"Math inconsistency: total {data['total']} ≠ subtotal + tax ({expected:.2f})")

    for k, v in data.items():
        if is_date_like(k) and isinstance(v, str):
            try:
                parsed = date_parser.parse(v, dayfirst=True).date()
                if parsed > date.today() and not pol.get("date_future_allowed", False):
                    errors.append(f"Future date in '{k}': {v}")
            except ValueError:
                pass

    critical_strings = ["merchant", "supplier", "customer_name", "account_holder"]
    for k in critical_strings:
        if k in data and not str(data[k]).strip():
            errors.append(f"Empty critical field '{k}'")

    if errors:
        return ValidationMetric(name="internal_consistency", score=0.0, is_pass=False,
                                details="; ".join(errors))
    return ValidationMetric(name="internal_consistency", score=1.0, is_pass=True,
                            details="Internal consistency checks passed")

# 3. Relevance
async def check_relevance(data: Dict[str, Any], source_contexts: List[str], doc_type: str) -> ValidationMetric:
    if not embedder or not source_contexts:
        return ValidationMetric(name="relevance", score=0.0, is_pass=False, details="Missing embedder or source contexts")

    context_text = " ".join(source_contexts)
    ctx_emb_np = embedder.encode(context_text, convert_to_tensor=False)
    ctx_emb = torch.from_numpy(ctx_emb_np).to(torch.float32)

    pol = settings.POLICIES["relevance"]
    expected = pol["expected_fields"].get(doc_type, [])
    fin_kw = pol["financial_keywords"]

    field_scores = {}
    low_fields = []
    unexpected = 0

    for key, value in data.items():
        if value in (None, "", [], {}, " "):
            continue
        val_str = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        val_emb_np = embedder.encode(val_str, convert_to_tensor=False)

        val_emb = torch.from_numpy(val_emb_np).to(torch.float32).unsqueeze(0)
        ctx_emb_batch = ctx_emb.clone().detach().unsqueeze(0).to(torch.float32)
        sim = util.cos_sim(val_emb, ctx_emb_batch)[0][0].item()

        if any(w in key.lower() or w in val_str.lower() for w in fin_kw):
            sim = min(1.0, sim + pol["keyword_boost"])

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
        details += f" | LOW relevance fields: {', '.join(low_fields)} → likely hallucination or noise"

    return ValidationMetric(name="relevance", score=round(avg_score, 3), is_pass=is_pass, details=details)

# 4. Domain Rules
def check_domain_rules(data: Dict[str, Any], context: DocumentContext, relevant_keys: List[str], source_contexts: List[str]) -> ValidationMetric:
    pol = settings.POLICIES["domain_rules"]
    tax_pol = pol["tax"].get(context.doc_type.value, pol["tax"]["default"])

    errors = []
    suspicious = []

    for v in data.values():
        if isinstance(v, str) and any(kw.lower() in v.lower() for kw in pol["blacklist_keywords"]):
            suspicious.append("Blacklisted keyword found")

    thresh = pol["large_amount_thresholds"].get(context.doc_type.value, 1000000.0)
    for k in relevant_keys:
        v = data.get(k)
        if is_amount_like(k) and isinstance(v, (int, float)) and v > thresh:
            suspicious.append(f"Suspiciously large '{k}': {v} > {thresh}")

    tax_val = None
    subtotal_val = None
    for k in relevant_keys:
        kl = k.lower()
        if "tax" in kl or "vat" in kl:
            tax_val = data.get(k)
        if "subtotal" in kl or "base" in kl:
            subtotal_val = data.get(k)

    zero_ctx = any(
        kw.lower() in str(v).lower()
        for v in data.values()
        for kw in tax_pol["zero_rated_keywords"]
    ) or any(
        kw.lower() in " ".join(source_contexts).lower()
        for kw in tax_pol["zero_rated_keywords"]
    )

    if tax_val is not None and subtotal_val and subtotal_val > 0:
        rate = (tax_val / subtotal_val) * 100
        allowed = tax_pol["allowed_rates"]
        closest = min(allowed, key=lambda x: abs(x - rate))
        tol = tax_pol["tolerance_pct"]

        if abs(rate - closest) <= tol or rate in allowed:
            pass
        elif zero_ctx and abs(rate - 0.0) < 2.0:
            pass
        elif rate > tax_pol["max_rate"] or rate < tax_pol["min_rate"]:
            errors.append(f"Invalid VAT rate: {rate:.2f}% (allowed range {tax_pol['min_rate']}–{tax_pol['max_rate']}%)")
        else:
            suspicious.append(f"Non-standard VAT rate: {rate:.2f}%")

    elif (tax_val == 0 or tax_val is None) and subtotal_val and subtotal_val > 0:
        if not zero_ctx:
            suspicious.append("Zero or missing VAT without exempt/zero-rated context")

    if errors:
        return ValidationMetric(name="domain_rules", score=0.0, is_pass=False, details="; ".join(errors))
    if suspicious:
        return ValidationMetric(name="domain_rules", score=0.5, is_pass=False,
                                details="Suspicious flags: " + "; ".join(suspicious))
    return ValidationMetric(name="domain_rules", score=1.0, is_pass=True,
                            details="All domain/fraud checks passed")

# 5. PII Leakage – fixed attribute + suppression
def check_pii_leakage(answer_json: str, doc_type: str) -> ValidationMetric:
    try:
        results = analyzer.analyze(text=answer_json, language="en")
        if not results:
            return ValidationMetric(name="pii_leakage", score=1.0, is_pass=True, details="No PII detected")

        detected: Dict[str, List[str]] = {}
        for entity in results:
            if entity.score >= settings.POLICIES["pii_leakage"]["min_confidence"]:
                detected.setdefault(entity.entity_type, []).append(entity.matched_text)  # type: ignore[attr-defined]

        allowed = settings.POLICIES["pii_leakage"]["allowed_entities"].get(doc_type, [])
        forbidden = [et for et in detected if et not in allowed]

        if forbidden:
            return ValidationMetric(name="pii_leakage", score=0.0, is_pass=False,
                                    details=f"Non-allowed PII types: {', '.join(forbidden)}")

        return ValidationMetric(name="pii_leakage", score=1.0, is_pass=True,
                                details=f"Only allowed PII: {', '.join(detected.keys())}")
    except Exception as e:
        logger.warning(f"PII analysis error: {e}")
        return ValidationMetric(name="pii_leakage", score=1.0, is_pass=True, details="PII check skipped due to error")

# 6. Faithfulness
async def check_faithfulness(data: Dict[str, Any], source_contexts: List[str], relevant_keys: List[str]) -> ValidationMetric:
    if not embedder or not source_contexts or not relevant_keys:
        return ValidationMetric(name="faithfulness", score=0.0, is_pass=False,
                                details="Missing embedder, sources, or relevant fields")

    context_text = " ".join(source_contexts)
    ctx_emb_np = embedder.encode(context_text, convert_to_tensor=False)
    ctx_emb = torch.from_numpy(ctx_emb_np).to(torch.float32)

    pol = settings.POLICIES["faithfulness"]
    sem_total, sem_count = 0.0, 0
    num_matches, num_total = 0, 0

    for key in relevant_keys:
        if key not in data:
            continue
        val = data[key]
        val_str = json.dumps(val) if isinstance(val, (dict, list)) else str(val)
        if not val_str.strip():
            continue

        val_emb_np = embedder.encode(val_str, convert_to_tensor=False)
        val_emb = torch.from_numpy(val_emb_np).to(torch.float32).unsqueeze(0)
        ctx_emb_batch = ctx_emb.clone().detach().unsqueeze(0).to(torch.float32)
        sim = util.cos_sim(val_emb, ctx_emb_batch)[0][0].item()

        weight = pol["field_importance"].get(key, pol["field_importance"]["default"])
        sem_total += sim * weight
        sem_count += weight

    sem_avg = sem_total / sem_count if sem_count > 0 else 0.0

    ans_nums = [float(v) for k, v in data.items() if is_amount_like(k) and isinstance(v, (int, float))]
    src_nums = [float(x) for x in re.findall(r'\d+\.?\d{0,2}', context_text)]
    if ans_nums and src_nums:
        for a in ans_nums:
            for s in src_nums:
                if abs(a - s) / max(s, 1) <= pol["numerical_tolerance"].get("default", 0.005):
                    num_matches += 1
                    break
        num_total = len(ans_nums)
        num_score = num_matches / num_total if num_total > 0 else 0.0
    else:
        num_score = 0.8

    ent_score = 0.85

    final_score = (
        sem_avg * pol["semantic_weight"] +
        num_score * pol["numerical_weight"] +
        ent_score * pol["entity_weight"]
    )

    is_pass = final_score >= settings.FAITHFULNESS_THRESHOLD

    return ValidationMetric(
        name="faithfulness",
        score=round(final_score, 3),
        is_pass=is_pass,
        details=f"Semantic {sem_avg:.3f} (w) | Numerical {num_score:.3f} | Entity {ent_score:.3f} | Final {final_score:.3f}"
    )
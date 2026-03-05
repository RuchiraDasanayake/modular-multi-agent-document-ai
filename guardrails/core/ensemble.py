"""
Validation Ensemble — orchestrates all 5 guardrail checks in sequence.

1. Schema Adherence  — Pydantic model validation per doc type
2. Internal Consistency — business logic (math, negatives, future dates, dosage)
3. Domain Rules — tax plausibility, vendor fraud, suspicious keywords, large amounts
4. PII Leakage — Presidio-based, context-aware
5. Faithfulness — semantic similarity via sentence-transformers
"""

from ..models import RAGInput, ValidationMetric, SCHEMA_MAP
from .validation import (
    check_schema_adherence,
    check_internal_consistency,
    check_domain_rules,
    check_pii_leakage,
    check_faithfulness,
)

async def run_validation_ensemble(rag_input: RAGInput) -> list[ValidationMetric]:
    """Run the full 5-layer guardrail ensemble and return per-check results.
    
    Every check is executed with error isolation — a single check failure
    does not crash the entire ensemble. Skipped checks receive a neutral
    score (0.5) so downstream consumers always see all 5 check names.
    """
    from datetime import datetime, timezone
    results: list[ValidationMetric] = []

    # 1. Schema Adherence
    try:
        results.append(
            await check_schema_adherence(rag_input.answer_json, rag_input.document_context.doc_type.value)
        )
    except Exception as exc:
        results.append(ValidationMetric(
            name="schema_adherence", score=0.0, is_pass=False,
            details=f"Schema check error: {exc}", timestamp=datetime.now(timezone.utc),
        ))

    # Parse validated data for consistency + domain checks
    validated_data = None
    if results[-1].is_pass:
        try:
            model = SCHEMA_MAP[rag_input.document_context.doc_type.value]
            validated_data = model.model_validate_json(rag_input.answer_json)
        except Exception:
            pass

    # 2. Internal Consistency (requires validated data)
    if validated_data:
        try:
            results.append(check_internal_consistency(validated_data, rag_input.document_context))
        except Exception as exc:
            results.append(ValidationMetric(
                name="internal_consistency", score=0.0, is_pass=False,
                details=f"Consistency check error: {exc}", timestamp=datetime.now(timezone.utc),
            ))
    else:
        results.append(ValidationMetric(
            name="internal_consistency", score=0.5, is_pass=True,
            details="Skipped — schema adherence failed or no typed model available",
            timestamp=datetime.now(timezone.utc),
        ))

    # 3. Domain Rules (requires validated data)
    if validated_data:
        try:
            results.append(check_domain_rules(validated_data, rag_input.document_context))
        except Exception as exc:
            results.append(ValidationMetric(
                name="domain_rules", score=0.0, is_pass=False,
                details=f"Domain rules error: {exc}", timestamp=datetime.now(timezone.utc),
            ))
    else:
        results.append(ValidationMetric(
            name="domain_rules", score=0.5, is_pass=True,
            details="Skipped — no typed model available for domain validation",
            timestamp=datetime.now(timezone.utc),
        ))

    # 4. PII Leakage (context-aware)
    try:
        results.append(check_pii_leakage(rag_input.answer_json, rag_input.document_context.doc_type.value))
    except Exception as exc:
        results.append(ValidationMetric(
            name="pii_leakage", score=0.0, is_pass=False,
            details=f"PII check error: {exc}", timestamp=datetime.now(timezone.utc),
        ))

    # 5. Faithfulness
    try:
        results.append(await check_faithfulness(rag_input.answer_json, rag_input.source_contexts))
    except Exception as exc:
        results.append(ValidationMetric(
            name="faithfulness", score=0.0, is_pass=False,
            details=f"Faithfulness check error: {exc}", timestamp=datetime.now(timezone.utc),
        ))

    return results

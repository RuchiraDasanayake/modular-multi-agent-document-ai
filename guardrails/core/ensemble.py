"""
Validation Ensemble — orchestrates all 5 guardrail checks in sequence.

1. Schema Adherence  — Pydantic model validation per doc type
2. Internal Consistency — business logic (math, negatives, future dates, dosage)
3. Domain Rules — tax plausibility, vendor fraud, suspicious keywords, large amounts
4. PII Leakage — Presidio-based, context-aware
5. Faithfulness — semantic similarity via sentence-transformers
"""

from typing import List

from ..models import RAGInput, ValidationMetric, SCHEMA_MAP
from .validation import (
    check_schema_adherence,
    check_internal_consistency,
    check_domain_rules,
    check_pii_leakage,
    check_faithfulness,
)


async def run_validation_ensemble(rag_input: RAGInput) -> List[ValidationMetric]:
    """Run the full 5-layer guardrail ensemble and return per-check results."""
    results: List[ValidationMetric] = []

    # 1. Schema Adherence
    results.append(
        await check_schema_adherence(rag_input.answer_json, rag_input.document_context.doc_type.value)
    )

    # Parse validated data for consistency + domain checks
    validated_data = None
    if results[-1].is_pass:
        try:
            model = SCHEMA_MAP[rag_input.document_context.doc_type.value]
            validated_data = model.model_validate_json(rag_input.answer_json)
        except Exception:
            pass

    if validated_data:
        results.append(check_internal_consistency(validated_data, rag_input.document_context))
        results.append(check_domain_rules(validated_data, rag_input.document_context))

    # 4. PII Leakage (context-aware)
    results.append(check_pii_leakage(rag_input.answer_json, rag_input.document_context.doc_type.value))

    # 5. Faithfulness
    results.append(await check_faithfulness(rag_input.answer_json, rag_input.source_contexts))

    return results

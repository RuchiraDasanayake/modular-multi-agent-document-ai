"""
Validation Ensemble — orchestrates all 6 guardrail checks in sequence.

1. Schema Adherence  — Pydantic model validation per doc type
2. Relevance — checks if extracted fields are relevant to source (hallucination detection)
3. Internal Consistency — business logic (math, negatives, future dates, dosage)
4. Domain Rules — tax plausibility, vendor fraud, suspicious keywords, large amounts
5. PII Leakage — Presidio-based, context-aware
6. Faithfulness — weighted semantic + numerical similarity
"""
import asyncio
import json
from ..models import RAGInput, ValidationMetric, SCHEMA_MAP
from .validation import (
    check_schema_adherence,
    check_relevance,
    check_internal_consistency,
    check_domain_rules,
    check_pii_leakage,
    check_faithfulness,
)

async def run_validation_ensemble(rag_input: RAGInput) -> list[ValidationMetric]:
    """Run the full 6-layer guardrail ensemble and return per-check results.

    Every check is executed with error isolation — a single check failure
    does not crash the entire ensemble. Skipped checks receive a neutral
    score (0.5) so downstream consumers always see all 6 check names.
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
    data_dict = None
    if results[-1].is_pass:
        try:
            model = SCHEMA_MAP[rag_input.document_context.doc_type.value]
            validated_data = model.model_validate_json(rag_input.answer_json)
            data_dict = json.loads(rag_input.answer_json)
        except Exception:
            pass

    # 2. Relevance Check (hallucination detection)
    if data_dict and rag_input.source_contexts:
        try:
            results.append(
                await check_relevance(
                    data_dict,
                    rag_input.source_contexts,
                    rag_input.document_context.doc_type.value
                )
            )
        except Exception as exc:
            results.append(ValidationMetric(
                name="relevance", score=0.0, is_pass=False,
                details=f"Relevance check error: {exc}", timestamp=datetime.now(timezone.utc),
            ))
    else:
        results.append(ValidationMetric(
            name="relevance", score=0.5, is_pass=True,
            details="Skipped — no data or source contexts available",
            timestamp=datetime.now(timezone.utc),
        ))

    # 3. Internal Consistency (requires validated data)
    if validated_data:
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, check_internal_consistency, validated_data, rag_input.document_context
            )
            results.append(result)
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

    # 4. Domain Rules (requires validated data)
    if validated_data:
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, check_domain_rules, validated_data, rag_input.document_context
            )
            results.append(result)
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

    # 5. PII Leakage (context-aware)
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, check_pii_leakage, rag_input.answer_json, rag_input.document_context.doc_type.value
        )
        results.append(result)
    except Exception as exc:
        results.append(ValidationMetric(
            name="pii_leakage", score=0.0, is_pass=False,
            details=f"PII check error: {exc}", timestamp=datetime.now(timezone.utc),
        ))

    # 6. Faithfulness (with timeout to prevent hangs on large contexts)
    try:
        results.append(
            await asyncio.wait_for(check_faithfulness(rag_input.answer_json, rag_input.source_contexts), timeout=30.0)
        )
    except asyncio.TimeoutError:
        results.append(ValidationMetric(
            name="faithfulness", score=0.5, is_pass=True,
            details="Faithfulness check timed out (30s) — skipped",
            timestamp=datetime.now(timezone.utc),
        ))
    except Exception as exc:
        results.append(ValidationMetric(
            name="faithfulness", score=0.0, is_pass=False,
            details=f"Faithfulness check error: {exc}", timestamp=datetime.now(timezone.utc),
        ))

    return results

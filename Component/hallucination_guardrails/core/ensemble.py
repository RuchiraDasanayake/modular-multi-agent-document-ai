from typing import List

from ..models import RAGInput, ValidationMetric, SCHEMA_MAP
from .validation import (
    check_schema_adherence,
    check_internal_consistency,
    check_domain_rules,
    check_pii_leakage,
    check_faithfulness
)

async def run_validation_ensemble(input: RAGInput) -> List[ValidationMetric]:
    results = []
    
    # 1. Schema
    results.append(await check_schema_adherence(input.answer_json, input.document_context.doc_type.value))
    
    # Parse data if schema passed
    validated_data = None
    if results[-1].is_pass:
        try:
            model = SCHEMA_MAP[input.document_context.doc_type.value]
            validated_data = model.model_validate_json(input.answer_json)
        except Exception:
            pass
    
    if validated_data:
        results.append(check_internal_consistency(validated_data, input.document_context))
        results.append(check_domain_rules(validated_data, input.document_context))
    
    # PII – pass doc_type for context-aware allowance
    results.append(check_pii_leakage(input.answer_json, input.document_context.doc_type.value))
    
    # Faithfulness
    results.append(await check_faithfulness(input.answer_json, input.source_contexts))
    
    return results
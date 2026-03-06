"""
ensemble.py – Orchestrates the full validation pipeline
"""

import json
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any

from ..models import RAGInput, GuardrailOutput, ValidationMetric
from .validation import (
    check_schema_adherence,
    check_internal_consistency,
    check_relevance,
    check_domain_rules,
    check_pii_leakage,
    check_faithfulness
)

async def run_validation_ensemble(input_data: RAGInput) -> GuardrailOutput:
    start_time = time.time()
    audit_id = str(uuid.uuid4())
    advice_id = str(uuid.uuid4())

    validation_results: List[ValidationMetric] = []
    data: Dict[str, Any] = {}
    relevant_fields: List[str] = []
    guardrails_passed = False

    try:
        data = json.loads(input_data.answer_json)
    except Exception as e:
        validation_results.append(ValidationMetric(
            name="json_parse", score=0.0, is_pass=False, details=str(e)
        ))
        overall_pass = False
        halluc_detected = True
        risk = "HIGH"
    else:
        doc_type = input_data.document_context.doc_type.value

        schema_res = await check_schema_adherence(input_data.answer_json, doc_type)
        validation_results.append(schema_res)

        if schema_res.is_pass:
            validation_results.append(check_internal_consistency(data, input_data.document_context))
            rel_res = await check_relevance(data, input_data.source_contexts, doc_type)
            validation_results.append(rel_res)

            if rel_res.is_pass:
                relevant_fields = list(data.keys())
                domain_res = check_domain_rules(data, input_data.document_context, relevant_fields, input_data.source_contexts)
                validation_results.append(domain_res)

                pii_res = check_pii_leakage(input_data.answer_json, doc_type)
                validation_results.append(pii_res)

        guardrails_passed = all(r.is_pass for r in validation_results)

        faithfulness_res = await check_faithfulness(data, input_data.source_contexts, relevant_fields)
        validation_results.append(faithfulness_res)

        halluc_detected = not faithfulness_res.is_pass
        overall_pass = guardrails_passed and not halluc_detected

        if not overall_pass:
            risk = "HIGH"
        elif any(r.score <= 0.5 for r in validation_results if r.score is not None):
            risk = "MEDIUM"
        else:
            risk = "LOW"

    processing_time_ms = (time.time() - start_time) * 1000

    metrics_summary = {
        "guardrails_success": guardrails_passed,
        "hallucination_detected": halluc_detected,
        "risk_level": risk,
        "num_failed_checks": sum(1 for r in validation_results if not r.is_pass),
        "num_suspicious_checks": sum(1 for r in validation_results if r.score == 0.5),
        "processing_time_ms": round(processing_time_ms, 1),
        "faithfulness_score": next((r.score for r in validation_results if r.name == "faithfulness"), None),
        "relevance_score": next((r.score for r in validation_results if r.name == "relevance"), None),
    }

    return GuardrailOutput(
        rag_input=input_data,
        validation_results=validation_results,
        overall_passes=overall_pass,
        hallucination_detected=halluc_detected,
        risk_level=risk,
        audit_log_id=audit_id,
        processing_time_ms=processing_time_ms,
        timestamp=datetime.now(),
        advice_id=advice_id,
        metrics=metrics_summary
    )
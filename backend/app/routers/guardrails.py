"""
Guardrails router — /api/guardrails
Integrates the top-level guardrails 5-layer validation ensemble into the backend API.
"""

import time
import uuid
import logging
from datetime import datetime
from collections import defaultdict

from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..schemas.guardrails import (
    ValidateRequest,
    ValidateResponse,
    ValidationMetricResponse,
    GuardrailStatsResponse,
)

from guardrails import (
    DocumentType,
    GuardrailDocumentContext,
    RAGInput,
    run_validation_ensemble,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/guardrails", tags=["guardrails"])

# In-memory audit log (extend to DB for production)
_audit_store: list[dict] = []


@router.post("/validate", response_model=ValidateResponse)
async def validate_response(req: ValidateRequest, _user=Depends(get_current_user)):
    """
    Validate a RAG extraction through the 5-layer guardrail ensemble.

    Checks: Schema Adherence → Internal Consistency → Domain Rules → PII Leakage → Faithfulness
    """
    start = time.time()
    audit_id = str(uuid.uuid4())

    # Build core input
    rag_input = RAGInput(
        document_context=GuardrailDocumentContext(
            doc_type=DocumentType(req.document_context.doc_type),
            vendor=req.document_context.vendor,
            quality_bin=req.document_context.quality_bin,
        ),
        query=req.query,
        answer_json=req.answer_json,
        source_contexts=req.source_contexts,
        document_id=req.document_id,
    )

    # Run ensemble
    results = await run_validation_ensemble(rag_input)
    overall = all(r.is_pass for r in results)
    elapsed_ms = (time.time() - start) * 1000

    # Build metrics summary
    metrics = {
        "guardrails_success": overall,
        "num_failed_checks": sum(1 for r in results if not r.is_pass),
        "processing_time_ms": round(elapsed_ms, 1),
    }
    for r in results:
        metrics[f"{r.name}_score"] = r.score

    # Store audit
    audit_entry = {
        "audit_log_id": audit_id,
        "timestamp": datetime.now().isoformat(),
        "document_id": req.document_id,
        "doc_type": req.document_context.doc_type,
        "overall_passes": overall,
        "processing_time_ms": round(elapsed_ms, 1),
        "checks": {r.name: {"score": r.score, "is_pass": r.is_pass} for r in results},
    }
    _audit_store.append(audit_entry)

    logger.info(f"Guardrail {audit_id}: {'PASS' if overall else 'FAIL'} ({elapsed_ms:.0f}ms)")

    return ValidateResponse(
        overall_passes=overall,
        audit_log_id=audit_id,
        processing_time_ms=round(elapsed_ms, 1),
        timestamp=datetime.now(),
        validation_results=[
            ValidationMetricResponse(
                name=r.name, score=r.score, is_pass=r.is_pass,
                details=r.details, timestamp=r.timestamp,
            )
            for r in results
        ],
        metrics=metrics,
    )


@router.get("/stats", response_model=GuardrailStatsResponse)
async def guardrail_stats(_user=Depends(get_current_user)):
    """Aggregate statistics from guardrail validation runs."""
    total = len(_audit_store)
    passed = sum(1 for a in _audit_store if a["overall_passes"])
    failed = total - passed
    avg_time = (
        sum(a["processing_time_ms"] for a in _audit_store) / total if total else 0.0
    )

    # Per-check breakdown
    breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "failed": 0})
    for a in _audit_store:
        for check_name, check_data in a.get("checks", {}).items():
            if check_data["is_pass"]:
                breakdown[check_name]["passed"] += 1
            else:
                breakdown[check_name]["failed"] += 1

    return GuardrailStatsResponse(
        total_validations=total,
        total_passed=passed,
        total_failed=failed,
        pass_rate=round(passed / total, 3) if total else 0.0,
        avg_processing_time_ms=round(avg_time, 1),
        checks_breakdown=dict(breakdown),
    )


@router.get("/history")
async def guardrail_history(limit: int = 50, _user=Depends(get_current_user)):
    """Return recent guardrail audit log entries."""
    return _audit_store[-limit:][::-1]

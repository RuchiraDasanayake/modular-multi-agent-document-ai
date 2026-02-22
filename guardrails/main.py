"""
Guardrails Microservice — 5-Layer Hallucination Detection Ensemble

Validates RAG extraction outputs through: Schema Adherence, Internal Consistency,
Domain Rules, PII Leakage, and Faithfulness checks.

Component Owner: Wijetunga W.L.A.T. (Thenuka)
"""

import os
import time
import uuid
import logging
from datetime import datetime
from collections import defaultdict
from typing import Any, Optional

from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .models import DocumentType, GuardrailDocumentContext, RAGInput
from .core.ensemble import run_validation_ensemble

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# ─── Request / Response Schemas ──────────────────────────────────────────────


class DocumentContextRequest(BaseModel):
    doc_type: str = Field(
        ...,
        description="One of: ClinicalSummary, MedicationDosage, Invoice, "
        "InsuranceClaim, BankStatement, PurchaseOrder, Receipt",
    )
    vendor: Optional[str] = None
    quality_bin: Optional[str] = None


class ValidateRequest(BaseModel):
    document_context: DocumentContextRequest
    query: str
    answer_json: str = Field(..., description="Extracted data as JSON string.")
    source_contexts: list[str] = Field(
        ..., description="Source text chunks for faithfulness check."
    )
    document_id: Optional[str] = None


class ValidationMetricResponse(BaseModel):
    name: str
    score: float
    is_pass: bool
    details: str
    timestamp: datetime


class ValidateResponse(BaseModel):
    overall_passes: bool
    audit_log_id: str
    processing_time_ms: float
    timestamp: datetime
    validation_results: list[ValidationMetricResponse]
    metrics: dict[str, Any]


class StatsResponse(BaseModel):
    total_validations: int
    total_passed: int
    total_failed: int
    pass_rate: float
    avg_processing_time_ms: float
    checks_breakdown: dict[str, dict[str, int]]


# ─── In-Memory Audit Store ───────────────────────────────────────────────────
# For production, replace with database persistence.

_audit_store: list[dict] = []


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Guardrails Service",
    description="5-Layer Hallucination Detection & Validation Ensemble",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "guardrails"}


@app.post("/validate", response_model=ValidateResponse)
async def validate_response(req: ValidateRequest):
    """
    Validate a RAG extraction through the 5-layer guardrail ensemble.

    Checks: Schema Adherence → Internal Consistency → Domain Rules
            → PII Leakage → Faithfulness
    """
    start = time.time()
    audit_id = str(uuid.uuid4())

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

    results = await run_validation_ensemble(rag_input)
    overall = all(r.is_pass for r in results)
    elapsed_ms = (time.time() - start) * 1000

    metrics: dict[str, Any] = {
        "guardrails_success": overall,
        "num_failed_checks": sum(1 for r in results if not r.is_pass),
        "processing_time_ms": round(elapsed_ms, 1),
    }
    for r in results:
        metrics[f"{r.name}_score"] = r.score

    _audit_store.append(
        {
            "audit_log_id": audit_id,
            "timestamp": datetime.now().isoformat(),
            "document_id": req.document_id,
            "doc_type": req.document_context.doc_type,
            "overall_passes": overall,
            "processing_time_ms": round(elapsed_ms, 1),
            "checks": {
                r.name: {"score": r.score, "is_pass": r.is_pass} for r in results
            },
        }
    )

    logger.info("Guardrail %s: %s (%.0fms)", audit_id, "PASS" if overall else "FAIL", elapsed_ms)

    return ValidateResponse(
        overall_passes=overall,
        audit_log_id=audit_id,
        processing_time_ms=round(elapsed_ms, 1),
        timestamp=datetime.now(),
        validation_results=[
            ValidationMetricResponse(
                name=r.name,
                score=r.score,
                is_pass=r.is_pass,
                details=r.details,
                timestamp=r.timestamp,
            )
            for r in results
        ],
        metrics=metrics,
    )


@app.get("/stats", response_model=StatsResponse)
async def guardrail_stats():
    """Aggregate statistics from validation runs."""
    total = len(_audit_store)
    passed = sum(1 for a in _audit_store if a["overall_passes"])
    failed = total - passed
    avg_time = (
        sum(a["processing_time_ms"] for a in _audit_store) / total if total else 0.0
    )

    breakdown: dict[str, dict[str, int]] = defaultdict(
        lambda: {"passed": 0, "failed": 0}
    )
    for a in _audit_store:
        for check_name, check_data in a.get("checks", {}).items():
            if check_data["is_pass"]:
                breakdown[check_name]["passed"] += 1
            else:
                breakdown[check_name]["failed"] += 1

    return StatsResponse(
        total_validations=total,
        total_passed=passed,
        total_failed=failed,
        pass_rate=round(passed / total, 3) if total else 0.0,
        avg_processing_time_ms=round(avg_time, 1),
        checks_breakdown=dict(breakdown),
    )


@app.get("/history")
async def guardrail_history(limit: int = Query(50, ge=1, le=500)):
    """Return recent guardrail audit log entries."""
    return _audit_store[-limit:][::-1]

"""
Guardrails Microservice — 5-Layer Hallucination Detection Ensemble

Validates RAG extraction outputs through: Schema Adherence, Internal Consistency,
Domain Rules, PII Leakage, and Faithfulness checks.

Component Owner: Wijetunga W.L.A.T. (Thenuka)
"""

import asyncio
import os
import time
import uuid
import json
import logging
import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .models import DocumentType, GuardrailDocumentContext, RAGInput
from .core.ensemble import run_validation_ensemble
from .config import guardrail_settings

# psycopg async connections on Windows require Selector event loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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
    vendor: str | None = None
    quality_bin: str | None = None

class ValidateRequest(BaseModel):
    document_context: DocumentContextRequest
    query: str
    answer_json: str = Field(..., description="Extracted data as JSON string.")
    source_contexts: list[str] = Field(
        ..., description="Source text chunks for faithfulness check."
    )
    document_id: str | None = None

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

# ─── Audit Persistence ────────────────────────────────────────────────────
# In-memory deque kept as a fast read cache; writes also go to PostgreSQL
# guardrail_audit_log table when POSTGRES_URI is configured.

from collections import deque

_audit_store: deque[dict] = deque(maxlen=10_000)

# Optional async DB pool — initialised on startup if POSTGRES_URI is set
_db_pool = None

async def _persist_audit(entry: dict) -> None:
    """Write audit entry to PostgreSQL (fire-and-forget, non-blocking)."""
    if _db_pool is None:
        return
    try:
        async with _db_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO guardrail_audit_log
                       (id, document_id, doc_type, overall_passes, processing_time_ms, checks)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        entry["audit_log_id"],
                        entry.get("document_id"),
                        entry["doc_type"],
                        entry["overall_passes"],
                        entry["processing_time_ms"],
                        json.dumps(entry["checks"]),
                    ),
                )
            await conn.commit()
    except Exception as exc:
        logger.warning("Failed to persist audit log to DB: %s", exc)

# ─── Lifespan ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _db_pool
    pg_uri = guardrail_settings.POSTGRES_URI
    if pg_uri:
        try:
            from psycopg_pool import AsyncConnectionPool
            _db_pool = AsyncConnectionPool(pg_uri, min_size=1, max_size=5)
            await _db_pool.open()
            logger.info("Guardrails DB pool opened — audit logs will persist to PostgreSQL")
        except Exception as exc:
            logger.warning("Could not open DB pool (audit logs will stay in-memory): %s", exc)
            _db_pool = None
    else:
        logger.info("No POSTGRES_URI — guardrail audit logs stored in-memory only")
    yield
    if _db_pool:
        await _db_pool.close()
        logger.info("Guardrails DB pool closed")

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Guardrails Service",
    description="5-Layer Hallucination Detection & Validation Ensemble",
    version="1.0.0",
    lifespan=lifespan,
)

# Internal service — restrict CORS to gateway and local dev only
_allowed_origins = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://gateway:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "guardrails"}

@app.post("/guardrails/validate", response_model=ValidateResponse)
async def validate_response(req: ValidateRequest):
    """
    Validate a RAG extraction through the 5-layer guardrail ensemble.

    Checks: Schema Adherence → Internal Consistency → Domain Rules
            → PII Leakage → Faithfulness
    """
    start = time.time()
    audit_id = str(uuid.uuid4())

    try:
        doc_type = DocumentType(req.document_context.doc_type)
    except ValueError:
        doc_type = DocumentType.GENERIC

    rag_input = RAGInput(
        document_context=GuardrailDocumentContext(
            doc_type=doc_type,
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

    audit_entry = {
        "audit_log_id": audit_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "document_id": req.document_id,
        "doc_type": req.document_context.doc_type,
        "overall_passes": overall,
        "processing_time_ms": round(elapsed_ms, 1),
        "checks": {
            r.name: {"score": r.score, "is_pass": r.is_pass} for r in results
        },
    }

    _audit_store.append(audit_entry)

    # Persist to PostgreSQL (non-blocking, best-effort)
    asyncio.create_task(_persist_audit(audit_entry))

    logger.info("Guardrail %s: %s (%.0fms)", audit_id, "PASS" if overall else "FAIL", elapsed_ms)

    return ValidateResponse(
        overall_passes=overall,
        audit_log_id=audit_id,
        processing_time_ms=round(elapsed_ms, 1),
        timestamp=datetime.now(timezone.utc),
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

@app.get("/guardrails/stats", response_model=StatsResponse)
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

@app.get("/guardrails/history")
async def guardrail_history(limit: int = Query(50, ge=1, le=500)):
    """Return recent guardrail audit log entries."""
    store_list = list(_audit_store)
    return store_list[-limit:][::-1]

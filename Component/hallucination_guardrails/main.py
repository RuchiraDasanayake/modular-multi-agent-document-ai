from datetime import datetime
import uuid
import time
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .models import RAGInput, GuardrailOutput  # ← FIXED: added GuardrailOutput
from .core.ensemble import run_validation_ensemble
from .config import settings

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

app = FastAPI(title="Hallucination Guardrails for Modular Document AI", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

audit_logs = {}  # In-memory; extend to DB for production

@app.post("/v1/validate_response", response_model=GuardrailOutput)
async def validate_response(input: RAGInput):
    start = time.time()
    audit_id = str(uuid.uuid4())
    results = await run_validation_ensemble(input)
    overall = all(r.is_pass for r in results)

    # Extract scores for metrics
    schema_res = next((r for r in results if r.name == "schema_adherence"), None)
    cons_res = next((r for r in results if r.name == "internal_consistency"), None)
    domain_res = next((r for r in results if r.name == "domain_rules"), None)
    pii_res = next((r for r in results if r.name == "pii_leakage"), None)
    faith_res = next((r for r in results if r.name == "faithfulness"), None)

    failed_count = sum(1 for r in results if not r.is_pass)

    response = GuardrailOutput(
        rag_input=input,
        validation_results=results,
        overall_passes=overall,
        audit_log_id=audit_id,
        processing_time_ms=(time.time() - start) * 1000,
        timestamp=datetime.now(),

        advice_id=audit_id,

        metrics={
            "guardrails_success": overall,
            "num_failed_checks": failed_count,
            "faithfulness_avg_score": faith_res.score if faith_res else None,
            "schema_adherence_score": schema_res.score if schema_res else None,
            "consistency_score": cons_res.score if cons_res else None,
            "domain_rules_score": domain_res.score if domain_res else None,
            "pii_leakage_score": pii_res.score if pii_res else None,
            "cost": 0.0,
            "processing_time_ms": (time.time() - start) * 1000,
        }
    )

    audit_logs[audit_id] = response.model_dump()
    logger.info(f"Audit/Advice ID {audit_id}: {'PASS' if overall else 'FAIL'} - {failed_count} checks failed")
    return response

@app.get("/health")
async def health(): return {"status": "healthy"}
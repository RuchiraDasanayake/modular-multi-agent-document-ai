"""
main.py – FastAPI application entry point
Fixed: absolute import for config.settings + type hint
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import time
import uuid
import logging

from hallucination_guardrails.models import RAGInput, GuardrailOutput
from hallucination_guardrails.core.ensemble import run_validation_ensemble
from hallucination_guardrails.config import settings  # pyright: ignore[reportAttributeAccessIssue] # ← absolute import

# Type hint – tells Pylance exactly what settings is
from typing import Any
settings: Any = settings  # ← this line makes Pylance happy

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Financial Document Hallucination Guardrails (Peak Version)",
    description="Dynamic, policy-driven validation for financial extractions",
    version="2.0.0 (2026 peak)"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory audit (replace with DB in production)
audit_logs = {}

@app.post("/v1/validate_response", response_model=GuardrailOutput)
async def validate_response(input_data: RAGInput):
    start = time.time()
    audit_id = str(uuid.uuid4())

    result = await run_validation_ensemble(input_data)

    # Store for audit
    audit_logs[audit_id] = result.model_dump()

    # Use start to avoid unused variable warning
    processing_time = (time.time() - start) * 1000

    logger.info(
        f"Audit {audit_id} | Doc: {input_data.document_id or 'n/a'} | "
        f"Pass: {result.overall_passes} | Halluc: {result.hallucination_detected} | "
        f"Risk: {result.risk_level} | Time: {processing_time:.1f}ms"
    )

    return result

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.0-peak"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("hallucination_guardrails.main:app", host="0.0.0.0", port=8000, reload=True)
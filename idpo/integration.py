"""
Cross-Service Integration Layer
================================
Orchestrates the IDPO ↔ AHMN ↔ Guardrails ↔ XAI-HITL pipeline cycle.

Flow:
  1. IDPO → AHMN:  Get policy advice before processing
  2. IDPO:         Run extraction pipeline with advised policy
  3. IDPO → Guardrails:  Validate extraction output
  4. IDPO → XAI:   Get explainable analysis of results
  5. IDPO → AHMN:  Log outcome metrics so bandit learns
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import concurrent.futures

import httpx
from pathlib import Path

logger = logging.getLogger("idpo.integration")

# ---------------------------------------------------------------------------
# Policy store: maps policy_id → list of expected entity field names.
# Used to compute direct F1 against the policy's defined extraction targets.
# ---------------------------------------------------------------------------

def _load_expected_fields() -> dict[str, list[str]]:
    """Load explicit_entities per policy from policy_store.json."""
    store_path = Path(__file__).resolve().parents[1] / "configs" / "policy_store.json"
    mapping: dict[str, list[str]] = {}
    try:
        with open(store_path) as f:
            store = json.load(f)
        for policy in store.get("policies", []):
            pid = policy.get("policy_id", "")
            entities = (
                policy.get("actions", {})
                .get("extraction", {})
                .get("explicit_entities", [])
            )
            mapping[pid] = [e.lower() for e in entities]
    except Exception as exc:
        logger.warning("Could not load policy_store.json for F1 computation: %s", exc)
    return mapping

_POLICY_EXPECTED_FIELDS: dict[str, list[str]] = _load_expected_fields()
_POLICY_STORE_MTIME: float | None = None


def _maybe_refresh_expected_fields() -> None:
    """Reload policy expected fields if policy_store.json changed on disk."""
    global _POLICY_EXPECTED_FIELDS, _POLICY_STORE_MTIME
    store_path = Path(__file__).resolve().parents[1] / "configs" / "policy_store.json"
    try:
        mtime = store_path.stat().st_mtime
    except OSError:
        return

    if _POLICY_STORE_MTIME is None:
        _POLICY_STORE_MTIME = mtime
        return

    if mtime != _POLICY_STORE_MTIME:
        _POLICY_EXPECTED_FIELDS = _load_expected_fields()
        _POLICY_STORE_MTIME = mtime
        logger.info("Reloaded policy expected fields from policy_store.json")

# ---------------------------------------------------------------------------
# Service URLs — resolved from environment or Docker defaults
# ---------------------------------------------------------------------------
AHMN_URL = os.getenv("AHMN_SERVICE_URL", "http://ahmn:8001")
GUARDRAILS_URL = os.getenv("GUARDRAILS_SERVICE_URL", "http://guardrails:8002")
XAI_HITL_URL = os.getenv("XAI_HITL_SERVICE_URL", "http://xai-hitl:8003")

_TIMEOUT = 45.0
_XAI_TIMEOUT = 90.0          # XAI runs DistilBERT + LIME on CPU — needs more time
_CONNECT_TIMEOUT = 5.0
_MAX_RETRIES = 3

# Module-level reusable httpx client
_shared_client: httpx.Client | None = None

def _get_client() -> httpx.Client:
    """Get or create a reusable httpx client with connection pooling."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.Client(
            timeout=httpx.Timeout(_TIMEOUT, connect=_CONNECT_TIMEOUT),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _shared_client

def _close_client() -> None:
    """Cleanup shared client on process exit."""
    global _shared_client
    if _shared_client and not _shared_client.is_closed:
        _shared_client.close()
        logger.info("Shared httpx client closed")

atexit.register(_close_client)

def _request_with_retry(
    method: str,
    url: str,
    *,
    json_data: Any = None,
    max_retries: int = _MAX_RETRIES,
    timeout: float | None = None,
) -> httpx.Response:
    """Execute an HTTP request with exponential backoff retry.

    ReadTimeout is NOT retried — it means the service is processing
    (just slowly).  Retrying would only add to its request queue.
    """
    client = _get_client()
    last_exc: Exception | None = None
    req_timeout = httpx.Timeout(timeout or _TIMEOUT, connect=_CONNECT_TIMEOUT) if timeout else None
    for attempt in range(max_retries):
        try:
            resp = client.request(method, url, json=json_data, timeout=req_timeout)
            resp.raise_for_status()
            return resp
        except httpx.ReadTimeout:
            raise  # Don't retry — model is just slow, retrying queues more work
        except (httpx.ConnectError, httpx.WriteTimeout) as exc:
            last_exc = exc
            wait = min(2 ** attempt * 0.5, 8.0)
            logger.warning(
                "Retry %d/%d for %s %s: %s (wait %.1fs)",
                attempt + 1, max_retries, method, url, exc, wait,
            )
            time.sleep(wait)
        except httpx.HTTPStatusError:
            raise  # Don't retry 4xx / 5xx
    raise last_exc or RuntimeError(f"All {max_retries} retries exhausted for {method} {url}")

# ---------------------------------------------------------------------------
# Data classes for typed pipeline results
# ---------------------------------------------------------------------------
@dataclass
class AHMNAdvice:
    advice_id: str = ""
    policy_id: str = "default_policy"
    policy_data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    rabi_used: bool = False
    retrieval_source: str = "DEFAULT"
    n_neighbors: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "advice_id": self.advice_id,
            "policy_id": self.policy_id,
            "policy_data": self.policy_data,
            "confidence": self.confidence,
            "rabi_used": self.rabi_used,
            "retrieval_source": self.retrieval_source,
            "n_neighbors": self.n_neighbors,
            "error": self.error,
        }

@dataclass
class GuardrailResult:
    document_id: str = ""
    overall_passes: bool = True
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    processing_time_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "overall_passes": self.overall_passes,
            "validation_results": self.validation_results,
            "metrics": self.metrics,
            "processing_time_ms": self.processing_time_ms,
            "error": self.error,
        }

@dataclass
class ComponentExplanation:
    """Explanation for a single component (AHMN, IDPO, or Guardrails)."""
    component: str = ""  # "ahmn" | "idpo" | "guardrails"
    title: str = ""
    summary: str = ""
    details: list[dict[str, Any]] = field(default_factory=list)
    status: str = "info"  # "success" | "warning" | "error" | "info"
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "title": self.title,
            "summary": self.summary,
            "details": self.details,
            "status": self.status,
            "metrics": self.metrics,
        }


@dataclass
class XAIExplanation:
    document_id: str = ""
    answer: str = ""
    confidence: float = 0.0
    explanation: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    # New: component-level explanations
    component_explanations: list[ComponentExplanation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "answer": self.answer,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "error": self.error,
            "component_explanations": [c.to_dict() for c in self.component_explanations],
        }

@dataclass
class AHMNFeedback:
    status: str = "skipped"
    advice_id: str = ""
    policy_id_used: str = ""
    metrics_sent: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "advice_id": self.advice_id,
            "policy_id_used": self.policy_id_used,
            "metrics_sent": self.metrics_sent,
            "error": self.error,
        }

@dataclass
class IntegrationResult:
    # Per-document AHMN advices (one per doc, indexed by doc_id)
    ahmn_advices: list[AHMNAdvice] = field(default_factory=list)
    guardrails: list[GuardrailResult] = field(default_factory=list)
    xai_explanations: list[XAIExplanation] = field(default_factory=list)
    # Per-document feedback (one per doc)
    ahmn_feedbacks: list[AHMNFeedback] = field(default_factory=list)
    cycle_time_ms: float = 0.0
    skipped_guardrails: bool = False
    skipped_xai: bool = False

    @property
    def ahmn_advice(self) -> AHMNAdvice:
        """Backward-compatible alias for the first advice item."""
        return self.ahmn_advices[0] if self.ahmn_advices else AHMNAdvice()

    @property
    def ahmn_feedback(self) -> AHMNFeedback:
        """Backward-compatible alias for the first feedback item."""
        return self.ahmn_feedbacks[0] if self.ahmn_feedbacks else AHMNFeedback()

    def to_dict(self) -> dict:
        return {
            "ahmn_advices": [a.to_dict() for a in self.ahmn_advices],
            "guardrails": [g.to_dict() for g in self.guardrails],
            "xai_explanations": [x.to_dict() for x in self.xai_explanations],
            "ahmn_feedbacks": [f.to_dict() for f in self.ahmn_feedbacks],
            "cycle_time_ms": round(self.cycle_time_ms, 1),
            "skipped_guardrails": self.skipped_guardrails,
            "skipped_xai": self.skipped_xai,
            # Backward compatibility: provide first advice as ahmn_advice
            "ahmn_advice": self.ahmn_advice.to_dict(),
            "ahmn_feedback": self.ahmn_feedback.to_dict(),
        }

# ═══════════════════════════════════════════════════════════════════════════
# Step 1: AHMN Advice (pre-processing)
# ═══════════════════════════════════════════════════════════════════════════

def get_ahmn_advice(
    doc_type: str = "unknown",
    vendor: str | None = None,
    extra_context: dict[str, Any] | None = None,
    content_profile: str | None = None,
    doc_id: str | None = None,
) -> AHMNAdvice:
    """Ask AHMN for policy advice for a document.

    Args:
        doc_type: Document type (e.g., "invoice", "clinical_summary")
        vendor: Vendor cluster name
        extra_context: Additional context for policy selection
        content_profile: Content profile (e.g., "table-heavy", "text-heavy")
        doc_id: Document ID for tracking (optional)
    """
    advice = AHMNAdvice()
    try:
        payload: dict[str, Any] = {
            "doc_type": doc_type,
            "vendor": vendor,
            "extra_context": extra_context or {},
        }
        if content_profile:
            payload["content_profile"] = content_profile
        logger.info("Requesting AHMN advice: doc_type=%s, vendor=%s, content_profile=%s, doc_id=%s",
                    doc_type, vendor, content_profile, doc_id)
        resp = _request_with_retry("POST", f"{AHMN_URL}/advice", json_data=payload)
        data = resp.json()

        advice.advice_id = str(data.get("advice_id", ""))
        advice.policy_id = data.get("policy_id", "default_policy")
        advice.policy_data = data.get("policy_data", {})
        advice.confidence = data.get("confidence", 0.0)
        advice.rabi_used = data.get("rabi_used", False)
        advice.retrieval_source = data.get("retrieval_source", "DEFAULT")
        advice.n_neighbors = data.get("n_neighbors")
        logger.info(
            "AHMN advice received for %s: policy=%s confidence=%.3f source=%s",
            doc_id or "batch", advice.policy_id, advice.confidence, advice.retrieval_source,
        )
    except httpx.ConnectError:
        advice.error = "AHMN service unreachable"
        logger.warning("AHMN service unreachable at %s", AHMN_URL)
    except Exception as exc:
        advice.error = str(exc)
        logger.warning("AHMN advice failed: %s", exc)
    return advice


def get_per_doc_ahmn_advices(
    doc_records: list[dict[str, Any]],
) -> list[AHMNAdvice]:
    """Get AHMN policy advice for each document based on its actual doc_type.

    This is called AFTER DAE (Document Analysis) has classified each document,
    so we can request the appropriate policy for each document's actual type.

    Returns:
        List of AHMNAdvice objects, one per document (in same order as doc_records)
    """
    if not doc_records:
        return []

    def _advice_for_doc(doc: dict[str, Any]) -> AHMNAdvice:
        doc_id = doc.get("doc_id", "")
        doc_type = doc.get("doc_type", "unknown")
        vendor = doc.get("vendor_cluster") or doc.get("vendor")
        content_profile = doc.get("content_profile")
        quality_bin = doc.get("quality_bin", "medium")
        complexity_bin = doc.get("complexity_bin", "medium")

        return get_ahmn_advice(
            doc_type=doc_type,
            vendor=vendor,
            content_profile=content_profile,
            extra_context={
                "quality_bin": quality_bin,
                "complexity_bin": complexity_bin,
                "entity_count": doc.get("entity_count", 0),
            },
            doc_id=doc_id,
        )

    if len(doc_records) == 1:
        return [_advice_for_doc(doc_records[0])]

    # Parallelize network-bound advice calls across documents.
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(doc_records))) as pool:
        futures = [pool.submit(_advice_for_doc, doc) for doc in doc_records]
        return [f.result() for f in futures]

# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Guardrails Validation (post-processing)
# ═══════════════════════════════════════════════════════════════════════════

def _validate_single_doc(
    doc: dict[str, Any],
    client: httpx.Client,
) -> GuardrailResult:
    """Validate a single document with Guardrails."""
    # Map pipeline doc_types to Guardrails-recognized DocumentType values
    _DOC_TYPE_MAP = {
        "table_document": "Invoice",
        "form_document": "Generic",
        "scanned_document": "Generic",
        "text_document": "Generic",
        "mixed_document": "Generic",
        "unknown": "Generic",
        "invoice": "Invoice",
        "receipt": "Receipt",
        "purchase_order": "PurchaseOrder",
        "bank_statement": "BankStatement",
        "insurance_claim": "InsuranceClaim",
        "clinical_summary": "ClinicalSummary",
        "medication_dosage": "MedicationDosage",
    }
    gr = GuardrailResult(document_id=str(doc.get("doc_id", "")))
    try:
        # Use structured entities dict if available, else fall back to field_ prefix
        entities = doc.get("entities", {})
        if not entities or not isinstance(entities, dict):
            entities = {}
            for key, val in doc.items():
                if key.startswith("field_") and not key.endswith(("_confidence", "_page", "_span", "_source")):
                    entities[key.replace("field_", "")] = val

        source_contexts = []
        summary = doc.get("summary", "")
        if summary:
            source_contexts.append(str(summary))

        raw_doc_type = str(doc.get("doc_type", "unknown"))
        # Also check vendor_cluster for more specific mapping
        vendor = str(doc.get("vendor_cluster", ""))
        mapped_type = _DOC_TYPE_MAP.get(vendor, _DOC_TYPE_MAP.get(raw_doc_type, raw_doc_type))

        payload = {
            "document_context": {
                "doc_type": mapped_type,
                "vendor": vendor,
                "quality_bin": str(doc.get("quality_bin", "medium")),
            },
            "query": f"Extract fields from {doc.get('doc_type', 'document')}: {', '.join(entities.keys()) if entities else 'all fields'}",
            "answer_json": json.dumps(entities) if entities else json.dumps(doc),
            "source_contexts": source_contexts if source_contexts else ["No source context available"],
            "document_id": str(doc.get("doc_id", "")),
        }

        logger.info("Validating doc %s with Guardrails", doc.get("doc_id", "?"))
        resp = _request_with_retry("POST", f"{GUARDRAILS_URL}/guardrails/validate", json_data=payload)
        data = resp.json()

        gr.overall_passes = data.get("overall_passes", True)
        gr.validation_results = data.get("validation_results", [])
        gr.metrics = data.get("metrics", {})
        gr.processing_time_ms = data.get("processing_time_ms", 0.0)
        logger.info(
            "Guardrails result for %s: passes=%s checks=%d",
            doc.get("doc_id", "?"),
            gr.overall_passes,
            len(gr.validation_results),
        )
    except httpx.ConnectError:
        gr.error = "Guardrails service unreachable"
        logger.warning("Guardrails service unreachable at %s", GUARDRAILS_URL)
    except (httpx.RemoteProtocolError, httpx.ReadError):
        gr.error = "Guardrails service disconnected — the container may have run out of memory"
        logger.warning("Guardrails service disconnected for %s (possible OOM)", doc.get("doc_id", "?"))
    except httpx.ReadTimeout:
        gr.error = "Guardrails validation timed out"
        logger.warning("Guardrails timed out for %s", doc.get("doc_id", "?"))
    except Exception as exc:
        gr.error = str(exc)
        logger.warning("Guardrails validation failed for %s: %s", doc.get("doc_id", "?"), exc)
    return gr

def validate_with_guardrails(
    doc_records: list[dict[str, Any]],
) -> list[GuardrailResult]:
    """Send extraction results to Guardrails for multi-layer validation."""
    if not doc_records:
        return []
    client = _get_client()
    if len(doc_records) == 1:
        return [_validate_single_doc(doc_records[0], client)]
    # Parallelize validation across documents
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(doc_records))) as pool:
        futures = [pool.submit(_validate_single_doc, doc, client) for doc in doc_records]
        return [f.result() for f in futures]

# ═══════════════════════════════════════════════════════════════════════════
# Step 4: XAI Explanation
# ═══════════════════════════════════════════════════════════════════════════

def _build_ahmn_explanation(doc: dict[str, Any], ahmn_advice: AHMNAdvice | None) -> ComponentExplanation:
    """Build AHMN policy selection explanation from actual data."""
    if not ahmn_advice or ahmn_advice.error:
        return ComponentExplanation(
            component="ahmn",
            title="AHMN Policy Selection",
            summary="Policy selection unavailable" if not ahmn_advice else ahmn_advice.error or "Error",
            status="error" if ahmn_advice and ahmn_advice.error else "info",
        )

    policy_id = ahmn_advice.policy_id
    confidence = ahmn_advice.confidence
    rabi_used = ahmn_advice.rabi_used
    retrieval_source = ahmn_advice.retrieval_source
    policy_data = ahmn_advice.policy_data or {}

    # Build explanation based on how the policy was selected
    details = []
    if rabi_used:
        details.append({
            "step": 1,
            "action": "RABI Neighbor Search",
            "description": f"Found {ahmn_advice.n_neighbors or 'N'} similar document contexts in memory",
            "outcome": "Used neighbor-based retrieval for policy selection",
        })
    else:
        details.append({
            "step": 1,
            "action": "Thompson Sampling",
            "description": "Selected policy using multi-armed bandit with alpha/beta priors",
            "outcome": f"Confidence score: {confidence:.1%}",
        })

    details.append({
        "step": 2,
        "action": "Policy Selected",
        "description": f"Policy '{policy_id}' chosen from {retrieval_source}",
        "outcome": policy_data.get("action", "Document processing"),
    })

    # Summary based on confidence
    if confidence >= 0.8:
        summary = f"High confidence ({confidence:.0%}) - Policy '{policy_id}' strongly recommended based on past performance"
    elif confidence >= 0.5:
        summary = f"Moderate confidence ({confidence:.0%}) - Policy '{policy_id}' selected, may benefit from more data"
    else:
        summary = f"Low confidence ({confidence:.0%}) - Policy '{policy_id}' selected, exploring new approach"

    return ComponentExplanation(
        component="ahmn",
        title="AHMN Policy Selection",
        summary=summary,
        details=details,
        status="success" if confidence >= 0.5 else "warning",
        metrics={
            "confidence": round(confidence, 3),
            "policy_id": policy_id,
            "rabi_used": rabi_used,
            "retrieval_source": retrieval_source,
        },
    )


def _build_idpo_explanation(doc: dict[str, Any]) -> ComponentExplanation:
    """Build IDPO orchestration explanation from extraction metadata."""
    details = []
    step = 0

    # Model selection
    model_used = doc.get("model_used", "default")
    model_reason = doc.get("model_reason", "")
    if model_used:
        step += 1
        details.append({
            "step": step,
            "action": "Model Selection",
            "description": f"Selected model: {model_used}",
            "outcome": model_reason or "Based on document complexity",
        })

    # Policy/Plan info
    policy_name = doc.get("policy_name", doc.get("policy_id", ""))
    plan_source = doc.get("plan_source", "")
    if policy_name:
        step += 1
        details.append({
            "step": step,
            "action": "Execution Plan",
            "description": f"Applied policy: {policy_name}",
            "outcome": f"Plan source: {plan_source}" if plan_source else "Dynamic planning",
        })

    # Document analysis
    doc_type = doc.get("doc_type", "unknown")
    quality_bin = doc.get("quality_bin", "medium")
    complexity_bin = doc.get("complexity_bin", "medium")
    step += 1
    details.append({
        "step": step,
        "action": "Document Analysis",
        "description": f"Classified as '{doc_type}' document",
        "outcome": f"Quality: {quality_bin}, Complexity: {complexity_bin}",
    })

    # Entity extraction
    entity_count = doc.get("entity_count", 0)
    entities = doc.get("entities", {})
    if isinstance(entities, dict):
        field_names = list(entities.keys())[:5]
    else:
        field_names = []
    step += 1
    details.append({
        "step": step,
        "action": "Entity Extraction",
        "description": f"Extracted {entity_count} entities from document",
        "outcome": f"Fields: {', '.join(field_names)}" if field_names else "No fields extracted",
    })

    # Stage signals if available
    stage_signals = doc.get("stage_signals", [])
    if stage_signals and isinstance(stage_signals, list):
        stages_completed = len([s for s in stage_signals if isinstance(s, dict) and s.get("completed", True)])
        step += 1
        details.append({
            "step": step,
            "action": "Pipeline Stages",
            "description": f"Completed {stages_completed}/{len(stage_signals)} processing stages",
            "outcome": "All stages successful" if stages_completed == len(stage_signals) else "Some stages had issues",
        })

    # Calculate overall status
    status = "success" if entity_count > 0 else "warning"
    summary = f"Extracted {entity_count} fields from {doc_type} document using {model_used} model"

    return ComponentExplanation(
        component="idpo",
        title="IDPO Extraction Pipeline",
        summary=summary,
        details=details,
        status=status,
        metrics={
            "entity_count": entity_count,
            "doc_type": doc_type,
            "model_used": model_used,
            "quality_bin": quality_bin,
            "complexity_bin": complexity_bin,
        },
    )


def _build_guardrails_explanation(gr: GuardrailResult | None) -> ComponentExplanation:
    """Build Guardrails validation explanation from check results."""
    if not gr:
        return ComponentExplanation(
            component="guardrails",
            title="Guardrails Validation",
            summary="Validation skipped",
            status="info",
        )

    if gr.error:
        return ComponentExplanation(
            component="guardrails",
            title="Guardrails Validation",
            summary=f"Validation error: {gr.error}",
            status="error",
        )

    details = []
    passed_checks = 0
    failed_checks = []

    for i, check in enumerate(gr.validation_results, 1):
        check_name = check.get("name", f"Check {i}").replace("_", " ").title()
        is_pass = check.get("is_pass", False)
        score = check.get("score", 0.0)
        check_details = check.get("details", "")

        if is_pass:
            passed_checks += 1

        details.append({
            "step": i,
            "action": check_name,
            "description": check_details or f"Score: {score:.2f}",
            "outcome": "PASS" if is_pass else "FAIL",
            "score": round(score, 3),
            "passed": is_pass,
        })

        if not is_pass:
            failed_checks.append(check_name)

    total_checks = len(gr.validation_results)
    if gr.overall_passes:
        summary = f"All {total_checks} validation checks passed"
        status = "success"
    elif passed_checks > 0:
        summary = f"{passed_checks}/{total_checks} checks passed. Failed: {', '.join(failed_checks)}"
        status = "warning"
    else:
        summary = f"All {total_checks} validation checks failed"
        status = "error"

    return ComponentExplanation(
        component="guardrails",
        title="Guardrails Validation",
        summary=summary,
        details=details,
        status=status,
        metrics={
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": len(failed_checks),
            "overall_passes": gr.overall_passes,
            "processing_time_ms": round(gr.processing_time_ms, 1),
        },
    )


def _explain_single_doc(
    doc: dict[str, Any],
    gr: GuardrailResult | None,
    ahmn_advice: AHMNAdvice | None = None,
) -> XAIExplanation:
    """Generate component-level explanations for a document.

    Instead of calling an external XAI service with SHAP/LIME, this builds
    real explanations from the actual processing data:
    1. AHMN: Why this policy was selected
    2. IDPO: What extraction steps were performed
    3. Guardrails: How validation checks passed/failed
    """
    xai = XAIExplanation(document_id=str(doc.get("doc_id", "")))

    try:
        # Build component explanations from actual data
        ahmn_exp = _build_ahmn_explanation(doc, ahmn_advice)
        idpo_exp = _build_idpo_explanation(doc)
        guardrails_exp = _build_guardrails_explanation(gr)

        xai.component_explanations = [ahmn_exp, idpo_exp, guardrails_exp]

        # Calculate overall confidence from components
        ahmn_conf = ahmn_advice.confidence if ahmn_advice and not ahmn_advice.error else 0.5
        gr_conf = 1.0 if (gr and gr.overall_passes) else (0.5 if gr else 0.7)
        entity_count = doc.get("entity_count", 0)
        idpo_conf = min(1.0, entity_count / 10.0) if entity_count > 0 else 0.3

        xai.confidence = (ahmn_conf * 0.3 + idpo_conf * 0.4 + gr_conf * 0.3)

        # Build summary answer
        entity_count = doc.get("entity_count", 0)
        doc_type = doc.get("doc_type", "document")
        validation_status = "passed" if (gr and gr.overall_passes) else "needs review"

        xai.answer = (
            f"Extracted {entity_count} fields from {doc_type} document. "
            f"Policy '{ahmn_advice.policy_id if ahmn_advice else 'default'}' "
            f"selected with {ahmn_conf:.0%} confidence. "
            f"Validation {validation_status}."
        )

        logger.info(
            "Component explanations built for %s: confidence=%.3f",
            doc.get("doc_id", "?"), xai.confidence,
        )
    except Exception as exc:
        xai.error = str(exc)
        logger.warning("Failed to build explanations for %s: %s", doc.get("doc_id", "?"), exc)

    return xai

def get_xai_explanations(
    doc_records: list[dict[str, Any]],
    guardrail_results: list[GuardrailResult],
    ahmn_advices: list[AHMNAdvice] | None = None,
) -> list[XAIExplanation]:
    """Build component-level explanations for extraction results.

    Instead of calling an external XAI service, this generates real
    explanations from the actual processing data (AHMN, IDPO, Guardrails).

    Args:
        doc_records: List of document records from extraction
        guardrail_results: List of guardrail results (one per doc)
        ahmn_advices: List of per-doc AHMN advices (one per doc)
    """
    if not doc_records:
        return []

    # Ensure ahmn_advices has the right length
    advices = ahmn_advices or []
    while len(advices) < len(doc_records):
        advices.append(AHMNAdvice())

    if len(doc_records) == 1:
        gr = guardrail_results[0] if guardrail_results else None
        return [_explain_single_doc(doc_records[0], gr, advices[0])]

    # Parallelize explanation building
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(doc_records))) as pool:
        futures = []
        for i, doc in enumerate(doc_records):
            gr = guardrail_results[i] if i < len(guardrail_results) else None
            advice = advices[i] if i < len(advices) else AHMNAdvice()
            futures.append(pool.submit(_explain_single_doc, doc, gr, advice))
        return [f.result() for f in futures]

# ═══════════════════════════════════════════════════════════════════════════
# Step 5: AHMN Feedback Loop (post-processing metrics)
# ═══════════════════════════════════════════════════════════════════════════

def log_per_doc_ahmn_feedbacks(
    doc_records: list[dict[str, Any]],
    ahmn_advices: list[AHMNAdvice],
    guardrail_results: list[GuardrailResult],
    processing_time_ms: float,
) -> list[AHMNFeedback]:
    """Log per-document feedback to AHMN.

    Each document gets its own feedback with:
    - Its own advice_id (from per-doc AHMN call)
    - Its own policy_id (what was actually used)
    - Its own F1 score and metrics

    Returns:
        List of AHMNFeedback objects, one per document
    """
    if not doc_records:
        return []

    per_doc_time_ms = processing_time_ms / max(len(doc_records), 1)

    def _feedback_for_index(i: int, doc: dict[str, Any]) -> AHMNFeedback:
        advice = ahmn_advices[i] if i < len(ahmn_advices) else AHMNAdvice()
        gr = guardrail_results[i] if i < len(guardrail_results) else GuardrailResult()
        return log_ahmn_feedback(
            advice=advice,
            doc_records=[doc],  # Single doc
            guardrail_results=[gr] if gr.document_id else [],
            processing_time_ms=per_doc_time_ms,
            actual_policy_id=doc.get("policy_id"),
        )

    if len(doc_records) == 1:
        return [_feedback_for_index(0, doc_records[0])]

    # Parallelize network-bound feedback calls across documents.
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(doc_records))) as pool:
        futures = [pool.submit(_feedback_for_index, i, doc) for i, doc in enumerate(doc_records)]
        return [f.result() for f in futures]


def log_ahmn_feedback(
    advice: AHMNAdvice,
    doc_records: list[dict[str, Any]],
    guardrail_results: list[GuardrailResult],
    processing_time_ms: float,
    actual_policy_id: str | None = None,
    actual_doc_type: str | None = None,
    actual_content_profile: str | None = None,
) -> AHMNFeedback:
    """Send outcome metrics to AHMN so the bandit learns.
    
    CRITICAL: We send the ACTUAL policy IDPO used (from doc_records),
    not what AHMN recommended. This is how AHMN learns which policies
    work for which document types.
    """
    feedback = AHMNFeedback()
    if not advice.advice_id:
        feedback.status = "skipped"
        feedback.error = "No advice_id to reference"
        return feedback

    try:
        _maybe_refresh_expected_fields()

        # Determine the actual policy IDPO used
        used_policy = actual_policy_id
        if not used_policy:
            for doc in doc_records:
                pid = doc.get("policy_id")
                if pid and pid != "default_policy":
                    used_policy = pid
                    break
        if not used_policy:
            used_policy = advice.policy_id or "default_policy"

        # ----- Direct F1 Score Computation -----
        # Instead of a proxy, we compute set-based precision/recall/F1
        # using the policy's explicit_entities as the ground truth
        # field set and the actually extracted entity keys as predictions.

        expected_fields = _POLICY_EXPECTED_FIELDS.get(used_policy, [])

        doc_f1_scores: list[float] = []
        doc_precisions: list[float] = []
        doc_recalls: list[float] = []
        for doc in doc_records:
            # Collect extracted entity keys that were EXPLICITLY targeted by the
            # policy (is_explicit=True) with confidence >= 0.5.  Including all
            # discovered entities would inflate the denominator and crush
            # precision — only policy-targeted fields should be measured.
            extracted_keys: set[str] = set()
            details = doc.get("entity_details", [])
            if details:
                for ed in details:
                    key = (ed.get("key") or "") if isinstance(ed, dict) else getattr(ed, "key", "")
                    conf = ed.get("confidence", 0) if isinstance(ed, dict) else getattr(ed, "confidence", 0)
                    is_explicit = (ed.get("is_explicit", False) if isinstance(ed, dict)
                                   else getattr(ed, "is_explicit", False))
                    if key and isinstance(conf, (int, float)) and conf >= 0.5 and is_explicit:
                        extracted_keys.add(key.lower())
            else:
                # Fallback: field_confidence dict (no is_explicit flag available,
                # so include all with sufficient confidence)
                fc = doc.get("field_confidence", {})
                if fc and isinstance(fc, dict):
                    for k, v in fc.items():
                        if isinstance(v, (int, float)) and v >= 0.5:
                            extracted_keys.add(k.lower())

            if expected_fields:
                # Direct set-based F1
                expected_set = set(expected_fields)
                true_positives = extracted_keys & expected_set
                tp = len(true_positives)
                precision = tp / len(extracted_keys) if extracted_keys else 0.0
                recall = tp / len(expected_set)
                if precision + recall > 0:
                    f1 = 2 * precision * recall / (precision + recall)
                else:
                    f1 = 0.0
            else:
                # No expected fields defined (default policy):
                # Derive separate precision/recall proxies from the
                # confidence distribution instead of mirroring one value.
                all_confs: list[float] = []
                for ed in details:
                    c = ed.get("confidence", 0) if isinstance(ed, dict) else getattr(ed, "confidence", 0)
                    if isinstance(c, (int, float)) and c > 0:
                        all_confs.append(float(c))
                if not all_confs:
                    fc = doc.get("field_confidence", {})
                    if fc and isinstance(fc, dict):
                        all_confs = [float(v) for v in fc.values()
                                     if isinstance(v, (int, float)) and v > 0]
                if all_confs:
                    # Precision proxy: mean confidence of entities above
                    # acceptance threshold (quality of accepted extractions)
                    accepted = [c for c in all_confs if c >= 0.5]
                    precision = sum(accepted) / len(accepted) if accepted else 0.0
                    # Recall proxy: fraction of entities that exceeded
                    # the acceptance threshold (extraction coverage)
                    recall = len(accepted) / len(all_confs)
                    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
                else:
                    f1 = 0.0
                    precision = 0.0
                    recall = 0.0

            doc_f1_scores.append(f1)
            doc_precisions.append(precision)
            doc_recalls.append(recall)

        f1_score = sum(doc_f1_scores) / len(doc_f1_scores) if doc_f1_scores else 0.0
        f1_score = max(0.0, min(1.0, f1_score))
        avg_precision = sum(doc_precisions) / len(doc_precisions) if doc_precisions else 0.0
        avg_recall = sum(doc_recalls) / len(doc_recalls) if doc_recalls else 0.0

        total_docs = len(doc_records)
        successful_validations = sum(1 for gr in guardrail_results if gr.overall_passes and not gr.error)
        guardrails_ran = len(guardrail_results) > 0 and not all(gr.error for gr in guardrail_results)
        success_rate = successful_validations / max(total_docs, 1) if guardrails_ran else 1.0

        metrics = {
            "f1_score": round(f1_score, 4),
            "cost": total_docs * 0.01,
            "processing_time_ms": round(processing_time_ms, 1),
            "success": f1_score >= 0.4 or success_rate >= 0.5,
            "precision": round(avg_precision, 4),
            "recall": round(avg_recall, 4),
        }

        # Extract the REAL document context discovered during pipeline
        # processing so AHMN stores the correct doc_type (not the pre-
        # processing guess which is often "unknown").
        real_context: dict[str, Any] = {}
        for doc in doc_records:
            dt = doc.get("doc_type") or doc.get("metadata", {}).get("doc_type")
            if dt and dt != "unknown":
                real_context["doc_type"] = dt
                real_context["vendor"] = doc.get("vendor_cluster") or doc.get("vendor")
                real_context["content_profile"] = (
                    doc.get("content_profile")
                    or doc.get("metadata", {}).get("content_profile")
                )
                break

        # Fallback to caller-provided runtime context if doc_records did not
        # contain a non-unknown doc_type/content_profile.
        if "doc_type" not in real_context and actual_doc_type:
            real_context["doc_type"] = actual_doc_type
        if "content_profile" not in real_context and actual_content_profile:
            real_context["content_profile"] = actual_content_profile

        payload: dict[str, Any] = {
            "advice_id": advice.advice_id,
            "policy_id_used": used_policy,
            "metrics": metrics,
        }
        if real_context:
            payload["document_context"] = real_context

        logger.info(
            "Logging AHMN feedback: advice=%s f1=%.3f success=%s actual_policy=%s doc_type=%s",
            advice.advice_id, f1_score, metrics["success"], used_policy,
            real_context.get("doc_type", "(not overridden)"),
        )
        resp = _request_with_retry("POST", f"{AHMN_URL}/advice/log", json_data=payload)

        feedback.status = "logged"
        feedback.advice_id = advice.advice_id
        feedback.policy_id_used = used_policy
        feedback.metrics_sent = metrics
        logger.info("AHMN feedback logged successfully")
    except httpx.ConnectError:
        feedback.status = "failed"
        feedback.error = "AHMN service unreachable"
        logger.warning("AHMN service unreachable for feedback at %s", AHMN_URL)
    except Exception as exc:
        feedback.status = "failed"
        feedback.error = str(exc)
        logger.warning("AHMN feedback failed: %s", exc)
    return feedback

# ═══════════════════════════════════════════════════════════════════════════
# Full Integration Cycle
# ═══════════════════════════════════════════════════════════════════════════

def run_integration_cycle(
    doc_records: list[dict[str, Any]],
    processing_time_ms: float,
    ahmn_advices: list[AHMNAdvice] | None = None,
    skip_guardrails: bool = False,
    skip_xai: bool = False,
    actual_policy_id: str | None = None,
    actual_doc_type: str | None = None,
    actual_content_profile: str | None = None,
) -> IntegrationResult:
    """
    Execute the post-processing integration cycle with per-document AHMN:
      1. Per-doc AHMN advice (based on actual doc_type from DAE)
      2. Guardrails validation (skippable)
      3. XAI explanation (skippable)
      4. Per-doc AHMN feedback loop

    Args:
        doc_records: Documents with their actual doc_types from DAE
        processing_time_ms: Total processing time
        ahmn_advices: Pre-fetched per-doc advices (if None, will be fetched here)
        skip_guardrails: Skip guardrails validation
        skip_xai: Skip XAI explanations
    """
    cycle_start = time.time()
    result = IntegrationResult()
    result.skipped_guardrails = skip_guardrails
    result.skipped_xai = skip_xai

    # Step 1: Per-document AHMN advice (if not already provided)
    if ahmn_advices:
        result.ahmn_advices = ahmn_advices
    else:
        logger.info("Requesting per-document AHMN advices for %d docs", len(doc_records))
        result.ahmn_advices = get_per_doc_ahmn_advices(doc_records)

    # Step 2: Guardrails validation
    if skip_guardrails:
        logger.info("Guardrails validation skipped by user")
        result.guardrails = []
    else:
        result.guardrails = validate_with_guardrails(doc_records)

    # Step 3: Component-level explanations with per-doc advice
    if skip_xai:
        logger.info("Component explanations skipped by user")
        result.xai_explanations = []
    else:
        result.xai_explanations = get_xai_explanations(
            doc_records, result.guardrails, result.ahmn_advices
        )

    # Step 4: Per-document AHMN feedback loop
    if result.ahmn_advices:
        has_valid_advices = any(a.advice_id for a in result.ahmn_advices)
        if has_valid_advices:
            result.ahmn_feedbacks = log_per_doc_ahmn_feedbacks(
                doc_records, result.ahmn_advices, result.guardrails, processing_time_ms
            )
        else:
            result.ahmn_feedbacks = []
    else:
        result.ahmn_feedbacks = []

    result.cycle_time_ms = (time.time() - cycle_start) * 1000
    logger.info("Integration cycle completed in %.1f ms for %d docs", result.cycle_time_ms, len(doc_records))
    return result

# ═══════════════════════════════════════════════════════════════════════════
# HITL → AHMN Bridge: forward human corrections as learning signals
# ═══════════════════════════════════════════════════════════════════════════

def forward_hitl_correction(
    advice_id: str,
    feedback_type: str,
) -> dict:
    """
    Forward a human HITL correction to AHMN's /advice/feedback endpoint.
    This sets the human_corrected flag on the MTM outcome so AHMN can
    learn from human review.

    feedback_type: 'correct' | 'incorrect' | 'partially_correct' | 'needs_more_context'
    """
    human_corrected = feedback_type != "correct"

    payload = {
        "advice_id": advice_id,
        "human_corrected": human_corrected,
        "feedback_type": feedback_type,
    }

    try:
        resp = _request_with_retry("POST", f"{AHMN_URL}/advice/feedback", json_data=payload)
        logger.info(
            "HITL correction forwarded to AHMN: advice=%s type=%s human_corrected=%s",
            advice_id, feedback_type, human_corrected,
        )
        return {"status": "forwarded", "human_corrected": human_corrected}
    except Exception as exc:
        logger.warning("Failed to forward HITL correction to AHMN: %s", exc)
        return {"status": "failed", "error": str(exc)}

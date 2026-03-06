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
class XAIExplanation:
    document_id: str = ""
    answer: str = ""
    confidence: float = 0.0
    explanation: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "answer": self.answer,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "error": self.error,
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
    ahmn_advice: AHMNAdvice = field(default_factory=AHMNAdvice)
    guardrails: list[GuardrailResult] = field(default_factory=list)
    xai_explanations: list[XAIExplanation] = field(default_factory=list)
    ahmn_feedback: AHMNFeedback = field(default_factory=AHMNFeedback)
    cycle_time_ms: float = 0.0
    skipped_guardrails: bool = False
    skipped_xai: bool = False

    def to_dict(self) -> dict:
        return {
            "ahmn_advice": self.ahmn_advice.to_dict(),
            "guardrails": [g.to_dict() for g in self.guardrails],
            "xai_explanations": [x.to_dict() for x in self.xai_explanations],
            "ahmn_feedback": self.ahmn_feedback.to_dict(),
            "cycle_time_ms": round(self.cycle_time_ms, 1),
            "skipped_guardrails": self.skipped_guardrails,
            "skipped_xai": self.skipped_xai,
        }

# ═══════════════════════════════════════════════════════════════════════════
# Step 1: AHMN Advice (pre-processing)
# ═══════════════════════════════════════════════════════════════════════════

def get_ahmn_advice(
    doc_type: str = "unknown",
    vendor: str | None = None,
    extra_context: dict[str, Any] | None = None,
    content_profile: str | None = None,
) -> AHMNAdvice:
    """Ask AHMN for policy advice before document processing."""
    advice = AHMNAdvice()
    try:
        payload: dict[str, Any] = {
            "doc_type": doc_type,
            "vendor": vendor,
            "extra_context": extra_context or {},
        }
        if content_profile:
            payload["content_profile"] = content_profile
        logger.info("Requesting AHMN advice: doc_type=%s, vendor=%s, content_profile=%s", doc_type, vendor, content_profile)
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
            "AHMN advice received: policy=%s confidence=%.3f source=%s",
            advice.policy_id, advice.confidence, advice.retrieval_source,
        )
    except httpx.ConnectError:
        advice.error = "AHMN service unreachable"
        logger.warning("AHMN service unreachable at %s", AHMN_URL)
    except Exception as exc:
        advice.error = str(exc)
        logger.warning("AHMN advice failed: %s", exc)
    return advice

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

def _explain_single_doc(
    doc: dict[str, Any],
    gr: GuardrailResult | None,
    client: httpx.Client,
) -> XAIExplanation:
    """Get XAI explanation for a single document."""
    xai = XAIExplanation(document_id=str(doc.get("doc_id", "")))
    try:
        summary = doc.get("summary", "")
        doc_type = doc.get("doc_type", "document")
        entity_count = doc.get("entity_count", 0)
        quality = doc.get("quality_bin", "medium")

        validation_status = "passed" if (gr and gr.overall_passes) else "needs review"
        checks_passed = len([v for v in (gr.validation_results if gr else []) if v.get("is_pass")])
        total_checks = len(gr.validation_results) if gr else 0

        paragraph = (
            f"Document type: {doc_type}. Quality: {quality}. "
            f"Extracted {entity_count} entities. "
            f"Guardrails validation: {validation_status} "
            f"({checks_passed}/{total_checks} checks passed). "
            f"Summary: {summary[:500] if summary else 'No summary available.'}"
        )

        question = (
            f"Analyze the extraction quality and explain whether the results "
            f"for this {doc_type} document are reliable. "
            f"What is the confidence assessment?"
        )

        logger.info("Requesting XAI explanation for doc %s", doc.get("doc_id", "?"))
        resp = _request_with_retry(
            "POST",
            f"{XAI_HITL_URL}/xai/ask",
            json_data={"paragraph": paragraph, "question": question},
            timeout=_XAI_TIMEOUT,
        )
        data = resp.json()

        xai.answer = data.get("answer", "")
        xai.confidence = data.get("confidence", 0.0)
        xai.explanation = data.get("explanation", {})
        logger.info(
            "XAI explanation for %s: confidence=%.3f",
            doc.get("doc_id", "?"), xai.confidence,
        )
    except httpx.ConnectError:
        xai.error = "XAI service unreachable"
        logger.warning("XAI service unreachable at %s", XAI_HITL_URL)
    except Exception as exc:
        xai.error = str(exc)
        logger.warning("XAI explanation failed for %s: %s", doc.get("doc_id", "?"), exc)
    return xai

def get_xai_explanations(
    doc_records: list[dict[str, Any]],
    guardrail_results: list[GuardrailResult],
) -> list[XAIExplanation]:
    """Get XAI explanations for extraction results (parallelized)."""
    if not doc_records:
        return []
    client = _get_client()
    if len(doc_records) == 1:
        gr = guardrail_results[0] if guardrail_results else None
        return [_explain_single_doc(doc_records[0], gr, client)]
    # Parallelize XAI calls
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(doc_records))) as pool:
        futures = []
        for i, doc in enumerate(doc_records):
            gr = guardrail_results[i] if i < len(guardrail_results) else None
            futures.append(pool.submit(_explain_single_doc, doc, gr, client))
        return [f.result() for f in futures]

# ═══════════════════════════════════════════════════════════════════════════
# Step 5: AHMN Feedback Loop (post-processing metrics)
# ═══════════════════════════════════════════════════════════════════════════

def log_ahmn_feedback(
    advice: AHMNAdvice,
    doc_records: list[dict[str, Any]],
    guardrail_results: list[GuardrailResult],
    processing_time_ms: float,
    actual_policy_id: str | None = None,
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
        for doc in doc_records:
            # Collect extracted entity keys (with confidence >= 0.5 as "valid")
            extracted_keys: set[str] = set()
            details = doc.get("entity_details", [])
            if details:
                for ed in details:
                    key = (ed.get("key") or "") if isinstance(ed, dict) else getattr(ed, "key", "")
                    conf = ed.get("confidence", 0) if isinstance(ed, dict) else getattr(ed, "confidence", 0)
                    if key and isinstance(conf, (int, float)) and conf >= 0.5:
                        extracted_keys.add(key.lower())
            else:
                # Fallback: field_confidence dict
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
                # Use mean confidence of extracted entities as quality signal
                confs: list[float] = []
                for ed in details:
                    c = ed.get("confidence", 0) if isinstance(ed, dict) else getattr(ed, "confidence", 0)
                    if isinstance(c, (int, float)) and c > 0:
                        confs.append(float(c))
                f1 = sum(confs) / len(confs) if confs else 0.0

            doc_f1_scores.append(f1)

        f1_score = sum(doc_f1_scores) / len(doc_f1_scores) if doc_f1_scores else 0.0
        f1_score = max(0.0, min(1.0, f1_score))

        total_docs = len(doc_records)
        successful_validations = sum(1 for gr in guardrail_results if gr.overall_passes and not gr.error)
        guardrails_ran = len(guardrail_results) > 0 and not all(gr.error for gr in guardrail_results)
        success_rate = successful_validations / max(total_docs, 1) if guardrails_ran else 1.0

        metrics = {
            "f1_score": round(f1_score, 4),
            "cost": total_docs * 0.01,
            "processing_time_ms": round(processing_time_ms, 1),
            "success": f1_score >= 0.4 or success_rate >= 0.5,
        }

        payload = {
            "advice_id": advice.advice_id,
            "policy_id_used": used_policy,
            "metrics": metrics,
        }

        logger.info(
            "Logging AHMN feedback: advice=%s f1=%.3f success=%s actual_policy=%s",
            advice.advice_id, f1_score, metrics["success"], used_policy,
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
    ahmn_advice: AHMNAdvice | None = None,
    skip_guardrails: bool = False,
    skip_xai: bool = False,
    actual_policy_id: str | None = None,
) -> IntegrationResult:
    """
    Execute the post-processing integration cycle:
      1. Guardrails validation  (skippable)
      2. XAI explanation        (skippable)
      3. AHMN feedback loop

    The AHMN advice (step 1) should be obtained BEFORE processing and
    passed in here so the feedback loop can reference it.
    """
    cycle_start = time.time()
    result = IntegrationResult()

    # Use provided advice or create empty placeholder
    result.ahmn_advice = ahmn_advice or AHMNAdvice()
    result.skipped_guardrails = skip_guardrails
    result.skipped_xai = skip_xai

    # Step 3: Guardrails validation
    if skip_guardrails:
        logger.info("Guardrails validation skipped by user")
        result.guardrails = []
    else:
        result.guardrails = validate_with_guardrails(doc_records)

    # Step 4: XAI explanations
    if skip_xai:
        logger.info("XAI explanations skipped by user")
        result.xai_explanations = []
    else:
        result.xai_explanations = get_xai_explanations(doc_records, result.guardrails)

    # Step 5: AHMN feedback loop
    if ahmn_advice and ahmn_advice.advice_id:
        result.ahmn_feedback = log_ahmn_feedback(
            ahmn_advice, doc_records, result.guardrails, processing_time_ms,
            actual_policy_id=actual_policy_id,
        )

    result.cycle_time_ms = (time.time() - cycle_start) * 1000
    logger.info("Integration cycle completed in %.1f ms", result.cycle_time_ms)
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

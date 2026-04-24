from __future__ import annotations

import importlib
import json
import urllib.error
import urllib.request

from idpo.agents.base import AgentContext
from idpo.core.config import PipelineConfig
from idpo.core.types import DAEOutput
from idpo.pipeline.executor import ExecutionState


def log_ahmn_feedback(
    *,
    ctx: AgentContext,
    config: PipelineConfig,
    advice_id: str | None,
    selected_policy_id: str,
    reward_value: float,
    reward_details: dict[str, object],
    latency_ms: float,
    state: ExecutionState,
    dae_output: DAEOutput,
    spent_budget_units: float,
) -> tuple[bool, str | None]:
    if not config.ahmn.enabled:
        return False, None
    if not advice_id:
        return False, "missing_advice_id"
    endpoint = (config.ahmn.endpoint or "").strip()
    if not endpoint:
        return False, "ahmn_endpoint_missing"

    metrics: dict[str, object] = {
        "f1_score": float((reward_details or {}).get("f1", reward_value) or reward_value),
        "cost": round(float(spent_budget_units or 0.0), 4),
        "processing_time_ms": round(float(latency_ms or 0.0), 2),
        "success": len(state.validation_issues) == 0,
        "schema_valid": bool((reward_details or {}).get("schema_valid", False)),
        "missing_required_count": int((reward_details or {}).get("missing_required_count", 0) or 0),
        "hallucinated_field_count": int((reward_details or {}).get("hallucinated_field_count", 0) or 0),
        "grounding_coverage": round(float((reward_details or {}).get("grounding_coverage", 0.0) or 0.0), 4),
        "defer_status": str((reward_details or {}).get("defer_status", "not_needed")),
        "direct_scored": "f1" in (reward_details or {}),
    }
    if "precision" in reward_details:
        metrics["precision"] = float(reward_details.get("precision", 0.0) or 0.0)
    if "recall" in reward_details:
        metrics["recall"] = float(reward_details.get("recall", 0.0) or 0.0)

    payload = {
        "advice_id": advice_id,
        "policy_id_used": selected_policy_id,
        "metrics": metrics,
        "document_context": {
            "doc_type": dae_output.doc_type,
            "vendor": dae_output.vendor_cluster,
            "vendor_cluster": dae_output.vendor_cluster,
            "content_profile": dae_output.content_profile,
            "route_bin": dae_output.route_bin,
            "layout_cluster_id": dae_output.layout_cluster_id,
            "quality_bin": dae_output.quality_bin,
            "complexity_bin": dae_output.complexity_bin,
            "quality_features": dae_output.quality_features,
            "structural_features": dae_output.structural_features,
        },
    }
    # Try HTTP endpoint first (live AHMN server).
    if endpoint:
        log_url = endpoint.rstrip("/") + config.ahmn.log_endpoint
        request = urllib.request.Request(
            log_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        timeout = max(config.ahmn.timeout_ms, 10) / 1000.0
        http_error: str | None = None
        try:
            with urllib.request.urlopen(request, timeout=timeout):
                _record_feedback_event(
                    ctx=ctx,
                    advice_id=advice_id,
                    selected_policy_id=selected_policy_id,
                    metrics=metrics,
                    log_endpoint=config.ahmn.log_endpoint,
                    logged=True,
                    error=None,
                )
                return True, None
        except urllib.error.HTTPError as exc:
            http_error = f"http_{exc.code}"
        except urllib.error.URLError:
            http_error = "unreachable"
        except TimeoutError:
            http_error = "timeout"
        except Exception:
            http_error = "unknown_error"

        # Fall through to direct_import if HTTP failed.
        if not config.ahmn.direct_import:
            _record_feedback_event(
                ctx=ctx,
                advice_id=advice_id,
                selected_policy_id=selected_policy_id,
                metrics=metrics,
                log_endpoint=config.ahmn.log_endpoint,
                logged=False,
                error=http_error,
            )
            return False, http_error

    # Direct-import path: call log_outcome on the imported module.
    # This is the only feedback path that actually reaches the in-process advisor
    # when no HTTP server is running (local benchmarks).
    direct_import = (config.ahmn.direct_import or "").strip()
    if direct_import:
        try:
            module_path, func_name = direct_import.rsplit(":", 1)
            module = importlib.import_module(module_path)
            log_fn = getattr(module, "log_outcome", None)
            if callable(log_fn):
                f1 = float((reward_details or {}).get("f1", reward_value) or reward_value)
                log_fn(advice_id, selected_policy_id, f1)
                _record_feedback_event(
                    ctx=ctx,
                    advice_id=advice_id,
                    selected_policy_id=selected_policy_id,
                    metrics=metrics,
                    log_endpoint="direct_import",
                    logged=True,
                    error=None,
                )
                return True, None
        except Exception as exc:
            error = f"direct_import_error:{exc}"
            _record_feedback_event(
                ctx=ctx,
                advice_id=advice_id,
                selected_policy_id=selected_policy_id,
                metrics=metrics,
                log_endpoint="direct_import",
                logged=False,
                error=error,
            )
            return False, error

    _record_feedback_event(
        ctx=ctx,
        advice_id=advice_id,
        selected_policy_id=selected_policy_id,
        metrics=metrics,
        log_endpoint=config.ahmn.log_endpoint,
        logged=False,
        error="no_feedback_channel",
    )
    return False, "no_feedback_channel"


def _record_feedback_event(
    *,
    ctx: AgentContext,
    advice_id: str,
    selected_policy_id: str,
    metrics: dict[str, object],
    log_endpoint: str,
    logged: bool,
    error: str | None,
) -> None:
    outputs: dict[str, object] = {"logged": logged}
    if error:
        outputs["error"] = error
    ctx.provenance.record(
        agent="ahmn_feedback",
        version="v1",
        inputs={"advice_id": advice_id, "policy_id_used": selected_policy_id},
        outputs=outputs,
        parameters={"log_endpoint": log_endpoint, "metrics": metrics},
        artifacts=[],
        event_type="AHMNFeedback",
    )

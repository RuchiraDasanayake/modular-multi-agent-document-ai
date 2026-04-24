"""
Lightweight in-process AHMN advisor for local runtime and benchmark runs.

Provides Thompson Sampling with a small amount of job-scoped persistence so the
canonical runtime can accumulate learning across documents processed in the same
job or, when no job exists, the same run.
"""

from __future__ import annotations

import json
import os
import random
import threading
import uuid
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_POLICY_STORE_PATH = _REPO_ROOT / "configs" / "policy_store_research.json"
_DEFAULT_DATA_ROOT = _REPO_ROOT.parent / "idpo-data"
_STATE_SUBDIR = ("ahmn", "direct_advisor")

_state_lock = threading.Lock()
_posteriors: dict[str, list[float]] = {}
_call_count = 0
_rng = random.Random()
_active_scope_key = "global"
_advice_scopes: dict[str, str] = {}

_RECEIPT_POLICY_PRIORITY = [
    "default",
    "receipt_fast_local",
    "receipt_rescue_local",
    "noisy_ocr_rescue",
    "noisy_ocr_precision_local",
    "scanned_text",
    "unknown_vendor_safe",
]

# Specialist policies (vendor_cluster-specific) get a stronger initial prior so
# they win early TS draws when they appear as candidates.
_SPECIALIST_POLICY_PRIORITY = [
    "receipt_specialist",
    "correspondence_specialist",
]


def _runtime_data_root() -> Path:
    raw = os.getenv("IDPO_DATA_DIR", "").strip()
    if not raw:
        return _DEFAULT_DATA_ROOT.resolve()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _state_dir() -> Path:
    path = _runtime_data_root()
    for part in _STATE_SUBDIR:
        path = path / part
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sanitize_scope_token(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value.strip())
    return cleaned[:120] or "global"


def resolve_scope_key(*, job_id: str | None = None, run_id: str | None = None) -> str:
    if job_id and str(job_id).strip():
        return f"job_{_sanitize_scope_token(str(job_id))}"
    if run_id and str(run_id).strip():
        return f"run_{_sanitize_scope_token(str(run_id))}"
    return "global"


def _scope_from_payload(payload: dict[str, Any]) -> str:
    extra = payload.get("extra_context")
    metadata = extra.get("metadata") if isinstance(extra, dict) else None
    if not isinstance(metadata, dict):
        metadata = {}
    return resolve_scope_key(
        job_id=str(metadata.get("job_id", "")).strip() or None,
        run_id=str(metadata.get("run_id", "")).strip() or None,
    )


def _state_file(scope_key: str) -> Path:
    return _state_dir() / f"{_sanitize_scope_token(scope_key)}.json"


def _load_policies() -> list[dict[str, Any]]:
    try:
        store = json.loads(_POLICY_STORE_PATH.read_text(encoding="utf-8"))
        return [p for p in store.get("policies", []) if isinstance(p, dict) and "policy_id" in p]
    except Exception:
        return [{"policy_id": "default", "conditions": {}}]


def _value_map_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    extra = payload.get("extra_context")
    extra_context = extra if isinstance(extra, dict) else {}
    values: dict[str, Any] = {
        "doc_type": payload.get("doc_type"),
        "vendor_cluster": extra_context.get("vendor_cluster") or payload.get("vendor"),
        "layout_cluster_id": extra_context.get("layout_cluster_id"),
        "quality_bin": extra_context.get("quality_bin"),
        "complexity_bin": extra_context.get("complexity_bin"),
        "content_profile": payload.get("content_profile"),
        "route_bin": extra_context.get("route_bin"),
        "quality_score": extra_context.get("quality_score"),
        "complexity_score": extra_context.get("complexity_score"),
    }
    for prefix in ("quality_features", "structural_features", "signals"):
        nested = extra_context.get(prefix)
        if isinstance(nested, dict):
            for key, value in nested.items():
                values[f"{prefix}.{key}"] = value
    metadata = extra_context.get("metadata")
    if isinstance(metadata, dict):
        values.update(metadata)
    return values


def _matches_expectation(current: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return current in expected
    if isinstance(expected, dict):
        if current is None:
            return False
        if "min" in expected and current < expected["min"]:
            return False
        if "max" in expected and current > expected["max"]:
            return False
        if "equals" in expected:
            return current == expected["equals"]
        return True
    return current == expected


def _matches_conditions(conditions: dict[str, Any], values: dict[str, Any]) -> bool:
    if not conditions:
        return False
    for key, expected in conditions.items():
        if not _matches_expectation(values.get(key), expected):
            return False
    return True


def _candidate_policy_ids(payload: dict[str, Any]) -> list[str]:
    policies = _load_policies()
    values = _value_map_from_payload(payload)
    default_policy_id = "default"
    candidate_ids = [
        str(item["policy_id"])
        for item in policies
        if _matches_conditions(item.get("conditions", {}), values)
    ]
    if default_policy_id not in candidate_ids:
        candidate_ids.append(default_policy_id)
    return list(dict.fromkeys(candidate_ids))


def _restore_state(scope_key: str) -> None:
    global _active_scope_key, _call_count, _posteriors

    path = _state_file(scope_key)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    else:
        payload = {}

    posteriors = payload.get("posteriors")
    _posteriors = {
        str(pid): [float(values[0]), float(values[1])]
        for pid, values in (posteriors.items() if isinstance(posteriors, dict) else [])
        if isinstance(values, list) and len(values) == 2
    }
    _call_count = int(payload.get("call_count", 0) or 0)
    _active_scope_key = scope_key


def _persist_active_state() -> None:
    payload = {
        "scope_key": _active_scope_key,
        "call_count": _call_count,
        "posteriors": _posteriors,
    }
    path = _state_file(_active_scope_key)
    temp_path = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def _ensure_initialized(policy_ids: list[str]) -> None:
    for pid in policy_ids:
        if pid not in _posteriors:
            if pid in _SPECIALIST_POLICY_PRIORITY:
                alpha = 3.0  # specialist policies strongly preferred when they match
            elif pid in _RECEIPT_POLICY_PRIORITY:
                alpha = 1.5
            else:
                alpha = 1.0
            _posteriors[pid] = [alpha, 1.0]


def _thompson_sample(policy_ids: list[str]) -> str:
    samples = {pid: _rng.betavariate(_posteriors[pid][0], _posteriors[pid][1]) for pid in policy_ids}
    return max(samples, key=lambda pid: samples[pid])


def get_advice(payload: dict[str, Any]) -> dict[str, Any]:
    """Entry point for direct_import mode in policy_advisor.py."""
    global _call_count

    policy_ids = _candidate_policy_ids(payload)
    advice_id = str(uuid.uuid4())
    scope_key = _scope_from_payload(payload)

    with _state_lock:
        if scope_key != _active_scope_key:
            _restore_state(scope_key)
        _ensure_initialized(policy_ids)
        selected = _thompson_sample(policy_ids)
        _call_count += 1
        alpha, beta = _posteriors[selected]
        _advice_scopes[advice_id] = scope_key
        _persist_active_state()

    confidence = round(alpha / (alpha + beta), 4)
    return {
        "policy_id": selected,
        "advice_id": advice_id,
        "confidence": confidence,
        "retrieval_source": "direct_ts",
        "rabi_used": False,
        "n_neighbors": None,
        "source": "ahmn_direct",
        "doc_count_seen": _call_count,
        "scope_key": scope_key,
    }


def log_outcome(advice_id: str, policy_id: str, reward: float) -> None:
    """Update the Beta posterior for a policy after observing a reward."""
    with _state_lock:
        scope_key = _advice_scopes.get(advice_id) or _active_scope_key
        if scope_key != _active_scope_key:
            _restore_state(scope_key)
        if policy_id not in _posteriors:
            _posteriors[policy_id] = [1.0, 1.0]
        alpha, beta = _posteriors[policy_id]
        success = reward >= 0.5
        if success:
            _posteriors[policy_id][0] = alpha + 1.0
        else:
            _posteriors[policy_id][1] = beta + 1.0
        _persist_active_state()


def get_state_snapshot(scope_key: str | None = None) -> dict[str, Any]:
    """Return current posterior state for debugging and run artifacts."""
    with _state_lock:
        effective_scope = scope_key or _active_scope_key
        if effective_scope == _active_scope_key:
            payload = {
                "scope_key": _active_scope_key,
                "call_count": _call_count,
                "posteriors": _posteriors,
            }
        else:
            path = _state_file(effective_scope)
            if path.exists():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    payload = {}
            else:
                payload = {}
        posteriors = payload.get("posteriors", {})
        return {
            "scope_key": str(payload.get("scope_key", effective_scope) or effective_scope),
            "call_count": int(payload.get("call_count", 0) or 0),
            "policies": {
                str(pid): {
                    "alpha": float(values[0]),
                    "beta": float(values[1]),
                    "mean": round(float(values[0]) / (float(values[0]) + float(values[1])), 4),
                }
                for pid, values in posteriors.items()
                if isinstance(values, list) and len(values) == 2
            },
            "state_path": str(_state_file(effective_scope)),
        }

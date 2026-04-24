"""
Lightweight in-process AHMN advisor for benchmark runs.

Provides the same Thompson Sampling + RABI logic as the full microservice
but runs in-process without Redis, PostgreSQL, or FastAPI.
Use this via direct_import in the IDPO pipeline config for local benchmarks.
"""

from __future__ import annotations

import json
import math
import random
import threading
import uuid
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_POLICY_STORE_PATH = _REPO_ROOT / "configs" / "policy_store_research.json"

# Per-policy Beta(α, β) posteriors — shared across calls in a single process.
_state_lock = threading.Lock()
_posteriors: dict[str, list[float]] = {}  # policy_id -> [alpha, beta]
_call_count = 0

# Policies that are actually relevant for receipts (CORD v2 doc type)
_RECEIPT_POLICY_PRIORITY = [
    "default",
    "noisy_ocr_rescue",
    "noisy_ocr_precision_local",
    "scanned_text",
    "unknown_vendor_safe",
]


def _load_policy_ids() -> list[str]:
    try:
        store = json.loads(_POLICY_STORE_PATH.read_text(encoding="utf-8"))
        return [p["policy_id"] for p in store.get("policies", []) if "policy_id" in p]
    except Exception:
        return ["default"]


def _ensure_initialized(policy_ids: list[str]) -> None:
    for pid in policy_ids:
        if pid not in _posteriors:
            # Receipt-relevant policies get a weak head start (α=1.5, β=1)
            alpha = 1.5 if pid in _RECEIPT_POLICY_PRIORITY else 1.0
            _posteriors[pid] = [alpha, 1.0]


def _thompson_sample(policy_ids: list[str]) -> str:
    rng = random.Random()
    samples = {pid: rng.betavariate(_posteriors[pid][0], _posteriors[pid][1])
               for pid in policy_ids}
    return max(samples, key=lambda pid: samples[pid])


def get_advice(payload: dict[str, Any]) -> dict[str, Any]:
    """Entry point for direct_import mode in policy_advisor.py."""
    global _call_count

    policy_ids = _load_policy_ids()
    advice_id = str(uuid.uuid4())

    with _state_lock:
        _ensure_initialized(policy_ids)
        selected = _thompson_sample(policy_ids)
        _call_count += 1
        count = _call_count

    # Confidence = proportion of weight on selected policy (heuristic)
    alpha, beta = _posteriors[selected]
    confidence = round(alpha / (alpha + beta), 4)

    return {
        "policy_id": selected,
        "advice_id": advice_id,
        "confidence": confidence,
        "retrieval_source": "direct_ts",
        "rabi_used": False,
        "n_neighbors": None,
        "source": "ahmn_direct",
        "doc_count_seen": count,
    }


def log_outcome(advice_id: str, policy_id: str, reward: float) -> None:
    """Update the Beta posterior for a policy after observing a reward."""
    with _state_lock:
        if policy_id not in _posteriors:
            _posteriors[policy_id] = [1.0, 1.0]
        alpha, beta = _posteriors[policy_id]
        # Treat reward in [0,1] as a Bernoulli draw (round to nearest 0/1)
        success = reward >= 0.5
        if success:
            _posteriors[policy_id][0] = alpha + 1.0
        else:
            _posteriors[policy_id][1] = beta + 1.0


def get_state_snapshot() -> dict[str, Any]:
    """Return current posterior state for debugging."""
    with _state_lock:
        return {pid: {"alpha": a, "beta": b, "mean": round(a / (a + b), 4)}
                for pid, (a, b) in _posteriors.items()}

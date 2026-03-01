from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from idpo.core.config import RollbackConfig


@dataclass(frozen=True)
class RollbackDecision:
    triggered: bool
    reason: str
    revert_to_policy_id: Optional[str]
    deltas: Dict[str, float]


class PolicySafetyMonitor:
    """Tracks policy quality over a rolling window and triggers safe rollback."""

    def __init__(self, run_dir: Path, config: RollbackConfig, baseline_policy_id: str) -> None:
        self.path = Path(run_dir) / "metrics" / "policy_safety.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.baseline_policy_id = baseline_policy_id
        self.history: Dict[str, List[Dict[str, float]]] = {}
        self.blocked: set[str] = set()
        self.last_known_good = baseline_policy_id
        self._lock = threading.Lock()
        self._load()

    def update(self, policy_id: str, metrics: Dict[str, float]) -> RollbackDecision:
        if not self.config.enabled:
            return RollbackDecision(False, "disabled", None, {})

        with self._lock:
            items = self.history.setdefault(policy_id, [])
            items.append(metrics)
            window = max(self.config.window_size, 5)
            if len(items) > window:
                self.history[policy_id] = items[-window:]

            decision = self._evaluate(policy_id)
            if decision.triggered and decision.revert_to_policy_id:
                self.blocked.add(policy_id)
            elif policy_id not in self.blocked:
                self.last_known_good = policy_id
            self._save()
            return decision

    def is_blocked(self, policy_id: str) -> bool:
        return policy_id in self.blocked

    def _evaluate(self, policy_id: str) -> RollbackDecision:
        if policy_id == self.baseline_policy_id:
            return RollbackDecision(False, "baseline", None, {})
        current = self.history.get(policy_id, [])
        baseline = self.history.get(self.baseline_policy_id, [])
        minimum = min(5, max(self.config.window_size // 3, 3))
        if len(current) < minimum or len(baseline) < minimum:
            return RollbackDecision(False, "insufficient_history", None, {})

        current_p95 = _percentile([row.get("latency_ms", 0.0) for row in current], 95)
        baseline_p95 = _percentile([row.get("latency_ms", 0.0) for row in baseline], 95)
        current_pass = 1.0 - _mean([row.get("validation_failure", 0.0) for row in current])
        baseline_pass = 1.0 - _mean([row.get("validation_failure", 0.0) for row in baseline])
        current_quality = _mean([row.get("quality_proxy", 0.0) for row in current])
        baseline_quality = _mean([row.get("quality_proxy", 0.0) for row in baseline])

        latency_regression = (
            (current_p95 - baseline_p95) / baseline_p95 if baseline_p95 > 0 else 0.0
        )
        pass_drop = baseline_pass - current_pass
        quality_drop = baseline_quality - current_quality
        deltas = {
            "latency_p95_ms": current_p95,
            "baseline_latency_p95_ms": baseline_p95,
            "latency_regression_pct": latency_regression,
            "validation_pass_drop": pass_drop,
            "quality_drop": quality_drop,
        }

        if current_p95 > self.config.latency_p95_ms:
            return RollbackDecision(True, "latency_p95_limit", self.baseline_policy_id, deltas)
        if latency_regression > self.config.max_latency_regression_pct:
            return RollbackDecision(True, "latency_regression", self.baseline_policy_id, deltas)
        if pass_drop > self.config.min_validation_pass_delta:
            return RollbackDecision(True, "validation_pass_drop", self.baseline_policy_id, deltas)
        if quality_drop > self.config.quality_drop_threshold:
            return RollbackDecision(True, "quality_drop", self.baseline_policy_id, deltas)

        return RollbackDecision(False, "healthy", None, deltas)

    def _load(self) -> None:
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.history = {key: list(values) for key, values in payload.get("history", {}).items()}
        self.blocked = set(payload.get("blocked", []))
        self.last_known_good = payload.get("last_known_good", self.baseline_policy_id)

    def _save(self) -> None:
        payload = {
            "history": self.history,
            "blocked": sorted(self.blocked),
            "last_known_good": self.last_known_good,
            "baseline_policy_id": self.baseline_policy_id,
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _percentile(values: List[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((percentile / 100.0) * (len(ordered) - 1)))
    idx = max(0, min(idx, len(ordered) - 1))
    return ordered[idx]

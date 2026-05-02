from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from idpo.core.config import PipelineConfig, RollbackConfig


class PolicyRollbackMonitor:
    def __init__(self, run_dir: Path, config: PipelineConfig) -> None:
        self.config = config
        self.path = Path(run_dir) / "policy_rollbacks.json"
        self.history: dict[str, list[dict[str, float]]] = {}
        self.blocked: set[str] = set()
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.history = {key: list(values) for key, values in payload.get("history", {}).items()}
        self.blocked = set(payload.get("blocked", []))

    def record(self) -> None:
        payload = {"history": self.history, "blocked": sorted(self.blocked)}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def is_blocked(self, policy_id: str) -> bool:
        return policy_id in self.blocked

    def update(self, policy_id: str, metrics: dict[str, float], baseline_policy_id: str) -> dict[str, object]:
        if not self.config.rollback.enabled:
            return {
                "blocked": False,
                "triggered": False,
                "reason": "disabled",
                "blocked_count": len(self.blocked),
            }
        with self._lock:
            items = self.history.setdefault(policy_id, [])
            items.append(metrics)
            window = self.config.rollback.window_size
            if len(items) > window:
                self.history[policy_id] = items[-window:]
            reason = self._block_reason(policy_id, baseline_policy_id)
            should_block = reason is not None
            if should_block:
                self.blocked.add(policy_id)
            self.record()
            return {
                "blocked": policy_id in self.blocked,
                "triggered": should_block,
                "reason": reason,
                "blocked_count": len(self.blocked),
            }

    def _block_reason(self, policy_id: str, baseline_policy_id: str) -> str | None:
        if policy_id == baseline_policy_id:
            return None
        items = self.history.get(policy_id, [])
        if len(items) < min(5, self.config.rollback.window_size):
            return None
        latencies = [item.get("latency_ms", 0.0) for item in items]
        failures = [item.get("validation_failure", 0.0) for item in items]
        qualities = [item.get("quality_proxy", 0.0) for item in items]

        latency_p95 = _percentile(latencies, 95)
        failure_rate = sum(1.0 for flag in failures if flag) / len(failures)
        candidate_quality = sum(qualities) / len(qualities) if qualities else 0.0

        baseline_items = self.history.get(baseline_policy_id, [])
        baseline_quality = None
        if baseline_items:
            base_qualities = [item.get("quality_proxy", 0.0) for item in baseline_items]
            baseline_quality = sum(base_qualities) / len(base_qualities)

        if latency_p95 > self.config.rollback.latency_p95_ms:
            return "latency_p95_limit"
        if failure_rate > self.config.rollback.validation_failure_rate:
            return "validation_failure_rate"
        if baseline_quality is not None and (baseline_quality - candidate_quality) > self.config.rollback.quality_drop_threshold:
            return "quality_drop"
        return None


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(round((percentile / 100) * (len(sorted_vals) - 1)))
    idx = max(0, min(idx, len(sorted_vals) - 1))
    return sorted_vals[idx]


@dataclass(frozen=True)
class RollbackDecision:
    triggered: bool
    reason: str
    revert_to_policy_id: Optional[str]
    deltas: Dict[str, float]


class PolicySafetyMonitor:
    """Compatibility wrapper around the canonical rollback monitor."""

    def __init__(self, run_dir: Path, config: RollbackConfig, baseline_policy_id: str) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        pipeline_config = PipelineConfig()
        pipeline_config.rollback = config
        pipeline_config.knowledge.default_policy_id = baseline_policy_id
        self.baseline_policy_id = baseline_policy_id
        self._monitor = PolicyRollbackMonitor(run_dir, pipeline_config)

    def update(self, policy_id: str, metrics: Dict[str, float]) -> RollbackDecision:
        result = self._monitor.update(policy_id, metrics, baseline_policy_id=self.baseline_policy_id)
        reason = str(result.get("reason") or "")
        return RollbackDecision(
            triggered=bool(result.get("triggered", False)),
            reason=reason,
            revert_to_policy_id=self.baseline_policy_id if reason and reason != "disabled" else None,
            deltas=dict(metrics),
        )

    def is_blocked(self, policy_id: str) -> bool:
        return self._monitor.is_blocked(policy_id)

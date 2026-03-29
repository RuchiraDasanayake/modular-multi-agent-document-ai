from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from idpo.core.config import PipelineConfig, RollbackConfig
from idpo.pipeline.orchestrator import PolicyRollbackMonitor


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

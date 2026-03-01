from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List

from idpo.core.artifacts import ArtifactStore
from idpo.core.config import PipelineConfig
from idpo.core.provenance import ProvenanceRecorder
from idpo.core.contracts import AgentContract, AgentMessage
from idpo.core.types import AgentResult


@dataclass
class AgentContext:
    config: PipelineConfig
    artifact_store: ArtifactStore
    provenance: ProvenanceRecorder
    run_id: str
    budget_manager: Any | None = None
    calibrator: Any | None = None


class Agent:
    name: str = "agent"
    version: str = "v0"
    input_contract: Dict[str, Any] = {}
    output_contract: Dict[str, Any] = {}

    def contract(self) -> AgentContract:
        return AgentContract(
            name=self.name,
            version=self.version,
            inputs=self.input_contract,
            outputs=self.output_contract,
        )

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        raise NotImplementedError

    def _record(
        self,
        ctx: AgentContext,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        parameters: Dict[str, Any],
        artifacts: list[str] | None = None,
        input_artifacts: list[str] | None = None,
        output_artifacts: list[str] | None = None,
        cost_units: float = 0.0,
        started: float | None = None,
        event_type: str = "OperatorExecution",
    ) -> None:
        latency_ms = (time.time() - started) * 1000 if started else 0.0
        ctx.provenance.record(
            agent=self.name,
            version=self.version,
            inputs={**inputs, "contract": self.input_contract, "input_artifacts": input_artifacts or []},
            outputs={**outputs, "contract": self.output_contract, "output_artifacts": output_artifacts or []},
            parameters=parameters,
            artifacts=artifacts or [],
            latency_ms=latency_ms,
            cost_units=cost_units,
            event_type=event_type,
        )

"""Stage-wise pipeline executor for processing agent chains."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from idpo.agents.answering import AnsweringAgent
from idpo.agents.base import AgentContext
from idpo.agents.chunking import ChunkingAgent
from idpo.agents.escalation import EscalationAgent
from idpo.agents.preprocess import DeskewAgent, DenoiseAgent, OcrAgent, TableFormAgent
from idpo.agents.recovery import RecoveryAgent
from idpo.agents.structuring import SectioningAgent, SummarizationAgent
from idpo.agents.llm_extraction import LLMExtractionAgent
from idpo.agents.validation import ValidationAgent
from idpo.core.types import (
    AgentResult,
    Chunk,
    Document,
    Entity,
    ExecutionPlan,
    ModelDecision,
    Section,
    StageSignal,
    ValidationIssue,
)

@dataclass
class ExecutionState:
    document: Document
    entities: list[Entity] = field(default_factory=list)
    explicit_entities: list[Entity] = field(default_factory=list)
    default_entities: list[Entity] = field(default_factory=list)
    explicit_source: str = ""
    requested_field_status: dict[str, dict[str, object]] = field(default_factory=dict)
    llm_diagnostics: dict[str, object] = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)
    summary: str = ""
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    normalized_entities: dict[str, str] = field(default_factory=dict)
    field_confidence: dict[str, float] = field(default_factory=dict)
    recovered_fields: dict[str, str] = field(default_factory=dict)
    recovery_trace: list[dict[str, object]] = field(default_factory=list)
    failed_recovery_fields: list[str] = field(default_factory=list)
    escalated: bool = False
    escalation_status: str = "not_needed"
    escalation_info: dict[str, object] = field(default_factory=dict)
    chunks: list[Chunk] = field(default_factory=list)
    chunk_artifact_id: str = ""
    preprocess_route: list[str] = field(default_factory=list)
    preprocess_artifacts: list[str] = field(default_factory=list)
    stage_signals: list[StageSignal] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    last_artifact_id: str | None = None

class BudgetTracker:
    def __init__(self, max_cost_units: float) -> None:
        self.max_cost_units = max_cost_units
        self.spent = 0.0

    def can_spend(self, units: float) -> bool:
        return (self.spent + units) <= self.max_cost_units

    def spend(self, units: float) -> None:
        self.spent += units

class PlanExecutor:
    def __init__(self) -> None:
        self.ocr = OcrAgent()
        self.deskew = DeskewAgent()
        self.denoise = DenoiseAgent()
        self.table_extract = TableFormAgent()
        self.extractor = LLMExtractionAgent()
        self.sectioning = SectioningAgent()
        self.summarizer = SummarizationAgent()
        self.validator = ValidationAgent()
        self.recovery = RecoveryAgent()
        self.escalation = EscalationAgent()
        self.chunker = ChunkingAgent()
        self.answering = AnsweringAgent()

    def execute(self, plan: ExecutionPlan, doc: Document, ctx: AgentContext, escalation_count: int = 0) -> ExecutionState:
        state = ExecutionState(document=doc)
        budget = BudgetTracker(plan.budgets.get("max_cost_units", ctx.config.plan.max_total_budget_units))

        for step in plan.steps:
            if not budget.can_spend(step.budget_units):
                ctx.provenance.record(
                    agent="plan_executor",
                    version="v1",
                    inputs={"doc_id": doc.doc_id, "step": step.operator},
                    outputs={"skipped": True, "reason": "budget_exceeded"},
                    parameters={"budget_units": step.budget_units, "remaining": budget.max_cost_units - budget.spent},
                    artifacts=[],
                    event_type="OperatorExecution",
                )
                continue

            operator = step.operator
            executed = True
            if operator.startswith("preprocess."):
                self._run_preprocess(step, state, ctx)
            elif operator == "structuring.extract":
                self._run_extraction(step, state, ctx)
            elif operator == "structuring.section":
                self._run_sectioning(step, state, ctx)
            elif operator == "structuring.summary":
                self._run_summary(step, state, ctx)
            elif operator == "validation":
                self._run_validation(step, state, ctx, stage="initial")
            elif operator == "recovery":
                if state.validation_issues:
                    self._run_recovery(step, state, ctx)
                else:
                    executed = False
                    state.recovery_trace = []
                    state.failed_recovery_fields = []
                    ctx.provenance.record(
                        agent="recovery",
                        version="v1",
                        inputs={"doc_id": doc.doc_id, "issue_count": 0},
                        outputs={"skipped": True, "reason": "no_validation_issues"},
                        parameters={"strategy": step.params.get("strategy") if step.params else None},
                        artifacts=[],
                        event_type="RecoveryAction",
                    )
            elif operator == "escalation":
                if state.validation_issues:
                    remaining = budget.max_cost_units - budget.spent
                    self._run_escalation(step, state, ctx, budget_remaining=remaining, count=escalation_count)
                else:
                    executed = False
                    state.escalation_status = "not_needed"
                    state.escalation_info = {
                        "status": "not_needed",
                        "reason": "no_validation_issues",
                        "fields": [],
                        "estimated_cost_units": 0.0,
                        "estimated_latency_ms": 0.0,
                        "unresolved_field_count": 0,
                    }
                    ctx.provenance.record(
                        agent="escalation",
                        version="v1",
                        inputs={"doc_id": doc.doc_id, "issue_count": 0},
                        outputs={"skipped": True, "reason": "no_validation_issues"},
                        parameters={"tier": step.params.get("tier") if step.params else None},
                        artifacts=[],
                        event_type="EscalationAction",
                    )
            elif operator == "chunking":
                self._run_chunking(step, state, ctx)
            else:
                executed = False

            if executed:
                budget.spend(step.budget_units)

        return state

    def _run_preprocess(self, step, state: ExecutionState, ctx: AgentContext) -> None:
        payload = {
            "document": state.document,
            "input_artifact_id": state.last_artifact_id,
            "quality_bin": getattr(state.document, "quality_bin", ""),
            "content_profile": getattr(state.document, "content_profile", ""),
            **step.params,
        }
        if step.operator == "preprocess.ocr":
            result = self.ocr.run(payload, ctx)
            state.preprocess_route.append("ocr")
        elif step.operator == "preprocess.deskew":
            result = self.deskew.run(payload, ctx)
            state.preprocess_route.append("deskew")
        elif step.operator == "preprocess.denoise":
            result = self.denoise.run(payload, ctx)
            state.preprocess_route.append("denoise")
        else:
            result = self.table_extract.run(payload, ctx)
            state.preprocess_route.append("table_extract")

        state.document = result.artifacts.get("document", state.document)
        artifact_id = result.artifacts.get("artifact_id")
        if artifact_id:
            state.preprocess_artifacts.append(artifact_id)
            state.last_artifact_id = artifact_id
        signal = result.artifacts.get("signal")
        if signal:
            state.stage_signals.append(signal)

    def _run_extraction(self, step, state: ExecutionState, ctx: AgentContext) -> None:
        model = self._model_from_params(step.params, ctx)
        explicit_entities = step.params.get("explicit_entities") if step.params else None
        field_descriptions = step.params.get("field_descriptions") if step.params else None
        result = self.extractor.run(
            {
                "document": state.document,
                "model": model,
                "input_artifact_id": state.last_artifact_id,
                "explicit_entities": explicit_entities,
                "field_descriptions": field_descriptions,
            },
            ctx,
        )
        state.entities = result.artifacts.get("entities", [])
        state.explicit_entities = result.artifacts.get("explicit_entities", [])
        state.default_entities = result.artifacts.get("default_entities", [])
        state.explicit_source = result.artifacts.get("explicit_source", "")
        state.requested_field_status = result.artifacts.get("requested_field_status", {})
        state.llm_diagnostics = result.artifacts.get("llm_diagnostics", {})
        signal = result.artifacts.get("signal")
        if signal:
            state.stage_signals.append(signal)

    def _run_sectioning(self, step, state: ExecutionState, ctx: AgentContext) -> None:
        result = self.sectioning.run({"document": state.document}, ctx)
        state.sections = result.artifacts.get("sections", [])
        signal = result.artifacts.get("signal")
        if signal:
            state.stage_signals.append(signal)

    def _run_summary(self, step, state: ExecutionState, ctx: AgentContext) -> None:
        result = self.summarizer.run({"document": state.document}, ctx)
        state.summary = result.artifacts.get("summary", "")
        signal = result.artifacts.get("signal")
        if signal:
            state.stage_signals.append(signal)

    def _run_validation(self, step, state: ExecutionState, ctx: AgentContext, stage: str) -> None:
        result = self.validator.run(
            {"document": state.document, "entities": state.entities, "stage": stage},
            ctx,
        )
        state.validation_issues = result.artifacts.get("validation_issues", [])
        state.normalized_entities = result.artifacts.get("normalized_entities", {})
        state.field_confidence = result.artifacts.get("field_confidence", {})
        signal = result.artifacts.get("signal")
        if signal:
            state.stage_signals.append(signal)

    def _run_recovery(self, step, state: ExecutionState, ctx: AgentContext) -> None:
        result = self.recovery.run(
            {
                "document": state.document,
                "entities": state.entities,
                "issues": state.validation_issues,
                "strategy": step.params.get("strategy") if step.params else None,
            },
            ctx,
        )
        state.entities = result.artifacts.get("entities", state.entities)
        state.recovered_fields = result.artifacts.get("recovered_fields", {})
        state.recovery_trace = result.artifacts.get("recovery_trace", [])
        state.failed_recovery_fields = [
            str(item.get("field", ""))
            for item in state.recovery_trace
            if not bool(item.get("success", False))
        ]
        signal = result.artifacts.get("signal")
        if signal:
            state.stage_signals.append(signal)
        if state.recovered_fields:
            self._run_validation(step, state, ctx, stage="post_recovery")

    def _run_escalation(
        self, step, state: ExecutionState, ctx: AgentContext, budget_remaining: float, count: int
    ) -> None:
        result = self.escalation.run(
            {
                "document": state.document,
                "issues": state.validation_issues,
                "signal": None,
                "count": count,
                "budget_remaining": budget_remaining,
                "fields": [issue.field for issue in state.validation_issues],
            },
            ctx,
        )
        state.escalated = bool(result.artifacts.get("escalated", False))
        state.escalation_status = str(result.artifacts.get("escalation_status", "not_needed") or "not_needed")
        state.escalation_info = {
            "status": state.escalation_status,
            "reason": result.artifacts.get("escalation_reason", ""),
            "fields": result.artifacts.get("fields", []),
            "target_model": result.artifacts.get("target_model", ""),
            "estimated_cost_units": float(result.artifacts.get("estimated_cost_units", 0.0) or 0.0),
            "estimated_latency_ms": float(result.artifacts.get("estimated_latency_ms", 0.0) or 0.0),
            "unresolved_field_count": len({issue.field for issue in state.validation_issues}),
        }
        signal = result.artifacts.get("signal")
        if signal:
            state.stage_signals.append(signal)

    def _run_chunking(self, step, state: ExecutionState, ctx: AgentContext) -> None:
        payload = {
            "document": state.document,
            "sections": state.sections,
            "input_artifact_id": state.last_artifact_id,
            **step.params,
        }
        result = self.chunker.run(payload, ctx)
        state.chunks = result.artifacts.get("chunks", [])
        chunk_artifact = result.artifacts.get("chunks_artifact")
        if chunk_artifact:
            state.chunk_artifact_id = chunk_artifact.artifact_id
        signal = result.artifacts.get("signal")
        if signal:
            state.stage_signals.append(signal)

    def _model_from_params(self, params: dict[str, object], ctx: AgentContext) -> ModelDecision:
        model_tier = str(params.get("model_tier", ctx.config.llm.default_mode))
        mode = "cloud" if model_tier in {"cloud", "tier2"} else "local"
        model_name = ctx.config.llm.cloud_model if mode == "cloud" else ctx.config.llm.local_model
        return ModelDecision(mode=mode, model_name=model_name, reason="plan", metadata={"model_tier": model_tier})

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from idpo.agents.answering import AnsweringAgent
from idpo.agents.base import AgentContext
from idpo.agents.chunking import ChunkingAgent
from idpo.agents.escalation import EscalationAgent
from idpo.agents.llm_extraction import LLMExtractionAgent
from idpo.agents.preprocess import DeskewAgent, DenoiseAgent, OcrAgent, TableFormAgent
from idpo.agents.recovery import RecoveryAgent
from idpo.agents.structuring import SectioningAgent, SummarizationAgent
from idpo.agents.validation import ValidationAgent
from idpo.core.types import (
    Chunk,
    Document,
    Entity,
    ExecutionPlan,
    FieldExtraction,
    ModelDecision,
    Section,
    StageSignal,
    ValidationIssue,
)


@dataclass
class ExecutionState:
    document: Document
    entities: List[Entity] = field(default_factory=list)
    fields: List[FieldExtraction] = field(default_factory=list)
    explicit_entities: List[Entity] = field(default_factory=list)
    default_entities: List[Entity] = field(default_factory=list)
    explicit_source: str = ""
    sections: List[Section] = field(default_factory=list)
    summary: str = ""
    validation_issues: List[ValidationIssue] = field(default_factory=list)
    normalized_entities: Dict[str, str] = field(default_factory=dict)
    field_confidence: Dict[str, float] = field(default_factory=dict)
    field_details: Dict[str, Dict[str, object]] = field(default_factory=dict)
    recovered_fields: Dict[str, str] = field(default_factory=dict)
    failed_recovery_fields: List[str] = field(default_factory=list)
    recovery_log: List[Dict[str, object]] = field(default_factory=list)
    escalated: bool = False
    escalation_info: Dict[str, object] = field(default_factory=dict)
    chunks: List[Chunk] = field(default_factory=list)
    chunk_artifact_id: str = ""
    preprocess_route: List[str] = field(default_factory=list)
    preprocess_artifacts: List[str] = field(default_factory=list)
    stage_signals: List[StageSignal] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)
    last_artifact_id: Optional[str] = None


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
        started = time.time()
        if ctx.budget_manager:
            ctx.budget_manager.start_document(doc.doc_id)

        for step in plan.steps:
            elapsed_ms = (time.time() - started) * 1000
            if not budget.can_spend(step.budget_units):
                self._skip_step(
                    ctx,
                    doc.doc_id,
                    step.operator,
                    "plan_budget_exceeded",
                    step.budget_units,
                    budget.max_cost_units - budget.spent,
                )
                continue
            if ctx.budget_manager:
                decision = ctx.budget_manager.allow_spend(
                    doc_id=doc.doc_id,
                    cost_units=step.budget_units,
                    elapsed_ms=elapsed_ms,
                    operation=step.operator,
                )
                if not decision.allowed:
                    self._skip_step(
                        ctx,
                        doc.doc_id,
                        step.operator,
                        decision.reason,
                        step.budget_units,
                        decision.remaining_doc_cost,
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
                failing_fields = self._failing_fields(state)
                if failing_fields:
                    self._run_recovery(step, state, ctx, failing_fields=failing_fields)
                else:
                    executed = False
            elif operator == "escalation":
                failing_fields = self._failing_fields(state)
                if failing_fields:
                    remaining = budget.max_cost_units - budget.spent
                    self._run_escalation(
                        step,
                        state,
                        ctx,
                        budget_remaining=remaining,
                        count=escalation_count,
                        failing_fields=failing_fields,
                    )
                else:
                    executed = False
            elif operator == "chunking":
                self._run_chunking(step, state, ctx)
            else:
                executed = False

            if executed:
                budget.spend(step.budget_units)
                if ctx.budget_manager:
                    ctx.budget_manager.spend(doc.doc_id, step.budget_units)

        return state

    def _skip_step(
        self,
        ctx: AgentContext,
        doc_id: str,
        operator: str,
        reason: str,
        requested_budget: float,
        remaining: float,
    ) -> None:
        ctx.provenance.record(
            agent="plan_executor",
            version="v2",
            inputs={"doc_id": doc_id, "step": operator},
            outputs={"skipped": True, "reason": reason},
            parameters={"budget_units": requested_budget, "remaining": remaining},
            artifacts=[],
            event_type="OperatorExecution",
        )

    def _run_preprocess(self, step, state: ExecutionState, ctx: AgentContext) -> None:
        payload = {"document": state.document, "input_artifact_id": state.last_artifact_id, **step.params}
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
        field_templates = step.params.get("field_templates") if step.params else None
        result = self.extractor.run(
            {
                "document": state.document,
                "model": model,
                "input_artifact_id": state.last_artifact_id,
                "explicit_entities": explicit_entities,
                "field_descriptions": field_descriptions,
                "field_templates": field_templates,
            },
            ctx,
        )
        state.entities = result.artifacts.get("entities", [])
        state.fields = result.artifacts.get("fields", [])
        state.explicit_entities = result.artifacts.get("explicit_entities", [])
        state.default_entities = result.artifacts.get("default_entities", [])
        state.explicit_source = result.artifacts.get("explicit_source", "")
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
            {
                "document": state.document,
                "entities": state.entities,
                "stage": stage,
                "min_confidence": step.params.get("min_confidence") if step.params else None,
            },
            ctx,
        )
        state.validation_issues = result.artifacts.get("validation_issues", [])
        state.normalized_entities = result.artifacts.get("normalized_entities", {})
        state.field_confidence = result.artifacts.get("field_confidence", {})
        state.field_details = result.artifacts.get("field_details", {})
        signal = result.artifacts.get("signal")
        if signal:
            state.stage_signals.append(signal)

    def _run_recovery(self, step, state: ExecutionState, ctx: AgentContext, failing_fields: List[str]) -> None:
        allowed_fields = []
        for field in failing_fields:
            if not ctx.budget_manager:
                allowed_fields.append(field)
                continue
            decision = ctx.budget_manager.allow_retry(state.document.doc_id, field)
            if decision.allowed:
                allowed_fields.append(field)
                ctx.budget_manager.record_retry(state.document.doc_id, field)
            else:
                ctx.provenance.record(
                    agent="budget_manager",
                    version="v1",
                    inputs={"doc_id": state.document.doc_id, "field": field},
                    outputs={"allowed": False, "reason": decision.reason},
                    parameters={"action": "retry"},
                    event_type="BudgetDecision",
                )

        if not allowed_fields:
            return

        result = self.recovery.run(
            {
                "document": state.document,
                "entities": state.entities,
                "issues": state.validation_issues,
                "failing_fields": allowed_fields,
                "strategy": step.params.get("strategy") if step.params else None,
                "rag_hints": step.params.get("rag_hints") if step.params else None,
                "max_retries": ctx.config.budget.max_retries_per_field,
            },
            ctx,
        )
        state.entities = result.artifacts.get("entities", state.entities)
        state.recovered_fields = result.artifacts.get("recovered_fields", {})
        state.failed_recovery_fields = result.artifacts.get("failed_fields", [])
        state.recovery_log = result.artifacts.get("retry_log", [])
        signal = result.artifacts.get("signal")
        if signal:
            state.stage_signals.append(signal)
        if state.recovered_fields:
            self._run_validation(step, state, ctx, stage="post_recovery")

    def _run_escalation(
        self,
        step,
        state: ExecutionState,
        ctx: AgentContext,
        budget_remaining: float,
        count: int,
        failing_fields: List[str],
    ) -> None:
        estimated_cost = len(failing_fields) * float(ctx.config.escalation.estimated_cost_per_field)
        escalation_allowed = True
        block_reason = None
        if ctx.budget_manager:
            decision = ctx.budget_manager.allow_escalation(state.document.doc_id, estimated_cost)
            escalation_allowed = decision.allowed
            block_reason = decision.reason if not decision.allowed else None
            ctx.provenance.record(
                agent="budget_manager",
                version="v1",
                inputs={"doc_id": state.document.doc_id, "fields": failing_fields},
                outputs={"allowed": escalation_allowed, "reason": decision.reason},
                parameters={"action": "escalation", "estimated_cost": estimated_cost},
                event_type="BudgetDecision",
            )

        result = self.escalation.run(
            {
                "document": state.document,
                "issues": state.validation_issues,
                "signal": None,
                "count": count,
                "budget_remaining": budget_remaining,
                "fields": failing_fields,
                "target_model": step.params.get("target_model") if step.params else None,
                "escalation_allowed": escalation_allowed,
                "escalation_block_reason": block_reason,
            },
            ctx,
        )
        state.escalated = bool(result.artifacts.get("escalated", False))
        state.escalation_info = {
            "fields": result.artifacts.get("fields", failing_fields),
            "reason": result.artifacts.get("escalation_reason"),
            "cost_estimate": result.artifacts.get("cost_estimate"),
            "latency_estimate_ms": result.artifacts.get("latency_estimate_ms"),
            "target_model": result.artifacts.get("target_model"),
        }
        if state.escalated and ctx.budget_manager:
            ctx.budget_manager.record_escalation(state.document.doc_id, estimated_cost)
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

    def _failing_fields(self, state: ExecutionState) -> List[str]:
        failing = [issue.field for issue in state.validation_issues]
        for field, conf in state.field_confidence.items():
            if conf < 0.65 and field not in failing:
                failing.append(field)
        guardrail_flags = state.document.metadata.get("guardrail_flags", [])
        if isinstance(guardrail_flags, list):
            for item in guardrail_flags:
                if isinstance(item, dict):
                    field = item.get("field")
                    if field and field not in failing:
                        failing.append(str(field))
                elif isinstance(item, str) and item not in failing:
                    failing.append(item)
        return failing

    def _model_from_params(self, params: Dict[str, object], ctx: AgentContext) -> ModelDecision:
        model_tier = str(params.get("model_tier", ctx.config.llm.default_mode))
        mode = "cloud" if model_tier in {"cloud", "tier2"} else "local"
        model_name = ctx.config.llm.cloud_model if mode == "cloud" else ctx.config.llm.local_model
        return ModelDecision(mode=mode, model_name=model_name, reason="plan", metadata={"model_tier": model_tier})

"""Escalation agent for deciding when to flag documents for human review."""

from __future__ import annotations

import time

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, StageSignal, ValidationIssue

class EscalationAgent(Agent):
    name = "escalation"
    version = "v1"
    input_contract = {
        "document": "Document",
        "issues": "list",
        "signal": "StageSignal|None",
        "count": "int",
        "budget_remaining": "float|None",
        "fields": "list|None",
    }
    output_contract = {
        "escalated": "bool",
        "reason": "str",
        "signal": "StageSignal",
        "fields": "list",
        "escalation_status": "str",
    }

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        issues: list[ValidationIssue] = payload.get("issues", [])
        prior_signal = payload.get("signal")
        count = payload.get("count", 0)
        fields = payload.get("fields") or [issue.field for issue in issues]
        budget_remaining = payload.get("budget_remaining")
        escalated = False
        reason = ""
        status = "not_needed"
        if ctx.config.escalation.enabled and issues:
            escalated = True
            reason = "validation_issues"
            status = "attempted"

        cost_units = 0.5 * len(fields) if escalated else 0.0
        estimated_latency_ms = ctx.config.escalation.estimated_latency_ms_per_field * len(fields) if escalated else 0.0
        target_model = ctx.config.escalation.flagship_model if escalated else ""
        if budget_remaining is not None and cost_units > budget_remaining:
            escalated = False
            reason = "budget_remaining_exceeded"
            status = "budget_blocked"
            cost_units = 0.0
            estimated_latency_ms = 0.0
            target_model = ""
        if cost_units > ctx.config.escalation.max_cost_units:
            escalated = False
            reason = "budget_exceeded"
            status = "budget_blocked"
            cost_units = 0.0
            estimated_latency_ms = 0.0
            target_model = ""
        if count >= ctx.config.escalation.max_escalations_per_run:
            escalated = False
            reason = "rate_limited"
            status = "quota_blocked"
            cost_units = 0.0
            estimated_latency_ms = 0.0
            target_model = ""
        if prior_signal and prior_signal.confidence >= 0.75:
            escalated = False
            reason = "sufficient_confidence"
            status = "not_needed"
            cost_units = 0.0
            estimated_latency_ms = 0.0
            target_model = ""
        if status == "attempted" and not ctx.config.escalation.flagship_model.strip():
            escalated = False
            reason = "model_unavailable"
            status = "model_unavailable"
            cost_units = 0.0
            estimated_latency_ms = 0.0
            target_model = ""

        signal = StageSignal(
            stage=self.name,
            confidence=0.6 if escalated else 0.4,
            uncertainty=0.4 if escalated else 0.6,
            metadata={"escalated": escalated, "reason": reason, "status": status, "field_count": len(fields)},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id, "issue_count": len(issues)},
            outputs={"escalated": escalated, "reason": reason, "fields": fields, "status": status},
            parameters={"max_cost_units": ctx.config.escalation.max_cost_units, "budget_remaining": budget_remaining},
            started=started,
            cost_units=cost_units,
            event_type="EscalationAction",
        )
        return AgentResult(
            artifacts={
                "escalated": escalated,
                "escalation_reason": reason,
                "escalation_status": status,
                "fields": fields,
                "target_model": target_model,
                "estimated_cost_units": cost_units,
                "estimated_latency_ms": estimated_latency_ms,
                "signal": signal,
            }
        )

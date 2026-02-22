from __future__ import annotations

import time
from typing import List

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
    output_contract = {"escalated": "bool", "reason": "str", "signal": "StageSignal", "fields": "list"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        issues: List[ValidationIssue] = payload.get("issues", [])
        prior_signal = payload.get("signal")
        count = payload.get("count", 0)
        fields = payload.get("fields") or [issue.field for issue in issues]
        budget_remaining = payload.get("budget_remaining")
        escalated = False
        reason = ""
        if ctx.config.escalation.enabled and issues:
            escalated = True
            reason = "validation_issues"

        cost_units = 0.5 * len(fields) if escalated else 0.0
        if budget_remaining is not None and cost_units > budget_remaining:
            escalated = False
            reason = "budget_remaining_exceeded"
            cost_units = 0.0
        if cost_units > ctx.config.escalation.max_cost_units:
            escalated = False
            reason = "budget_exceeded"
            cost_units = 0.0
        if count >= ctx.config.escalation.max_escalations_per_run:
            escalated = False
            reason = "rate_limited"
            cost_units = 0.0
        if prior_signal and prior_signal.confidence >= 0.75:
            escalated = False
            reason = "sufficient_confidence"
            cost_units = 0.0

        signal = StageSignal(
            stage=self.name,
            confidence=0.6 if escalated else 0.4,
            uncertainty=0.4 if escalated else 0.6,
            metadata={"escalated": escalated, "reason": reason, "field_count": len(fields)},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id, "issue_count": len(issues)},
            outputs={"escalated": escalated, "reason": reason, "fields": fields},
            parameters={"max_cost_units": ctx.config.escalation.max_cost_units, "budget_remaining": budget_remaining},
            started=started,
            cost_units=cost_units,
            event_type="EscalationAction",
        )
        return AgentResult(
            artifacts={"escalated": escalated, "escalation_reason": reason, "fields": fields, "signal": signal}
        )

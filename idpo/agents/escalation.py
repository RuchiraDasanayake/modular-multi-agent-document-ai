from __future__ import annotations

import time
from typing import Dict, List

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, StageSignal, ValidationIssue


class EscalationAgent(Agent):
    name = "escalation"
    version = "v2"
    input_contract = {
        "document": "Document",
        "issues": "list",
        "signal": "StageSignal|None",
        "count": "int",
        "budget_remaining": "float|None",
        "fields": "list|None",
        "target_model": "str|None",
        "escalation_allowed": "bool|None",
        "escalation_block_reason": "str|None",
    }
    output_contract = {
        "escalated": "bool",
        "reason": "str",
        "signal": "StageSignal",
        "fields": "list",
        "cost_estimate": "float",
        "latency_estimate_ms": "float",
        "target_model": "str|None",
    }

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        issues: List[ValidationIssue] = payload.get("issues", [])
        prior_signal = payload.get("signal")
        count = int(payload.get("count", 0))
        fields = payload.get("fields") or [issue.field for issue in issues]
        fields = [field for field in fields if field]
        budget_remaining = payload.get("budget_remaining")
        target_model = payload.get("target_model") or ctx.config.escalation.flagship_model
        allowed = payload.get("escalation_allowed")
        block_reason = payload.get("escalation_block_reason")

        field_count = len(fields)
        cost_estimate = field_count * float(ctx.config.escalation.estimated_cost_per_field)
        latency_estimate_ms = field_count * float(ctx.config.escalation.estimated_latency_ms_per_field)

        escalated = False
        reason = ""
        if not ctx.config.escalation.enabled:
            reason = "escalation_disabled"
        elif not fields:
            reason = "no_failing_fields"
        elif allowed is False:
            reason = block_reason or "blocked_by_budget_manager"
        elif budget_remaining is not None and cost_estimate > float(budget_remaining):
            reason = "budget_remaining_exceeded"
        elif cost_estimate > float(ctx.config.escalation.max_cost_units):
            reason = "budget_exceeded"
        elif count >= int(ctx.config.escalation.max_escalations_per_run):
            reason = "rate_limited_run_quota"
        elif prior_signal and prior_signal.confidence >= 0.85:
            reason = "sufficient_confidence"
        elif not target_model:
            reason = "escalation_unavailable"
        else:
            escalated = True
            reason = "field_level_escalation"

        signal = StageSignal(
            stage=self.name,
            confidence=0.7 if escalated else 0.4,
            uncertainty=0.3 if escalated else 0.6,
            metadata={
                "escalated": escalated,
                "reason": reason,
                "field_count": field_count,
                "target_model": target_model,
            },
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id, "issue_count": len(issues), "fields": fields},
            outputs={
                "escalated": escalated,
                "reason": reason,
                "fields": fields,
                "cost_estimate": cost_estimate,
                "latency_estimate_ms": latency_estimate_ms,
                "target_model": target_model,
            },
            parameters={
                "max_cost_units": ctx.config.escalation.max_cost_units,
                "budget_remaining": budget_remaining,
                "fallback_mode": ctx.config.escalation.fallback_mode,
            },
            started=started,
            cost_units=cost_estimate if escalated else 0.0,
            event_type="EscalationAction",
        )
        return AgentResult(
            artifacts={
                "escalated": escalated,
                "escalation_reason": reason,
                "fields": fields,
                "cost_estimate": cost_estimate,
                "latency_estimate_ms": latency_estimate_ms,
                "target_model": target_model,
                "signal": signal,
            }
        )

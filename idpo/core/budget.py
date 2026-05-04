from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Tuple

from idpo.core.config import BudgetConfig


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    reason: str
    remaining_doc_cost: float
    remaining_minute_cost: float


@dataclass
class DocumentBudgetState:
    started_at: float
    cost_spent: float = 0.0
    retries_total: int = 0
    retries_per_field: Dict[str, int] = field(default_factory=dict)
    escalations: int = 0


class BudgetManager:
    """Central budget and rate-limit controller for retries/escalations."""

    def __init__(self, config: BudgetConfig) -> None:
        self.config = config
        self._doc_state: Dict[str, DocumentBudgetState] = {}
        self._minute_cost: Deque[Tuple[float, float]] = deque()
        self._minute_escalations: Deque[float] = deque()
        self._lock = threading.Lock()

    def start_document(self, doc_id: str) -> None:
        with self._lock:
            self._doc_state.setdefault(doc_id, DocumentBudgetState(started_at=time.time()))

    def allow_spend(
        self,
        doc_id: str,
        cost_units: float,
        elapsed_ms: float,
        operation: str,
    ) -> BudgetDecision:
        with self._lock:
            state = self._doc_state.setdefault(doc_id, DocumentBudgetState(started_at=time.time()))
            self._prune_windows()

            minute_cost = sum(item[1] for item in self._minute_cost)
            if state.cost_spent + cost_units > self.config.max_cost_per_doc:
                return self._decision(False, "max_cost_per_doc", state.cost_spent, minute_cost)
            if minute_cost + cost_units > self.config.max_cost_per_minute:
                return self._decision(False, "max_cost_per_minute", state.cost_spent, minute_cost)
            if elapsed_ms > self.config.max_latency_per_doc_ms:
                return self._decision(False, "max_latency_per_doc_soft_cutoff", state.cost_spent, minute_cost)
            return self._decision(True, operation, state.cost_spent, minute_cost)

    def spend(self, doc_id: str, cost_units: float) -> None:
        with self._lock:
            state = self._doc_state.setdefault(doc_id, DocumentBudgetState(started_at=time.time()))
            state.cost_spent += cost_units
            self._minute_cost.append((time.time(), cost_units))
            self._prune_windows()

    def allow_retry(self, doc_id: str, field: str) -> BudgetDecision:
        with self._lock:
            state = self._doc_state.setdefault(doc_id, DocumentBudgetState(started_at=time.time()))
            self._prune_windows()
            minute_cost = sum(item[1] for item in self._minute_cost)
            field_retries = state.retries_per_field.get(field, 0)
            if field_retries >= self.config.max_retries_per_field:
                return self._decision(False, "max_retries_per_field", state.cost_spent, minute_cost)
            if state.retries_total >= self.config.max_total_retries_per_doc:
                return self._decision(False, "max_total_retries_per_doc", state.cost_spent, minute_cost)
            return self._decision(True, "retry_allowed", state.cost_spent, minute_cost)

    def record_retry(self, doc_id: str, field: str) -> None:
        with self._lock:
            state = self._doc_state.setdefault(doc_id, DocumentBudgetState(started_at=time.time()))
            state.retries_total += 1
            state.retries_per_field[field] = state.retries_per_field.get(field, 0) + 1

    def allow_escalation(self, doc_id: str, estimated_cost: float) -> BudgetDecision:
        with self._lock:
            state = self._doc_state.setdefault(doc_id, DocumentBudgetState(started_at=time.time()))
            self._prune_windows()
            minute_cost = sum(item[1] for item in self._minute_cost)

            if state.escalations >= self.config.escalation_quota_per_doc:
                return self._decision(False, "escalation_quota_per_doc", state.cost_spent, minute_cost)
            if len(self._minute_escalations) >= self.config.escalation_quota_per_minute:
                return self._decision(False, "escalation_quota_per_minute", state.cost_spent, minute_cost)
            if state.cost_spent + estimated_cost > self.config.max_cost_per_doc:
                return self._decision(False, "max_cost_per_doc", state.cost_spent, minute_cost)
            if minute_cost + estimated_cost > self.config.max_cost_per_minute:
                return self._decision(False, "max_cost_per_minute", state.cost_spent, minute_cost)
            return self._decision(True, "escalation_allowed", state.cost_spent, minute_cost)

    def record_escalation(self, doc_id: str, cost_units: float) -> None:
        with self._lock:
            state = self._doc_state.setdefault(doc_id, DocumentBudgetState(started_at=time.time()))
            state.escalations += 1
            state.cost_spent += cost_units
            now = time.time()
            self._minute_cost.append((now, cost_units))
            self._minute_escalations.append(now)
            self._prune_windows()

    def snapshot(self, doc_id: str) -> Dict[str, object]:
        with self._lock:
            self._prune_windows()
            state = self._doc_state.get(doc_id)
            if not state:
                return {}
            minute_cost = sum(item[1] for item in self._minute_cost)
            return {
                "doc_id": doc_id,
                "cost_spent": state.cost_spent,
                "retries_total": state.retries_total,
                "retries_per_field": dict(state.retries_per_field),
                "escalations": state.escalations,
                "minute_cost": minute_cost,
                "minute_escalations": len(self._minute_escalations),
            }

    def _decision(
        self,
        allowed: bool,
        reason: str,
        doc_cost_spent: float,
        minute_cost: float,
    ) -> BudgetDecision:
        return BudgetDecision(
            allowed=allowed,
            reason=reason,
            remaining_doc_cost=max(self.config.max_cost_per_doc - doc_cost_spent, 0.0),
            remaining_minute_cost=max(self.config.max_cost_per_minute - minute_cost, 0.0),
        )

    def _prune_windows(self) -> None:
        now = time.time()
        cutoff = now - 60.0
        while self._minute_cost and self._minute_cost[0][0] < cutoff:
            self._minute_cost.popleft()
        while self._minute_escalations and self._minute_escalations[0] < cutoff:
            self._minute_escalations.popleft()

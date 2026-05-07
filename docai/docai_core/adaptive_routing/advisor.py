"""Review-Based Adaptive Routing advisor (read-only, evidence-gated)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from docai_core.adaptive_routing.evidence import FieldArmEvidence, ProjectEvidence
from docai_core.adaptive_routing.strategies import (
    ColdStartPriorStrategy,
    DriftDecayStrategy,
    EpsilonGreedyStrategy,
    ThompsonSamplingStrategy,
    UCB1Strategy,
)

ALLOWED_STRATEGIES = {"thompson_sampling", "ucb1", "epsilon_greedy", "all"}


@dataclass(slots=True)
class AdaptiveRoutingRecommendation:
    recommendation_id: str
    type: str
    severity: str
    schema_id: str | None
    field_name: str | None
    evidence_count: int
    correction_rate: float | None
    message: str
    suggested_action: str
    automatic_action_taken: bool = False


@dataclass(slots=True)
class AdaptiveRoutingAdvice:
    project_id: str
    evidence_count: int
    minimum_required: int
    status: str
    generated_by: str = "review_evidence_adaptive_routing_v1"
    is_read_only: bool = True
    automatic_action_taken: bool = False
    recommendations: list[AdaptiveRoutingRecommendation] = field(default_factory=list)
    diagnostics: dict[str, Any] | None = None


class AdaptiveRoutingAdvisor:
    def __init__(self, min_evidence: int = 10, apply_drift_decay: bool = True, half_life_days: int = 30):
        self.min_evidence = max(1, int(min_evidence))
        self.apply_drift_decay = bool(apply_drift_decay)
        self.half_life_days = max(1, int(half_life_days))

    def advise(
        self,
        evidence: ProjectEvidence,
        strategy: str | None = None,
        evaluation_time: datetime | None = None,
    ) -> AdaptiveRoutingAdvice:
        if evaluation_time is None:
            evaluation_time = datetime.now(timezone.utc)
        if strategy is not None and strategy not in ALLOWED_STRATEGIES:
            raise ValueError(f"Unsupported strategy: {strategy}")

        advice = AdaptiveRoutingAdvice(
            project_id=evidence.project_id,
            evidence_count=evidence.reviewed_sample_count,
            minimum_required=self.min_evidence,
            status="ready",
        )

        if evidence.reviewed_sample_count < self.min_evidence:
            advice.status = "insufficient_evidence"
            advice.recommendations = [
                AdaptiveRoutingRecommendation(
                    recommendation_id="insufficient_evidence_gate",
                    type="insufficient_evidence",
                    severity="info",
                    schema_id=None,
                    field_name=None,
                    evidence_count=evidence.reviewed_sample_count,
                    correction_rate=None,
                    message="Collect more reviewed corrections before enabling adaptive routing recommendations.",
                    suggested_action="Review and correct more documents to build reliable evidence.",
                )
            ]
            return advice

        advice.recommendations = self._build_recommendations(evidence)
        if strategy is not None:
            advice.diagnostics = self._build_diagnostics(
                evidence,
                strategy=strategy,
                evaluation_time=evaluation_time,
            )
        return advice

    def _build_recommendations(self, evidence: ProjectEvidence) -> list[AdaptiveRoutingRecommendation]:
        recommendations: list[AdaptiveRoutingRecommendation] = []
        seq = 1

        for arm in sorted(evidence.arms.values(), key=lambda row: (row.schema_id or "", row.field_name)):
            if arm.total_samples == 0 or arm.failures == 0:
                continue

            failures_by_type: dict[str, int] = {
                "wrong_value": 0,
                "missed_field": 0,
                "hallucinated_field": 0,
            }
            for sample in arm.samples:
                if sample.decision in failures_by_type:
                    failures_by_type[sample.decision] += 1

            dominant_type = max(failures_by_type, key=failures_by_type.get)
            if failures_by_type[dominant_type] == 0:
                continue

            if dominant_type == "wrong_value":
                rec_type = "field_frequently_corrected"
                suggested_action = "Review extraction instructions and field normalization rules for this field."
            elif dominant_type == "missed_field":
                rec_type = "field_frequently_missing"
                suggested_action = "Review schema field hints and document coverage for this field."
            else:
                rec_type = "field_frequently_hallucinated"
                suggested_action = "Tighten field constraints and validation around this field."

            severity = "warning" if arm.correction_rate >= 0.30 else "info"
            recommendations.append(
                AdaptiveRoutingRecommendation(
                    recommendation_id=f"rec_{seq}",
                    type=rec_type,
                    severity=severity,
                    schema_id=arm.schema_id,
                    field_name=arm.field_name,
                    evidence_count=arm.total_samples,
                    correction_rate=arm.correction_rate,
                    message=(
                        f"Field '{arm.field_name}' has correction rate {arm.correction_rate:.2f} "
                        f"from {arm.total_samples} reviewed samples."
                    ),
                    suggested_action=suggested_action,
                )
            )
            seq += 1

        schema_counts: dict[str, tuple[int, int]] = {}
        for arm in evidence.arms.values():
            if arm.schema_id is None:
                continue
            success, failure = schema_counts.get(arm.schema_id, (0, 0))
            schema_counts[arm.schema_id] = (success + arm.successes, failure + arm.failures)

        for schema_id, (successes, failures) in schema_counts.items():
            total = successes + failures
            if total < 5:
                continue
            rate = failures / total
            if rate >= 0.40:
                recommendations.append(
                    AdaptiveRoutingRecommendation(
                        recommendation_id=f"rec_{seq}",
                        type="schema_needs_review",
                        severity="warning",
                        schema_id=schema_id,
                        field_name=None,
                        evidence_count=total,
                        correction_rate=rate,
                        message=f"Schema '{schema_id}' shows elevated correction rate ({rate:.2f}) in reviewed evidence.",
                        suggested_action="Review schema-level field definitions and extraction guidance for this schema.",
                    )
                )
                seq += 1

        return recommendations

    def _build_diagnostics(
        self,
        evidence: ProjectEvidence,
        strategy: str | None,
        evaluation_time: datetime,
    ) -> dict[str, Any]:
        arms = [arm for arm in evidence.arms.values() if arm.total_samples > 0]
        total_samples = sum(arm.total_samples for arm in arms)
        diagnostics: dict[str, Any] = {}

        include_all = strategy == "all"
        if include_all or strategy == "thompson_sampling":
            ts = ThompsonSamplingStrategy()
            diagnostics["thompson_sampling"] = [
                {
                    "arm_id": diag.arm_id,
                    "field_name": diag.field_name,
                    "alpha": round(diag.alpha, 6),
                    "beta": round(diag.beta, 6),
                    "mean": round(diag.mean, 6),
                }
                for arm in arms
                for diag in [ts.evaluate(arm)]
                if diag is not None
            ]

        if include_all or strategy == "ucb1":
            ucb = UCB1Strategy()
            diagnostics["ucb1"] = [
                {
                    "arm_id": diag.arm_id,
                    "field_name": diag.field_name,
                    "empirical_score": round(diag.empirical_score, 6),
                    "exploration_bonus": round(diag.exploration_bonus, 6),
                    "ucb1_score": round(diag.ucb1_score, 6),
                }
                for arm in arms
                for diag in [ucb.evaluate(arm, max(total_samples, 1))]
                if diag is not None
            ]

        if include_all or strategy == "epsilon_greedy":
            eg = EpsilonGreedyStrategy().summarize(arms)
            diagnostics["epsilon_greedy"] = {
                "best_arm_id": eg.best_arm_id,
                "exploration_candidates": eg.exploration_candidates,
            }

        if include_all:
            csp = ColdStartPriorStrategy()
            diagnostics["cold_start_prior"] = [
                {
                    "arm_id": diag.arm_id,
                    "field_name": diag.field_name,
                    "prior_alpha": round(diag.prior_alpha, 6),
                    "prior_beta": round(diag.prior_beta, 6),
                    "priors_used": diag.priors_used,
                }
                for arm in arms
                for diag in [csp.estimate(arm, arms)]
            ]

            drift = DriftDecayStrategy(half_life_days=self.half_life_days)
            diagnostics["drift_decay"] = [
                {
                    "arm_id": diag.arm_id,
                    "field_name": diag.field_name,
                    "decay_applied": bool(self.apply_drift_decay and diag.decay_applied),
                    "half_life_days": diag.half_life_days,
                    "raw_samples": diag.raw_samples,
                    "effective_successes": round(diag.effective_successes if self.apply_drift_decay else float(sum(1 for s in arm.samples if s.decision in {"correct", "correctly_skipped"})), 6),
                    "effective_failures": round(diag.effective_failures if self.apply_drift_decay else float(sum(1 for s in arm.samples if s.decision in {"wrong_value", "missed_field", "hallucinated_field"})), 6),
                }
                for arm in arms
                for diag in [drift.evaluate(arm, evaluation_time=evaluation_time)]
            ]

        return diagnostics

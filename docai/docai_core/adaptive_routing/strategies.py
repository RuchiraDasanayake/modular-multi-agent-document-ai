"""Deterministic diagnostics for Review-Based Adaptive Routing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import log, sqrt

from docai_core.adaptive_routing.evidence import (
    FAILURE_DECISIONS,
    SUCCESS_DECISIONS,
    FieldArmEvidence,
)


@dataclass(slots=True)
class ThompsonSamplingDiagnostic:
    arm_id: str
    field_name: str
    alpha: float
    beta: float
    mean: float


@dataclass(slots=True)
class UCB1Diagnostic:
    arm_id: str
    field_name: str
    empirical_score: float
    exploration_bonus: float
    ucb1_score: float


@dataclass(slots=True)
class EpsilonGreedySummary:
    best_arm_id: str | None
    exploration_candidates: list[str]


@dataclass(slots=True)
class ColdStartPriorDiagnostic:
    arm_id: str
    field_name: str
    prior_alpha: float
    prior_beta: float
    priors_used: bool


@dataclass(slots=True)
class DriftDecayDiagnostic:
    arm_id: str
    field_name: str
    decay_applied: bool
    half_life_days: int
    raw_samples: int
    effective_successes: float
    effective_failures: float


class ThompsonSamplingStrategy:
    def evaluate(self, arm: FieldArmEvidence, prior_alpha: float = 1.0, prior_beta: float = 1.0) -> ThompsonSamplingDiagnostic | None:
        if arm.total_samples <= 0:
            return None
        alpha = prior_alpha + arm.successes
        beta = prior_beta + arm.failures
        mean = alpha / (alpha + beta)
        return ThompsonSamplingDiagnostic(
            arm_id=arm.arm_id,
            field_name=arm.field_name,
            alpha=alpha,
            beta=beta,
            mean=mean,
        )


class UCB1Strategy:
    def evaluate(self, arm: FieldArmEvidence, total_samples: int) -> UCB1Diagnostic | None:
        if arm.total_samples <= 0 or total_samples <= 0:
            return None
        empirical = arm.successes / arm.total_samples
        bonus = sqrt((2.0 * log(total_samples)) / arm.total_samples)
        return UCB1Diagnostic(
            arm_id=arm.arm_id,
            field_name=arm.field_name,
            empirical_score=empirical,
            exploration_bonus=bonus,
            ucb1_score=empirical + bonus,
        )


class EpsilonGreedyStrategy:
    def summarize(self, arms: list[FieldArmEvidence]) -> EpsilonGreedySummary:
        populated = [arm for arm in arms if arm.total_samples > 0]
        if not populated:
            return EpsilonGreedySummary(best_arm_id=None, exploration_candidates=[])

        ranked = sorted(
            populated,
            key=lambda arm: ((arm.successes / arm.total_samples), arm.total_samples, arm.arm_id),
            reverse=True,
        )
        best = ranked[0].arm_id
        candidates = [arm.arm_id for arm in ranked[1:]]
        return EpsilonGreedySummary(best_arm_id=best, exploration_candidates=candidates)


class ColdStartPriorStrategy:
    """Cold-start prior diagnostic."""

    def estimate(self, arm: FieldArmEvidence, all_arms: list[FieldArmEvidence]) -> ColdStartPriorDiagnostic:
        if arm.total_samples >= 5:
            return ColdStartPriorDiagnostic(
                arm_id=arm.arm_id,
                field_name=arm.field_name,
                prior_alpha=1.0,
                prior_beta=1.0,
                priors_used=False,
            )

        similar = [
            other
            for other in all_arms
            if other.arm_id != arm.arm_id and other.field_name == arm.field_name and other.total_samples > 0
        ]
        if not similar:
            return ColdStartPriorDiagnostic(
                arm_id=arm.arm_id,
                field_name=arm.field_name,
                prior_alpha=1.0,
                prior_beta=1.0,
                priors_used=False,
            )

        total_successes = sum(item.successes for item in similar)
        total_failures = sum(item.failures for item in similar)
        prior_alpha = 1.0 + (total_successes / max(len(similar), 1))
        prior_beta = 1.0 + (total_failures / max(len(similar), 1))
        return ColdStartPriorDiagnostic(
            arm_id=arm.arm_id,
            field_name=arm.field_name,
            prior_alpha=prior_alpha,
            prior_beta=prior_beta,
            priors_used=True,
        )


class DriftDecayStrategy:
    """Drift decay diagnostic."""

    def __init__(self, half_life_days: int = 30):
        self.half_life_days = max(1, half_life_days)

    def evaluate(self, arm: FieldArmEvidence, evaluation_time: datetime | None = None) -> DriftDecayDiagnostic:
        if evaluation_time is None:
            evaluation_time = datetime.now(timezone.utc)

        eff_successes = 0.0
        eff_failures = 0.0
        decay_applied = False

        for sample in arm.samples:
            if sample.created_at is None:
                weight = 1.0
            else:
                age_days = max(0.0, (evaluation_time - sample.created_at).total_seconds() / 86400.0)
                weight = 2.0 ** (-age_days / self.half_life_days)
                if age_days > 0.0:
                    decay_applied = True

            if sample.decision in SUCCESS_DECISIONS:
                eff_successes += weight
            elif sample.decision in FAILURE_DECISIONS:
                eff_failures += weight

        return DriftDecayDiagnostic(
            arm_id=arm.arm_id,
            field_name=arm.field_name,
            decay_applied=decay_applied,
            half_life_days=self.half_life_days,
            raw_samples=arm.total_samples,
            effective_successes=eff_successes,
            effective_failures=eff_failures,
        )

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from docai_core.adaptive_routing.evidence import EvidenceSample, FieldArmEvidence
from docai_core.adaptive_routing.strategies import (
    ColdStartPriorStrategy,
    DriftDecayStrategy,
    EpsilonGreedyStrategy,
    ThompsonSamplingStrategy,
    UCB1Strategy,
)


def _arm(field_name: str, successes: int, failures: int) -> FieldArmEvidence:
    arm = FieldArmEvidence(arm_id=f"invoice:{field_name}", schema_id="invoice", field_name=field_name)
    for _ in range(successes):
        arm.samples.append(EvidenceSample(schema_id="invoice", field_name=field_name, decision="correct", created_at=None))
        arm.successes += 1
    for _ in range(failures):
        arm.samples.append(EvidenceSample(schema_id="invoice", field_name=field_name, decision="wrong_value", created_at=None))
        arm.failures += 1
    return arm


def test_thompson_sampling_returns_expected_alpha_beta_mean() -> None:
    diag = ThompsonSamplingStrategy().evaluate(_arm("invoice_number", successes=9, failures=1))
    assert diag is not None
    assert diag.alpha == 10.0
    assert diag.beta == 2.0
    assert abs(diag.mean - (10.0 / 12.0)) < 1e-9


def test_ucb1_returns_empirical_and_bonus() -> None:
    diag = UCB1Strategy().evaluate(_arm("invoice_number", successes=8, failures=2), total_samples=100)
    assert diag is not None
    assert abs(diag.empirical_score - 0.8) < 1e-9
    assert diag.exploration_bonus > 0
    assert diag.ucb1_score > diag.empirical_score


def test_epsilon_greedy_returns_best_and_exploration_candidates() -> None:
    best = _arm("invoice_number", successes=8, failures=2)
    other = _arm("vendor_name", successes=6, failures=4)
    summary = EpsilonGreedyStrategy().summarize([best, other])

    assert summary.best_arm_id == best.arm_id
    assert summary.exploration_candidates == [other.arm_id]


def test_cold_start_prior_uses_neutral_when_no_similar_arm() -> None:
    target = _arm("invoice_number", successes=1, failures=0)
    diag = ColdStartPriorStrategy().estimate(target, [target])

    assert diag.prior_alpha == 1.0
    assert diag.prior_beta == 1.0
    assert diag.priors_used is False


def test_cold_start_prior_transfers_from_similar_fields() -> None:
    target = _arm("invoice_number", successes=1, failures=0)
    similar = FieldArmEvidence(
        arm_id="receipt:invoice_number",
        schema_id="receipt",
        field_name="invoice_number",
        successes=9,
        failures=1,
        samples=[
            EvidenceSample(schema_id="receipt", field_name="invoice_number", decision="correct", created_at=None)
            for _ in range(10)
        ],
    )

    diag = ColdStartPriorStrategy().estimate(target, [target, similar])
    assert diag.priors_used is True
    assert diag.prior_alpha > 1.0
    assert diag.prior_beta >= 1.0


def test_ucb1_handles_zero_samples_without_crash() -> None:
    # UCB1 should handle zero samples gracefully (though in practice this shouldn't happen)
    arm = FieldArmEvidence(arm_id="invoice:invoice_number", schema_id="invoice", field_name="invoice_number")
    # No samples added, so successes=0, failures=0

    diag = UCB1Strategy().evaluate(arm, total_samples=100)
    # With zero samples, returns None (no crash)
    assert diag is None


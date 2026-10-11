"""
Tests for AHMN's three core algorithms:
  1. Thompson Sampling  — best arm selected, exploration preserved
  2. RABI               — cold-start knowledge transfer from neighbors
  3. DAAF               — drift detection and adaptive forgetting
"""
import random
import pytest
import numpy as np

from ahmn_core.services.selection_strategies import (
    BanditArm, ThompsonSamplingStrategy, UCB1Strategy, get_strategy,
)
from ahmn_core.services.rabi import RABIInitializer, NeighborInfo
from ahmn_core.services.drift_forgetting import (
    DriftEstimator, AdaptiveForgettingBandit, DriftType,
)

class TestThompsonSampling:

    @pytest.fixture
    def arms(self):
        return [
            BanditArm(policy_id="good",  policy_data={}, context_hash="c", alpha=15.0, beta=3.0,  pulls=16),
            BanditArm(policy_id="mid",   policy_data={}, context_hash="c", alpha=5.0,  beta=5.0,  pulls=8),
            BanditArm(policy_id="new",   policy_data={}, context_hash="c", alpha=1.0,  beta=1.0,  pulls=0),
        ]

    def test_favors_best_arm(self, arms):
        """High-alpha arm should be selected most often."""
        np.random.seed(42)
        random.seed(42)
        ts = ThompsonSamplingStrategy()
        counts = {a.policy_id: 0 for a in arms}
        for t in range(1000):
            arm, _ = ts.select(arms, t)
            counts[arm.policy_id] += 1
        assert counts["good"] > counts["mid"]

    def test_still_explores(self, arms):
        """Even low-confidence arms get explored."""
        random.seed(42)
        ts = ThompsonSamplingStrategy()
        selected = set()
        for t in range(500):
            arm, _ = ts.select(arms, t)
            selected.add(arm.policy_id)
        assert len(selected) == 3

    def test_ucb1_picks_unpulled_first(self, arms):
        """UCB1 should prioritize arms with zero pulls."""
        ucb = UCB1Strategy(c=2.0)
        arm, score = ucb.select(arms, 10)
        assert arm.policy_id == "new"
        assert score == float("inf")

    def test_strategy_factory(self):
        assert isinstance(get_strategy("thompson"), ThompsonSamplingStrategy)
        with pytest.raises(ValueError):
            get_strategy("nonexistent")

# ── RABI (Cold-Start Transfer) ────────────────────────────────────

class TestRABI:

    @pytest.fixture
    def rabi(self):
        return RABIInitializer(
            k=5, similarity_threshold=0.4, temperature=0.5,
            min_samples_for_transfer=5, max_transfer_strength=10.0,
        )

    @pytest.fixture
    def good_neighbors(self):
        """Similar vendors with enough history to transfer from."""
        return [
            NeighborInfo(context_hash="h1", policy_id="p1", alpha=15, beta=3, similarity=0.85, n_samples=16),
            NeighborInfo(context_hash="h2", policy_id="p2", alpha=12, beta=4, similarity=0.72, n_samples=14),
            NeighborInfo(context_hash="h3", policy_id="p3", alpha=8,  beta=6, similarity=0.51, n_samples=12),
        ]

    def test_transfers_knowledge(self, rabi, good_neighbors):
        """With similar neighbors, prior should be informed (not flat)."""
        prior = rabi.initialize_prior(good_neighbors)
        assert prior.alpha > 1.0
        assert prior.beta > 1.0
        assert prior.n_neighbors == 3
        assert 0.0 < prior.mean < 1.0

    def test_flat_prior_fallback(self, rabi):
        """No neighbors → flat Beta(1,1) prior."""
        prior = rabi.initialize_prior([])
        assert prior.alpha == 1.0
        assert prior.beta == 1.0
        assert prior.n_neighbors == 0

    def test_weak_neighbors_filtered(self, rabi):
        """Low-similarity or low-sample neighbors are ignored."""
        weak = [
            NeighborInfo("h1", "p1", alpha=15, beta=3, similarity=0.2, n_samples=16),
            NeighborInfo("h2", "p2", alpha=12, beta=4, similarity=0.8, n_samples=2),
        ]
        prior = rabi.initialize_prior(weak)
        assert prior.alpha == 1.0  # Fell back to flat

    def test_transfer_strength_capped(self):
        """Extreme neighbor evidence is capped to prevent overconfidence."""
        rabi = RABIInitializer(
            similarity_threshold=0.3, max_transfer_strength=5.0, min_samples_for_transfer=0,
        )
        extreme = [NeighborInfo("h1", "p1", alpha=100, beta=5, similarity=0.9, n_samples=103)]
        prior = rabi.initialize_prior(extreme)
        total = abs(prior.alpha - 1.0) + abs(prior.beta - 1.0)
        assert total <= 5.01  # Capped

# ── DAAF (Drift Detection & Adaptive Forgetting) ─────────────────

class TestDAAF:

    @pytest.fixture
    def estimator(self):
        return DriftEstimator(window_size=50, min_samples=10,
                              drift_threshold=0.05, abrupt_threshold=0.15)

    def test_stable_no_drift(self, estimator):
        """Constant rewards → no drift."""
        for _ in range(120):
            metrics = estimator.update(0.8)
        assert metrics.drift_type == DriftType.NONE
        assert metrics.is_drifting is False

    def test_abrupt_drift_detected(self, estimator):
        """Sharp reward drop triggers abrupt drift."""
        for _ in range(60):
            estimator.update(0.9)
        for _ in range(60):
            metrics = estimator.update(0.3)
        assert metrics.is_drifting is True
        assert metrics.drift_type == DriftType.ABRUPT

    def test_higher_drift_higher_gamma(self):
        """More drift → higher forgetting rate."""
        small = DriftEstimator(window_size=50)
        big = DriftEstimator(window_size=50)

        for _ in range(60):
            small.update(0.8)
        for _ in range(60):
            m_small = small.update(0.7)

        for _ in range(60):
            big.update(0.9)
        for _ in range(60):
            m_big = big.update(0.3)

        assert m_big.optimal_gamma > m_small.optimal_gamma

    def test_bandit_adapts_to_drift(self):
        """AdaptiveForgettingBandit increases gamma when drift occurs."""
        bandit = AdaptiveForgettingBandit(window_size=50, min_gamma=0.001, max_gamma=0.3)
        for _ in range(60):
            bandit.update("arm1", 0.9)
        for _ in range(60):
            bandit.update("arm1", 0.3)
        stats = bandit.get_arm_stats("arm1")
        assert stats["last_gamma"] > 0.05


class TestSimulationReproducibility:

    def test_seed_fixes_the_run_regardless_of_global_random_state(self):
        """Published regret tables must not depend on what ran earlier in the process."""
        from ahmn_core.experiments.run_experiments import AHMNFullRunner, run_single
        from ahmn_core.experiments.synthetic_data import create_drift_scenario

        scenario = create_drift_scenario(n_rounds=300)
        np.random.seed(1)
        random.seed(1)
        first = run_single(AHMNFullRunner(scenario.policy_ids), scenario, seed=3)
        np.random.seed(2)
        random.seed(2)
        second = run_single(AHMNFullRunner(scenario.policy_ids), scenario, seed=3)

        assert second.selected_policies == first.selected_policies
        assert second.total_regret == first.total_regret

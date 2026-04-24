"""
AHMN Experimental Evaluation Runner.

Runs all bandit strategies across all scenarios with multiple seeds,
collects metrics, and outputs structured results for analysis.

Methods compared:
  1. Random         — uniform random policy selection
  2. ε-Greedy       — epsilon-greedy with exponential decay
  3. UCB1           — upper confidence bound
  4. TS (base)      — Thompson Sampling with flat Beta(1,1) priors
  5. AHMN-RABI      — TS + RABI cold-start transfer (no DAAF)
  6. AHMN-DAAF      — TS + DAAF adaptive forgetting (no RABI)
  7. AHMN-Full      — TS + RABI + DAAF (complete system)

Metrics collected per run:
  - Cumulative regret over time
  - Per-round reward (F1 score)
  - Convergence round (first round where rolling-50 avg > 95% of oracle)
  - Policy selection accuracy (% of rounds choosing the oracle-best policy)
  - Final average reward over last 100 rounds

Usage:
    cd ahmn_core
    python -m experiments.run_experiments
"""

import sys
import os
import json
import time
import numpy as np

from dataclasses import dataclass, field, asdict

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ahmn_core.services.selection_strategies import (
    BanditArm, ThompsonSamplingStrategy, UCB1Strategy,
    EpsilonGreedyStrategy, RandomStrategy
)
from ahmn_core.services.rabi import RABIInitializer, NeighborInfo, RABIPrior
from ahmn_core.services.drift_forgetting import (
    DriftEstimator, AdaptiveForgettingBandit, DriftType
)
from ahmn_core.experiments.synthetic_data import (
    Scenario, VendorProfile, DriftEvent,
    cosine_similarity, get_all_scenarios, POLICY_IDS,
    _make_cluster_embedding,
    create_stationary_scenario, create_cold_start_scenario,
    create_drift_scenario, create_combined_scenario,
)

# ═══════════════════════════════════════════════════════════════════════════════
# RESULT DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RunResult:
    """Result of a single experiment run (one method, one scenario, one seed)."""
    method: str
    scenario: str
    seed: int
    rewards: list[float]             # Per-round rewards
    cumulative_regret: list[float]   # Cumulative regret over time
    oracle_rewards: list[float]      # Oracle (best possible) per round
    selected_policies: list[str]     # Which policy was chosen each round
    optimal_policies: list[str]      # Oracle-best policy each round
    
    @property
    def n_rounds(self) -> int:
        return len(self.rewards)
    
    @property
    def total_regret(self) -> float:
        return self.cumulative_regret[-1] if self.cumulative_regret else 0.0
    
    @property
    def final_avg_reward(self) -> float:
        """Average reward over last 100 rounds."""
        tail = self.rewards[-100:]
        return float(np.mean(tail)) if tail else 0.0
    
    @property
    def policy_accuracy(self) -> float:
        """Fraction of rounds where the oracle-best policy was selected."""
        if not self.selected_policies:
            return 0.0
        correct = sum(1 for s, o in zip(self.selected_policies, self.optimal_policies) if s == o)
        return correct / len(self.selected_policies)
    
    @property
    def convergence_round(self) -> int | None:
        """First round where rolling-50 average exceeds 95% of oracle average."""
        if len(self.rewards) < 50:
            return None
        oracle_mean = float(np.mean(self.oracle_rewards))
        threshold = 0.95 * oracle_mean
        for i in range(50, len(self.rewards)):
            window = self.rewards[i-50:i]
            if np.mean(window) >= threshold:
                return i
        return None
    
    def to_summary(self) -> dict:
        """Compact summary for JSON output (scalars only)."""
        return {
            "method": self.method,
            "scenario": self.scenario,
            "seed": self.seed,
            "total_regret": round(self.total_regret, 3),
            "final_avg_reward": round(self.final_avg_reward, 4),
            "policy_accuracy": round(self.policy_accuracy, 4),
            "convergence_round": self.convergence_round,
            "n_rounds": self.n_rounds,
        }

    def to_full(self) -> dict:
        """Full record including per-round arrays — for curve plotting."""
        return {
            **self.to_summary(),
            "cumulative_regret": [round(v, 4) for v in self.cumulative_regret],
            "rewards": [round(v, 4) for v in self.rewards],
            "oracle_rewards": [round(v, 4) for v in self.oracle_rewards],
        }

# ═══════════════════════════════════════════════════════════════════════════════
# METHOD IMPLEMENTATIONS (wrappers for the actual algorithm classes)
# ═══════════════════════════════════════════════════════════════════════════════

class MethodRunner:
    """Base class for running a bandit method through a scenario."""
    
    def __init__(self, name: str, policy_ids: list[str]):
        self.name = name
        self.policy_ids = policy_ids
        # Per-vendor, per-policy arm tracking
        self.arms: dict[str, dict[str, BanditArm]] = {}
    
    def _get_arms(self, vendor_id: str) -> dict[str, BanditArm]:
        """Get or create arms for a vendor."""
        if vendor_id not in self.arms:
            self.arms[vendor_id] = {
                pid: BanditArm(
                    policy_id=pid,
                    policy_data={"engine": pid},
                    context_hash=vendor_id,
                    alpha=1.0,
                    beta=1.0,
                    pulls=0,
                )
                for pid in self.policy_ids
            }
        return self.arms[vendor_id]
    
    def select_policy(self, vendor: VendorProfile, round_num: int,
                      all_vendors: list[VendorProfile]) -> str:
        """Select a policy for this vendor. Override in subclasses."""
        raise NotImplementedError
    
    def update(self, vendor: VendorProfile, policy_id: str, reward: float,
               round_num: int):
        """Update after observing reward. Override in subclasses."""
        arms = self._get_arms(vendor.vendor_id)
        arm = arms[policy_id]
        arm.alpha += reward
        arm.beta += (1.0 - reward)
        arm.pulls += 1
    
    def reset(self):
        """Reset state for a new run."""
        self.arms = {}

class RandomRunner(MethodRunner):
    def __init__(self, policy_ids: list[str]):
        super().__init__("Random", policy_ids)
        self.strategy = RandomStrategy()
    
    def select_policy(self, vendor, round_num, all_vendors):
        arms = list(self._get_arms(vendor.vendor_id).values())
        selected, _ = self.strategy.select(arms, round_num)
        return selected.policy_id

class EpsilonGreedyRunner(MethodRunner):
    def __init__(self, policy_ids: list[str]):
        super().__init__("e-Greedy", policy_ids)
        self.strategy = EpsilonGreedyStrategy(
            epsilon_0=1.0, decay_rate=0.003, epsilon_min=0.01
        )
    
    def select_policy(self, vendor, round_num, all_vendors):
        arms = list(self._get_arms(vendor.vendor_id).values())
        selected, _ = self.strategy.select(arms, round_num)
        return selected.policy_id

class UCB1Runner(MethodRunner):
    def __init__(self, policy_ids: list[str]):
        super().__init__("UCB1", policy_ids)
        self.strategy = UCB1Strategy(c=2.0)
    
    def select_policy(self, vendor, round_num, all_vendors):
        arms = list(self._get_arms(vendor.vendor_id).values())
        selected, _ = self.strategy.select(arms, round_num)
        return selected.policy_id

class ThompsonSamplingRunner(MethodRunner):
    """Plain Thompson Sampling — no RABI, no DAAF."""
    def __init__(self, policy_ids: list[str]):
        super().__init__("TS (base)", policy_ids)
        self.strategy = ThompsonSamplingStrategy()
    
    def select_policy(self, vendor, round_num, all_vendors):
        arms = list(self._get_arms(vendor.vendor_id).values())
        selected, _ = self.strategy.select(arms, round_num)
        return selected.policy_id

class AHMNRABIRunner(MethodRunner):
    """Thompson Sampling + RABI (cold-start transfer, no DAAF)."""
    def __init__(self, policy_ids: list[str], temperature: float = 0.5,
                 similarity_threshold: float = 0.4):
        super().__init__("AHMN-RABI", policy_ids)
        self.rabi = RABIInitializer(
            k=5,
            similarity_threshold=similarity_threshold,
            temperature=temperature,
            min_samples_for_transfer=5,
            max_transfer_strength=10.0,
        )
        self.strategy = ThompsonSamplingStrategy()
        self._initialized_vendors = set()
    
    def _try_rabi_init(self, vendor: VendorProfile, all_vendors: list[VendorProfile]):
        """Use RABI to initialize arms for a new vendor from neighbors."""
        if vendor.vendor_id in self._initialized_vendors:
            return
        self._initialized_vendors.add(vendor.vendor_id)
        
        # Build neighbor info from all OTHER vendors' arms
        for pid in self.policy_ids:
            neighbors = []
            for other in all_vendors:
                if other.vendor_id == vendor.vendor_id:
                    continue
                if other.vendor_id not in self.arms:
                    continue
                other_arm = self.arms[other.vendor_id].get(pid)
                if other_arm is None:
                    continue
                
                sim = cosine_similarity(vendor.embedding, other.embedding)
                neighbors.append(NeighborInfo(
                    context_hash=other.vendor_id,
                    policy_id=pid,
                    alpha=other_arm.alpha,
                    beta=other_arm.beta,
                    similarity=sim,
                    n_samples=other_arm.pulls,
                ))
            
            if neighbors:
                prior = self.rabi.initialize_prior(neighbors)
                arms = self._get_arms(vendor.vendor_id)
                arms[pid].alpha = prior.alpha
                arms[pid].beta = prior.beta
    
    def select_policy(self, vendor, round_num, all_vendors):
        self._try_rabi_init(vendor, all_vendors)
        arms = list(self._get_arms(vendor.vendor_id).values())
        selected, _ = self.strategy.select(arms, round_num)
        return selected.policy_id
    
    def reset(self):
        super().reset()
        self._initialized_vendors = set()

class AHMNDAAFRunner(MethodRunner):
    """Thompson Sampling + DAAF (drift-aware forgetting, no RABI)."""
    def __init__(self, policy_ids: list[str], window_size: int = 50):
        super().__init__("AHMN-DAAF", policy_ids)
        self.strategy = ThompsonSamplingStrategy()
        self.drift_estimators: dict[str, dict[str, DriftEstimator]] = {}
        self.window_size = window_size
    
    def _get_estimator(self, vendor_id: str, policy_id: str) -> DriftEstimator:
        if vendor_id not in self.drift_estimators:
            self.drift_estimators[vendor_id] = {}
        if policy_id not in self.drift_estimators[vendor_id]:
            self.drift_estimators[vendor_id][policy_id] = DriftEstimator(
                window_size=self.window_size, min_samples=10,
                drift_threshold=0.05, abrupt_threshold=0.15
            )
        return self.drift_estimators[vendor_id][policy_id]
    
    def select_policy(self, vendor, round_num, all_vendors):
        arms = list(self._get_arms(vendor.vendor_id).values())
        selected, _ = self.strategy.select(arms, round_num)
        return selected.policy_id
    
    def update(self, vendor, policy_id, reward, round_num):
        arms = self._get_arms(vendor.vendor_id)
        arm = arms[policy_id]
        
        # DAAF: detect drift and compute γ*
        estimator = self._get_estimator(vendor.vendor_id, policy_id)
        drift_metrics = estimator.update(reward)
        gamma = drift_metrics.optimal_gamma
        
        # Apply forgetting then update
        retention = 1.0 - gamma
        arm.alpha = max(0.01, 1.0 + retention * (arm.alpha - 1.0))
        arm.beta = max(0.01, 1.0 + retention * (arm.beta - 1.0))
        
        # Boost for abrupt drift
        if drift_metrics.drift_type == DriftType.ABRUPT:
            arm.alpha = 1.0 + 0.5 * (arm.alpha - 1.0)
            arm.beta = 1.0 + 0.5 * (arm.beta - 1.0)
        
        arm.alpha += reward
        arm.beta += (1.0 - reward)
        arm.pulls += 1
    
    def reset(self):
        super().reset()
        self.drift_estimators = {}

class AHMNFullRunner(MethodRunner):
    """Full AHMN: Thompson Sampling + RABI + DAAF."""
    def __init__(self, policy_ids: list[str], temperature: float = 0.5,
                 similarity_threshold: float = 0.4):
        super().__init__("AHMN-Full", policy_ids)
        self.rabi = RABIInitializer(
            k=5,
            similarity_threshold=similarity_threshold,
            temperature=temperature,
            min_samples_for_transfer=5,
            max_transfer_strength=10.0,
        )
        self.strategy = ThompsonSamplingStrategy()
        self.drift_estimators: dict[str, dict[str, DriftEstimator]] = {}
        self._initialized_vendors = set()
    
    def _try_rabi_init(self, vendor: VendorProfile, all_vendors: list[VendorProfile]):
        if vendor.vendor_id in self._initialized_vendors:
            return
        self._initialized_vendors.add(vendor.vendor_id)
        
        for pid in self.policy_ids:
            neighbors = []
            for other in all_vendors:
                if other.vendor_id == vendor.vendor_id:
                    continue
                if other.vendor_id not in self.arms:
                    continue
                other_arm = self.arms[other.vendor_id].get(pid)
                if other_arm is None:
                    continue
                sim = cosine_similarity(vendor.embedding, other.embedding)
                neighbors.append(NeighborInfo(
                    context_hash=other.vendor_id,
                    policy_id=pid,
                    alpha=other_arm.alpha,
                    beta=other_arm.beta,
                    similarity=sim,
                    n_samples=other_arm.pulls,
                ))
            
            if neighbors:
                prior = self.rabi.initialize_prior(neighbors)
                arms = self._get_arms(vendor.vendor_id)
                arms[pid].alpha = prior.alpha
                arms[pid].beta = prior.beta
    
    def _get_estimator(self, vendor_id: str, policy_id: str) -> DriftEstimator:
        if vendor_id not in self.drift_estimators:
            self.drift_estimators[vendor_id] = {}
        if policy_id not in self.drift_estimators[vendor_id]:
            self.drift_estimators[vendor_id][policy_id] = DriftEstimator(
                window_size=50, min_samples=10,
                drift_threshold=0.05, abrupt_threshold=0.15
            )
        return self.drift_estimators[vendor_id][policy_id]
    
    def select_policy(self, vendor, round_num, all_vendors):
        self._try_rabi_init(vendor, all_vendors)
        arms = list(self._get_arms(vendor.vendor_id).values())
        selected, _ = self.strategy.select(arms, round_num)
        return selected.policy_id
    
    def update(self, vendor, policy_id, reward, round_num):
        arms = self._get_arms(vendor.vendor_id)
        arm = arms[policy_id]
        
        estimator = self._get_estimator(vendor.vendor_id, policy_id)
        drift_metrics = estimator.update(reward)
        gamma = drift_metrics.optimal_gamma
        
        retention = 1.0 - gamma
        arm.alpha = max(0.01, 1.0 + retention * (arm.alpha - 1.0))
        arm.beta = max(0.01, 1.0 + retention * (arm.beta - 1.0))
        
        if drift_metrics.drift_type == DriftType.ABRUPT:
            arm.alpha = 1.0 + 0.5 * (arm.alpha - 1.0)
            arm.beta = 1.0 + 0.5 * (arm.beta - 1.0)
        
        arm.alpha += reward
        arm.beta += (1.0 - reward)
        arm.pulls += 1
    
    def reset(self):
        super().reset()
        self.drift_estimators = {}
        self._initialized_vendors = set()

# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def run_single(
    method: MethodRunner,
    scenario: Scenario,
    seed: int,
) -> RunResult:
    """
    Run one method through one scenario with one random seed.
    
    Each round:
    1. Pick a vendor uniformly from active vendors
    2. Method selects a policy
    3. Environment samples reward from true distribution
    4. Method updates with observed reward
    5. Record regret = oracle_reward - actual_reward
    """
    rng = np.random.RandomState(seed)
    # Also seed Python's random for Thompson Sampling which uses random.betavariate
    import random as py_random
    py_random.seed(seed)
    
    method.reset()
    
    rewards = []
    cumulative_regret = []
    oracle_rewards = []
    selected_policies = []
    optimal_policies = []
    running_regret = 0.0
    
    # Pre-apply drift events by building a schedule
    drift_schedule: dict[int, DriftEvent] = {
        de.at_round: de for de in scenario.drift_events
    }
    # Mutable copy of vendor policies (so drift can modify them)
    vendor_policies: dict[str, dict] = {
        v.vendor_id: {pid: cfg for pid, cfg in v.policies.items()}
        for v in scenario.vendors
    }
    
    for t in range(scenario.n_rounds):
        # Apply drift if scheduled
        if t in drift_schedule:
            de = drift_schedule[t]
            vendor_policies[de.vendor_id] = {
                pid: cfg for pid, cfg in de.new_policies.items()
            }
            # Also update the vendor object so oracle is correct
            for v in scenario.vendors:
                if v.vendor_id == de.vendor_id:
                    v.policies = de.new_policies
        
        # Get active vendors
        active = scenario.get_active_vendors(t)
        if not active:
            continue
        
        # Pick a vendor using weights (higher weight = more documents from that vendor)
        weights = np.array([v.weight for v in active])
        weights = weights / weights.sum()
        vendor = active[rng.choice(len(active), p=weights)]
        
        # Method selects policy
        policy_id = method.select_policy(vendor, t, active)
        
        # Environment samples reward from true distribution
        cfg = vendor_policies[vendor.vendor_id][policy_id]
        reward = float(np.clip(rng.normal(cfg.true_mean, cfg.noise_std), 0.0, 1.0))
        
        # Oracle: best policy by true mean for this vendor right now
        best_pid = max(vendor_policies[vendor.vendor_id],
                       key=lambda p: vendor_policies[vendor.vendor_id][p].true_mean)
        oracle_reward = vendor_policies[vendor.vendor_id][best_pid].true_mean

        # Update method with the observed (noisy) reward
        method.update(vendor, policy_id, reward, t)

        # Pseudo-regret: difference in TRUE expected rewards, noise-free on both sides.
        # Standard definition in bandit literature — avoids comparing a noisy sample
        # against a noise-free oracle, which overstates regret.
        chosen_true_mean = vendor_policies[vendor.vendor_id][policy_id].true_mean
        regret = oracle_reward - chosen_true_mean
        running_regret += max(0.0, regret)
        
        rewards.append(reward)
        cumulative_regret.append(running_regret)
        oracle_rewards.append(oracle_reward)
        selected_policies.append(policy_id)
        optimal_policies.append(best_pid)
    
    return RunResult(
        method=method.name,
        scenario=scenario.name,
        seed=seed,
        rewards=rewards,
        cumulative_regret=cumulative_regret,
        oracle_rewards=oracle_rewards,
        selected_policies=selected_policies,
        optimal_policies=optimal_policies,
    )

def run_experiment(
    scenarios: list[Scenario] | None = None,
    n_seeds: int = 30,
    verbose: bool = True,
) -> list[RunResult]:
    """
    Run full experiment: all methods × all scenarios × n_seeds.
    
    Args:
        scenarios: List of scenarios (default: all 4 predefined ones)
        n_seeds: Number of random seeds for statistical significance
        verbose: Print progress
    
    Returns:
        List of RunResult objects
    """
    if scenarios is None:
        scenarios = get_all_scenarios()
    
    all_results: list[RunResult] = []
    
    for scenario in scenarios:
        methods = [
            RandomRunner(scenario.policy_ids),
            EpsilonGreedyRunner(scenario.policy_ids),
            UCB1Runner(scenario.policy_ids),
            ThompsonSamplingRunner(scenario.policy_ids),
            AHMNRABIRunner(scenario.policy_ids),
            AHMNDAAFRunner(scenario.policy_ids),
            AHMNFullRunner(scenario.policy_ids),
        ]
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"Scenario: {scenario.name} ({scenario.n_rounds} rounds)")
            print(f"{'='*70}")
        
        for method in methods:
            seed_results = []
            t0 = time.time()
            
            for seed in range(n_seeds):
                result = run_single(method, scenario, seed)
                seed_results.append(result)
                all_results.append(result)
            
            elapsed = time.time() - t0
            
            if verbose:
                regrets = [r.total_regret for r in seed_results]
                final_rewards = [r.final_avg_reward for r in seed_results]
                accuracies = [r.policy_accuracy for r in seed_results]
                conv_rounds = [r.convergence_round for r in seed_results if r.convergence_round is not None]
                
                conv_str = str(int(np.mean(conv_rounds))) if conv_rounds else "N/A"
                print(f"  {method.name:15s} | "
                      f"Regret: {np.mean(regrets):7.1f} ± {np.std(regrets):5.1f} | "
                      f"Final F1: {np.mean(final_rewards):.3f} ± {np.std(final_rewards):.3f} | "
                      f"Accuracy: {np.mean(accuracies):.3f} | "
                      f"Conv: {conv_str:>5s} | "
                      f"{elapsed:.1f}s")
    
    return all_results

# ═══════════════════════════════════════════════════════════════════════════════
# ABLATION STUDIES
# ═══════════════════════════════════════════════════════════════════════════════

def run_ablation_rabi_temperature(n_seeds: int = 30, verbose: bool = True) -> dict:
    """Ablation: vary RABI temperature τ ∈ {0.1, 0.3, 0.5, 0.7, 1.0, 2.0}."""
    scenario = create_cold_start_scenario()
    # Widen embedding spread so neighbor similarities vary (0.5-0.95 range)
    # This makes temperature meaningfully affect weight distribution
    cluster_map = {}  # vendor_id -> (cluster, within_id)
    for i, v in enumerate(scenario.vendors):
        cid = 1 if "inv" in v.vendor_id else 2
        wid = sum(1 for v2 in scenario.vendors[:i]
                  if (1 if "inv" in v2.vendor_id else 2) == cid)
        v.embedding = _make_cluster_embedding(cid, wid, spread=0.4)
    temperatures = [0.1, 0.3, 0.5, 0.7, 1.0, 2.0]
    results = {}
    
    if verbose:
        print(f"\n{'='*70}")
        print("Ablation: RABI Temperature (tau)")
        print(f"{'='*70}")
    
    for tau in temperatures:
        method = AHMNRABIRunner(scenario.policy_ids, temperature=tau)
        seed_results = [run_single(method, scenario, s) for s in range(n_seeds)]
        
        regrets = [r.total_regret for r in seed_results]
        final_rewards = [r.final_avg_reward for r in seed_results]
        conv = [r.convergence_round for r in seed_results if r.convergence_round is not None]
        
        results[tau] = {
            "regret_mean": float(np.mean(regrets)),
            "regret_std": float(np.std(regrets)),
            "reward_mean": float(np.mean(final_rewards)),
            "reward_std": float(np.std(final_rewards)),
            "convergence_mean": float(np.mean(conv)) if conv else None,
        }
        
        if verbose:
            print(f"  tau={tau:.1f} | Regret: {np.mean(regrets):7.1f} +/- {np.std(regrets):5.1f} | "
                  f"Final F1: {np.mean(final_rewards):.3f} | "
                  f"Conv: {int(np.mean(conv)) if conv else 'N/A'}")
    
    return results

def run_ablation_daaf_window(n_seeds: int = 30, verbose: bool = True) -> dict:
    """Ablation: vary DAAF window size ∈ {10, 20, 30, 50, 75, 100}."""
    scenario = create_drift_scenario()
    window_sizes = [10, 20, 30, 50, 75, 100]
    results = {}
    
    if verbose:
        print(f"\n{'='*70}")
        print("Ablation: DAAF Window Size")
        print(f"{'='*70}")
    
    for ws in window_sizes:
        method = AHMNDAAFRunner(scenario.policy_ids, window_size=ws)
        seed_results = [run_single(method, scenario, s) for s in range(n_seeds)]
        
        regrets = [r.total_regret for r in seed_results]
        final_rewards = [r.final_avg_reward for r in seed_results]
        accuracies = [r.policy_accuracy for r in seed_results]
        
        results[ws] = {
            "regret_mean": float(np.mean(regrets)),
            "regret_std": float(np.std(regrets)),
            "reward_mean": float(np.mean(final_rewards)),
            "reward_std": float(np.std(final_rewards)),
            "accuracy_mean": float(np.mean(accuracies)),
        }
        
        if verbose:
            print(f"  window={ws:3d} | Regret: {np.mean(regrets):7.1f} ± {np.std(regrets):5.1f} | "
                  f"Final F1: {np.mean(final_rewards):.3f} | Acc: {np.mean(accuracies):.3f}")
    
    return results

def run_ablation_similarity_threshold(n_seeds: int = 30, verbose: bool = True) -> dict:
    """Ablation: vary RABI similarity threshold ∈ {0.2, 0.3, 0.4, 0.5, 0.6, 0.8}."""
    scenario = create_cold_start_scenario()
    # Widen embeddings so some neighbors fall below higher thresholds
    for i, v in enumerate(scenario.vendors):
        cid = 1 if "inv" in v.vendor_id else 2
        wid = sum(1 for v2 in scenario.vendors[:i]
                  if (1 if "inv" in v2.vendor_id else 2) == cid)
        v.embedding = _make_cluster_embedding(cid, wid, spread=0.5)
    thresholds = [0.2, 0.3, 0.4, 0.5, 0.6, 0.8]
    results = {}
    
    if verbose:
        print(f"\n{'='*70}")
        print("Ablation: RABI Similarity Threshold")
        print(f"{'='*70}")
    
    for thresh in thresholds:
        method = AHMNRABIRunner(scenario.policy_ids, similarity_threshold=thresh)
        seed_results = [run_single(method, scenario, s) for s in range(n_seeds)]
        
        regrets = [r.total_regret for r in seed_results]
        final_rewards = [r.final_avg_reward for r in seed_results]
        
        results[thresh] = {
            "regret_mean": float(np.mean(regrets)),
            "regret_std": float(np.std(regrets)),
            "reward_mean": float(np.mean(final_rewards)),
            "reward_std": float(np.std(final_rewards)),
        }
        
        if verbose:
            print(f"  threshold={thresh:.1f} | Regret: {np.mean(regrets):7.1f} ± {np.std(regrets):5.1f} | "
                  f"Final F1: {np.mean(final_rewards):.3f}")
    
    return results

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("AHMN Experimental Evaluation Framework")
    print("30 seeds x 7 methods x 4 scenarios")
    print("=" * 70)
    
    t_start = time.time()
    
    # ── Main experiments ──
    results = run_experiment(n_seeds=30)
    
    # ── Ablation studies ──
    abl_temp = run_ablation_rabi_temperature(n_seeds=30)
    abl_window = run_ablation_daaf_window(n_seeds=30)
    abl_thresh = run_ablation_similarity_threshold(n_seeds=30)
    
    elapsed = time.time() - t_start
    
    # ── Save results ──
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    output = {
        "experiment_config": {
            "n_seeds": 30,
            "methods": ["Random", "e-Greedy", "UCB1", "TS (base)",
                        "AHMN-RABI", "AHMN-DAAF", "AHMN-Full"],
            "scenarios": ["stationary", "cold_start", "concept_drift", "combined"],
            "total_time_seconds": round(elapsed, 1),
        },
        "main_results": [r.to_summary() for r in results],
        "ablation_rabi_temperature": {str(k): v for k, v in abl_temp.items()},
        "ablation_daaf_window": {str(k): v for k, v in abl_window.items()},
        "ablation_similarity_threshold": {str(k): v for k, v in abl_thresh.items()},
    }
    
    out_path = os.path.join(output_dir, "experiment_results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    # Save per-round arrays separately for curve plotting (larger file)
    curves_path = os.path.join(output_dir, "experiment_curves.json")
    with open(curves_path, "w") as f:
        json.dump({"main_results": [r.to_full() for r in results]}, f, indent=2)
    
    print(f"\n{'='*70}")
    print(f"Done in {elapsed:.1f}s. Results saved to output/experiment_results.json")
    print(f"Total runs: {len(results)} ({len(results)//30} method-scenario combos × 30 seeds)")
    print(f"{'='*70}")
    
    return output

if __name__ == "__main__":
    main()

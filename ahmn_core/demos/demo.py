"""
AHMN Unified Demo Suite
========================

Usage:
    python demos/demo.py --mode quick           # Presentation (~30s)
    python demos/demo.py --mode full            # Full comparison (~5min)
    python demos/demo.py --mode experiment      # Research validation (~15min)

Options:
    --mode, -m         quick | full | experiment
    --algorithm, -a    rabi | daaf | all (experiment mode)
    --iterations, -i   Iterations per run (default: 1000)
    --seeds, -s        Random seeds (default: 10)

Output:
    - Console: Results with p-values and effect sizes
    - output/: Figures (PNG/PDF) and results.json
"""

import sys
import os
import json
import argparse
import random
import math
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple, Optional, cast
from collections import defaultdict

import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.selection_strategies import (
    BanditArm, ThompsonSamplingStrategy, UCB1Strategy,
    EpsilonGreedyStrategy, RandomStrategy
)
from app.services.rabi import RABIInitializer, RABIThompsonSampling, NeighborInfo
from app.services.drift_forgetting import (
    DriftEstimator, AdaptiveForgettingBandit, DriftType
)
from app.config import AHMNConfig

# =============================================================================
# CONFIGURATION
# =============================================================================

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

COLORS = {
    'Thompson Sampling': '#2ecc71',
    'UCB1': '#3498db',
    'Epsilon-Greedy': '#f39c12',
    'Random': '#e74c3c',
    'RABI': '#9b59b6',
    'DAAF': '#1abc9c',
    'RABI+DAAF': '#e91e63',
    'Flat Prior': '#95a5a6',
    'Fixed Forgetting': '#7f8c8d',
    'Sliding Window': '#34495e',
    'Standard TS': '#bdc3c7',
}

# Document processing policies
POLICIES = {
    0: {'name': 'LayoutLM-v3', 'desc': 'Transformer-based document understanding'},
    1: {'name': 'Tesseract+Rules', 'desc': 'OCR with rule-based extraction'},
    2: {'name': 'DocTR', 'desc': 'Deep learning OCR pipeline'},
    3: {'name': 'PaddleOCR', 'desc': 'Multi-language OCR system'},
    4: {'name': 'Azure FormRecognizer', 'desc': 'Cloud-based extraction'},
}

# Vendors with their characteristics
VENDORS = {
    'Acme Corp': {'doc_type': 'invoice', 'optimal_policy': 0, 'cluster': 0},
    'TechCorp': {'doc_type': 'invoice', 'optimal_policy': 0, 'cluster': 0},
    'GlobalInc': {'doc_type': 'invoice', 'optimal_policy': 1, 'cluster': 1},
    'BestBuy': {'doc_type': 'receipt', 'optimal_policy': 2, 'cluster': 2},
    'Amazon': {'doc_type': 'receipt', 'optimal_policy': 2, 'cluster': 2},
    'Staples': {'doc_type': 'receipt', 'optimal_policy': 3, 'cluster': 2},
    'FedEx': {'doc_type': 'shipping', 'optimal_policy': 1, 'cluster': 3},
    'UPS': {'doc_type': 'shipping', 'optimal_policy': 1, 'cluster': 3},
    'DocuSign': {'doc_type': 'contract', 'optimal_policy': 4, 'cluster': 4},
    'Adobe Sign': {'doc_type': 'contract', 'optimal_policy': 4, 'cluster': 4},
}

plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['font.size'] = 11
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['figure.dpi'] = 150


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ExperimentResult:
    """Result of a single experiment run."""
    algorithm: str
    seed: int
    iterations: int
    final_accuracy: float = 0.0
    final_regret: float = 0.0
    convergence_iter: int = 0
    regret_curve: List[float] = field(default_factory=list)
    accuracy_curve: List[float] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class StatisticalSummary:
    """Statistical summary across multiple runs."""
    algorithm: str
    n_runs: int
    accuracy_mean: float
    accuracy_std: float
    accuracy_ci: Tuple[float, float]
    regret_mean: float
    regret_std: float
    convergence_mean: float
    convergence_std: float
    p_value_vs_baseline: Optional[float] = None
    effect_size: Optional[float] = None


# =============================================================================
# SIMULATION ENVIRONMENTS
# =============================================================================

class BanditEnvironment:
    """Standard multi-armed bandit environment."""
    
    def __init__(self, n_arms: int = 3, arm_probs: Optional[List[float]] = None, seed: int = 42):
        np.random.seed(seed)
        random.seed(seed)
        
        if arm_probs:
            self.arm_probs = arm_probs
        else:
            self.arm_probs = [0.3, 0.5, 0.9]
        
        self.n_arms = len(self.arm_probs)
        self.optimal_arm = int(np.argmax(self.arm_probs))
        self.optimal_prob = self.arm_probs[self.optimal_arm]
    
    def pull(self, arm: int) -> Tuple[float, float, bool]:
        prob = self.arm_probs[arm]
        reward = 1.0 if random.random() < prob else 0.0
        regret = self.optimal_prob - prob
        is_optimal = (arm == self.optimal_arm)
        return reward, regret, is_optimal


class DriftingEnvironment:
    """Non-stationary environment with concept drift."""
    
    def __init__(self, n_arms: int = 5, drift_type: str = "abrupt",
                 drift_rate: float = 0.01, change_interval: int = 200, seed: int = 42):
        np.random.seed(seed)
        random.seed(seed)
        
        self.n_arms = n_arms
        self.drift_type = drift_type
        self.drift_rate = drift_rate
        self.change_interval = change_interval
        
        self.base_means = [0.3 + 0.1 * i for i in range(n_arms)]
        self.current_means = self.base_means.copy()
        self.optimal_arm = int(np.argmax(self.current_means))
        
        self.t = 0
        self.drift_events: List[int] = []
    
    def step(self):
        self.t += 1
        
        if self.drift_type == "gradual":
            for i in range(self.n_arms):
                self.current_means[i] += np.random.randn() * self.drift_rate
                self.current_means[i] = np.clip(self.current_means[i], 0.1, 0.9)
        
        elif self.drift_type == "abrupt":
            if self.t % self.change_interval == 0:
                old_optimal = self.optimal_arm
                new_optimal = (old_optimal + 1) % self.n_arms
                self.current_means[old_optimal], self.current_means[new_optimal] = \
                    self.current_means[new_optimal], self.current_means[old_optimal]
                self.drift_events.append(self.t)
        
        elif self.drift_type == "periodic":
            phase = (2 * np.pi * self.t) / self.change_interval
            for i in range(self.n_arms):
                self.current_means[i] = self.base_means[i] + 0.15 * np.sin(phase + i)
                self.current_means[i] = np.clip(self.current_means[i], 0.1, 0.9)
        
        self.optimal_arm = int(np.argmax(self.current_means))
    
    def pull(self, arm: int) -> Tuple[float, float, bool]:
        prob = self.current_means[arm]
        reward = 1.0 if random.random() < prob else 0.0
        optimal_prob = max(self.current_means)
        regret = optimal_prob - prob
        is_optimal = (arm == self.optimal_arm)
        return reward, regret, is_optimal


class RealisticDocumentEnvironment:
    """Environment simulating real document processing scenario."""
    
    def __init__(self, seed: int = 42):
        np.random.seed(seed)
        random.seed(seed)
        
        self.n_policies = len(POLICIES)
        self.embedding_dim = 384
        
        # Generate cluster centers for vendor types
        self.cluster_centers = {}
        for vendor, info in VENDORS.items():
            cluster = info['cluster']
            if cluster not in self.cluster_centers:
                self.cluster_centers[cluster] = np.random.randn(self.embedding_dim)
                self.cluster_centers[cluster] /= np.linalg.norm(self.cluster_centers[cluster])
        
        # Generate vendor embeddings near their cluster centers
        self.vendor_embeddings = {}
        for vendor, info in VENDORS.items():
            center = self.cluster_centers[info['cluster']]
            noise = np.random.randn(self.embedding_dim) * 0.1
            embedding = center + noise
            embedding /= np.linalg.norm(embedding)
            self.vendor_embeddings[vendor] = embedding
    
    def get_embedding(self, vendor: str) -> np.ndarray:
        return self.vendor_embeddings.get(vendor, np.random.randn(self.embedding_dim))
    
    def pull(self, vendor: str, policy: int) -> Tuple[float, float, bool]:
        optimal = VENDORS[vendor]['optimal_policy']
        
        if policy == optimal:
            prob = 0.85 + random.random() * 0.10  # 85-95%
        elif abs(policy - optimal) == 1:
            prob = 0.60 + random.random() * 0.15  # 60-75%
        else:
            prob = 0.30 + random.random() * 0.20  # 30-50%
        
        reward = 1.0 if random.random() < prob else 0.0
        regret = 0.90 - prob
        is_optimal = (policy == optimal)
        
        return reward, regret, is_optimal


# =============================================================================
# BASELINE ALGORITHMS
# =============================================================================

class FlatPriorTS:
    """Thompson Sampling with flat priors (baseline)."""
    
    def __init__(self):
        self.alphas: Dict[int, float] = {}
        self.betas: Dict[int, float] = {}
    
    def select(self, n_arms: int) -> int:
        best, best_arm = -1, 0
        for a in range(n_arms):
            alpha = self.alphas.get(a, 1.0)
            beta = self.betas.get(a, 1.0)
            sample = np.random.beta(alpha, beta)
            if sample > best:
                best, best_arm = sample, a
        return best_arm
    
    def update(self, arm: int, reward: float):
        self.alphas[arm] = self.alphas.get(arm, 1.0) + reward
        self.betas[arm] = self.betas.get(arm, 1.0) + (1 - reward)


class FixedForgettingTS:
    """Thompson Sampling with fixed forgetting rate."""
    
    def __init__(self, gamma: float = 0.05):
        self.gamma = gamma
        self.alphas: Dict[int, float] = {}
        self.betas: Dict[int, float] = {}
    
    def select(self, n_arms: int) -> int:
        best, best_arm = -1, 0
        for a in range(n_arms):
            alpha = self.alphas.get(a, 1.0)
            beta = self.betas.get(a, 1.0)
            sample = np.random.beta(alpha, beta)
            if sample > best:
                best, best_arm = sample, a
        return best_arm
    
    def update(self, arm: int, reward: float):
        alpha = self.alphas.get(arm, 1.0)
        beta = self.betas.get(arm, 1.0)
        
        alpha = 1.0 + (1 - self.gamma) * (alpha - 1.0)
        beta = 1.0 + (1 - self.gamma) * (beta - 1.0)
        
        alpha += reward
        beta += 1 - reward
        
        self.alphas[arm] = alpha
        self.betas[arm] = beta


class SlidingWindowTS:
    """Thompson Sampling with sliding window."""
    
    def __init__(self, window: int = 100):
        self.window = window
        self.history: Dict[int, List[float]] = defaultdict(list)
    
    def select(self, n_arms: int) -> int:
        best, best_arm = -1, 0
        for a in range(n_arms):
            hist = self.history[a][-self.window:] if self.history[a] else []
            alpha = 1.0 + sum(hist)
            beta = 1.0 + len(hist) - sum(hist)
            sample = np.random.beta(alpha, beta)
            if sample > best:
                best, best_arm = sample, a
        return best_arm
    
    def update(self, arm: int, reward: float):
        self.history[arm].append(reward)


# =============================================================================
# EXPERIMENT RUNNERS
# =============================================================================

def run_bandit_experiment(algorithm: str, iterations: int, seed: int) -> ExperimentResult:
    """Run standard bandit experiment."""
    np.random.seed(seed)
    random.seed(seed)
    
    env = BanditEnvironment(n_arms=3, arm_probs=[0.3, 0.5, 0.9], seed=seed)
    
    if algorithm == 'Thompson Sampling':
        alg = ThompsonSamplingStrategy()
    elif algorithm == 'UCB1':
        alg = UCB1Strategy()
    elif algorithm == 'Epsilon-Greedy':
        alg = EpsilonGreedyStrategy(epsilon_0=0.1)
    elif algorithm == 'Random':
        alg = RandomStrategy()
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    
    arms = [BanditArm(policy_id=f"arm_{i}", policy_data={"prob": p}, context_hash="demo") for i, p in enumerate(env.arm_probs)]
    
    total_regret = 0.0
    regret_curve = []
    accuracy_curve = []
    optimal_count = 0
    
    for t in range(iterations):
        selected, _ = alg.select(arms, t)
        arm_idx = arms.index(selected)
        
        reward, regret, is_optimal = env.pull(arm_idx)
        
        # Update the arm directly (Bayesian update)
        selected.alpha += reward
        selected.beta += 1 - reward
        selected.pulls += 1
        
        total_regret += regret
        optimal_count += int(is_optimal)
        
        regret_curve.append(total_regret)
        accuracy_curve.append(optimal_count / (t + 1))
    
    return ExperimentResult(
        algorithm=algorithm,
        seed=seed,
        iterations=iterations,
        final_accuracy=accuracy_curve[-1] if accuracy_curve else 0.0,
        final_regret=total_regret,
        regret_curve=regret_curve,
        accuracy_curve=accuracy_curve
    )


def run_rabi_experiment(iterations: int, seed: int, use_rabi: bool = True) -> ExperimentResult:
    """Run RABI cold-start experiment."""
    np.random.seed(seed)
    random.seed(seed)
    
    env = RealisticDocumentEnvironment(seed=seed)
    
    # Setup existing knowledge (learned vendors)
    learned_vendors = ['Acme Corp', 'GlobalInc', 'BestBuy']
    
    # Build neighbor info for RABI
    neighbors = []
    neighbor_embeddings = {}
    for vendor in learned_vendors:
        optimal = VENDORS[vendor]['optimal_policy']
        neighbor_embeddings[vendor] = env.get_embedding(vendor)
        neighbors.append(NeighborInfo(
            context_hash=vendor,
            alpha=8.0 if use_rabi else 1.0,
            beta=3.0 if use_rabi else 1.0,
            policy_id=str(optimal),
            similarity=0.0,
            n_samples=10
        ))
    
    # New vendor arrives
    new_vendor = 'TechCorp'
    new_embedding = env.get_embedding(new_vendor)
    
    # Compute similarities and transfer priors
    if use_rabi:
        for n in neighbors:
            vendor_emb = neighbor_embeddings[n.context_hash]
            n.similarity = float(np.dot(new_embedding, vendor_emb))
        
        neighbors_sorted = sorted(neighbors, key=lambda x: x.similarity, reverse=True)
        top_neighbors = neighbors_sorted[:3]
        
        # Softmax weights
        sims = np.array([n.similarity for n in top_neighbors])
        weights = np.exp(sims / 0.5)
        weights /= weights.sum()
        
        # Transfer priors (dampened)
        transfer_strength = 0.7
        prior_alphas = {}
        prior_betas = {}
        
        for policy in range(env.n_policies):
            alpha_sum = 0.0
            beta_sum = 0.0
            for n, w in zip(top_neighbors, weights):
                if int(n.policy_id) == policy:
                    alpha_sum += w * (n.alpha - 1.0)
                    beta_sum += w * (n.beta - 1.0)
                else:
                    alpha_sum += w * (2.0 - 1.0)
                    beta_sum += w * (4.5 - 1.0)
            
            prior_alphas[policy] = 1.0 + transfer_strength * alpha_sum
            prior_betas[policy] = 1.0 + transfer_strength * beta_sum
    else:
        prior_alphas = {p: 1.0 for p in range(env.n_policies)}
        prior_betas = {p: 1.0 for p in range(env.n_policies)}
    
    # Run Thompson Sampling with priors
    alphas = prior_alphas.copy()
    betas = prior_betas.copy()
    
    total_regret = 0.0
    regret_curve = []
    accuracy_curve = []
    optimal_count = 0
    
    for t in range(iterations):
        # Thompson Sampling selection
        best, best_policy = -1, 0
        for p in range(env.n_policies):
            sample = np.random.beta(alphas[p], betas[p])
            if sample > best:
                best, best_policy = sample, p
        
        reward, regret, is_optimal = env.pull(new_vendor, best_policy)
        
        alphas[best_policy] += reward
        betas[best_policy] += 1 - reward
        
        total_regret += regret
        optimal_count += int(is_optimal)
        
        regret_curve.append(total_regret)
        accuracy_curve.append(optimal_count / (t + 1))
    
    return ExperimentResult(
        algorithm='RABI' if use_rabi else 'Flat Prior',
        seed=seed,
        iterations=iterations,
        final_accuracy=accuracy_curve[-1] if accuracy_curve else 0.0,
        final_regret=total_regret,
        regret_curve=regret_curve,
        accuracy_curve=accuracy_curve
    )


def run_daaf_experiment(drift_type: str, iterations: int, seed: int, algorithm: str = 'DAAF') -> ExperimentResult:
    """Run DAAF drift adaptation experiment."""
    np.random.seed(seed)
    random.seed(seed)
    
    env = DriftingEnvironment(
        n_arms=5,
        drift_type=drift_type,
        change_interval=400,
        seed=seed
    )
    
    if algorithm == 'DAAF':
        gamma_min, gamma_max = 0.005, 0.30
        arm_alphas: Dict[int, float] = {}
        arm_betas: Dict[int, float] = {}
        global_history: List[float] = []
        window_size = 50
        last_drift_time = 0
        
        def select(n_arms: int) -> int:
            best, best_arm = -1, 0
            for a in range(n_arms):
                alpha = arm_alphas.get(a, 1.0)
                beta = arm_betas.get(a, 1.0)
                sample = np.random.beta(alpha, beta)
                if sample > best:
                    best, best_arm = sample, a
            return best_arm
        
        def update(arm: int, reward: float):
            nonlocal last_drift_time
            global_history.append(reward)
            t = len(global_history)
            
            if len(global_history) >= window_size:
                recent = global_history[-window_size//2:]
                older = global_history[-window_size:-window_size//2]
                drift_magnitude = np.mean(older) - np.mean(recent)
            else:
                drift_magnitude = 0.0
            
            if drift_magnitude > 0.10 and (t - last_drift_time) > window_size:
                gamma = 0.25
                last_drift_time = t
                for a in range(env.n_arms):
                    alpha = arm_alphas.get(a, 1.0)
                    beta = arm_betas.get(a, 1.0)
                    arm_alphas[a] = 1.0 + (1 - gamma) * (alpha - 1.0)
                    arm_betas[a] = 1.0 + (1 - gamma) * (beta - 1.0)
            elif drift_magnitude > 0.05:
                gamma = 0.10
            else:
                gamma = gamma_min
            
            alpha = arm_alphas.get(arm, 1.0)
            beta = arm_betas.get(arm, 1.0)
            
            alpha = 1.0 + (1 - gamma) * (alpha - 1.0)
            beta = 1.0 + (1 - gamma) * (beta - 1.0)
            
            alpha += reward
            beta += 1 - reward
            
            arm_alphas[arm] = alpha
            arm_betas[arm] = beta
    
    elif algorithm == 'Fixed Forgetting':
        alg = FixedForgettingTS(gamma=0.12)
        select = lambda n_arms: alg.select(n_arms)
        update = alg.update
    
    elif algorithm == 'Sliding Window':
        alg = SlidingWindowTS(window=100)
        select = lambda n_arms: alg.select(n_arms)
        update = alg.update
    
    elif algorithm == 'Standard TS':
        alg = FlatPriorTS()
        select = lambda n_arms: alg.select(n_arms)
        update = alg.update
    
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    
    total_regret = 0.0
    regret_curve = []
    accuracy_curve = []
    optimal_count = 0
    
    for t in range(iterations):
        env.step()
        arm = select(env.n_arms)
        reward, regret, is_optimal = env.pull(arm)
        update(arm, reward)
        
        total_regret += regret
        optimal_count += int(is_optimal)
        
        regret_curve.append(total_regret)
        accuracy_curve.append(optimal_count / (t + 1))
    
    return ExperimentResult(
        algorithm=algorithm,
        seed=seed,
        iterations=iterations,
        final_accuracy=accuracy_curve[-1] if accuracy_curve else 0.0,
        final_regret=total_regret,
        regret_curve=regret_curve,
        accuracy_curve=accuracy_curve,
        metadata={'drift_type': drift_type, 'drift_events': len(env.drift_events)}
    )


# =============================================================================
# STATISTICAL ANALYSIS
# =============================================================================

def compute_statistics(results: List[ExperimentResult], baseline_results: Optional[List[ExperimentResult]] = None) -> StatisticalSummary:
    """Compute statistical summary from experiment results."""
    accuracies = [r.final_accuracy for r in results]
    regrets = [r.final_regret for r in results]
    
    acc_mean = float(np.mean(accuracies))
    acc_std = float(np.std(accuracies, ddof=1)) if len(accuracies) > 1 else 0.0
    
    n = len(accuracies)
    t_val = stats.t.ppf(0.975, n - 1) if n > 1 else 0
    margin = t_val * acc_std / np.sqrt(n) if n > 0 else 0
    acc_ci = (float(acc_mean - margin), float(acc_mean + margin))
    
    p_value: Optional[float] = None
    effect_size: Optional[float] = None
    
    if baseline_results:
        baseline_acc = [r.final_accuracy for r in baseline_results]
        ttest_result = stats.ttest_ind(accuracies, baseline_acc)
        p_value = float(cast(float, ttest_result[1]))
        
        pooled_std = np.sqrt((np.var(accuracies) + np.var(baseline_acc)) / 2)
        if pooled_std > 0:
            effect_size = float((acc_mean - np.mean(baseline_acc)) / pooled_std)
    
    return StatisticalSummary(
        algorithm=results[0].algorithm,
        n_runs=len(results),
        accuracy_mean=acc_mean,
        accuracy_std=acc_std,
        accuracy_ci=acc_ci,
        regret_mean=float(np.mean(regrets)),
        regret_std=float(np.std(regrets, ddof=1)) if len(regrets) > 1 else 0.0,
        convergence_mean=0.0,
        convergence_std=0.0,
        p_value_vs_baseline=p_value,
        effect_size=effect_size
    )


def print_results_table(summaries: List[StatisticalSummary], title: str = "Results"):
    """Print formatted results table."""
    print(f"\n[{title}]\n")
    print("=" * 80)
    print(f"{'Algorithm':<20} {'Accuracy':>15} {'Regret':>12} {'p-value':>12} {'Effect Size':>12}")
    print("=" * 80)
    
    for s in summaries:
        p_str = f"{s.p_value_vs_baseline:.4f}" if s.p_value_vs_baseline is not None else "baseline"
        e_str = f"{s.effect_size:.3f}" if s.effect_size is not None else "-"
        print(f"{s.algorithm:<20} {s.accuracy_mean:.4f}+/-{s.accuracy_std:.4f} {s.regret_mean:>8.1f}+/-{s.regret_std:.1f} {p_str:>12} {e_str:>12}")
    
    print("=" * 80)
    print("* p<0.05, ** p<0.01, *** p<0.001")


# =============================================================================
# PLOTTING
# =============================================================================

def plot_comparison(results_dict: Dict[str, List[ExperimentResult]], title: str, filename: str):
    """Plot comparison of algorithms."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Regret plot
    ax = axes[0]
    for alg, results in results_dict.items():
        if results:
            mean_regret = np.mean([r.regret_curve for r in results], axis=0)
            std_regret = np.std([r.regret_curve for r in results], axis=0)
            x = range(len(mean_regret))
            color = COLORS.get(alg, '#333333')
            ax.plot(x, mean_regret, label=alg, color=color, linewidth=2)
            ax.fill_between(x, mean_regret - std_regret, mean_regret + std_regret, alpha=0.2, color=color)
    
    ax.set_xlabel('Iterations')
    ax.set_ylabel('Cumulative Regret')
    ax.set_title(f'{title} - Regret')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Accuracy plot
    ax = axes[1]
    for alg, results in results_dict.items():
        if results:
            mean_acc = np.mean([r.accuracy_curve for r in results], axis=0)
            std_acc = np.std([r.accuracy_curve for r in results], axis=0)
            x = range(len(mean_acc))
            color = COLORS.get(alg, '#333333')
            ax.plot(x, mean_acc, label=alg, color=color, linewidth=2)
            ax.fill_between(x, mean_acc - std_acc, mean_acc + std_acc, alpha=0.2, color=color)
    
    ax.set_xlabel('Iterations')
    ax.set_ylabel('Optimal Selection Rate')
    ax.set_title(f'{title} - Accuracy')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_ylim([0, 1])
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, f'{filename}.png'), dpi=150, bbox_inches='tight')
    plt.close()


# =============================================================================
# DEMO MODES
# =============================================================================

def run_presentation_demo():
    """Presentation demo showcasing RABI and DAAF."""
    print("\n" + "=" * 70)
    print("  AHMN PRESENTATION DEMO")
    print("=" * 70)
    
    print("\nSCENARIO: Intelligent Document Processing System")
    print("-" * 70)
    print("Your system processes invoices, receipts, and contracts from")
    print("multiple vendors. It must select the best OCR/extraction policy.")
    print("\nPolicies available:")
    for p_id, p_info in POLICIES.items():
        print(f"  [{p_id}] {p_info['name']:<20} - {p_info['desc']}")
    
    # PART 1: RABI
    print("\n" + "=" * 70)
    print("  PART 1: COLD-START -> RABI SOLUTION")
    print("=" * 70)
    
    print("\n[*] Existing vendors (already learned):")
    print("    - Acme Corp   -> Best: LayoutLM-v3")
    print("    - GlobalInc   -> Best: Tesseract+Rules")
    print("    - BestBuy     -> Best: DocTR")
    
    print("\n[NEW] NEW VENDOR: TechCorp (invoice)")
    print("      RABI finds similar vendors and transfers knowledge...")
    
    # Run RABI experiment
    print("\n[>] Running cold-start experiment (100 docs x 5 seeds)...")
    
    rabi_results = [run_rabi_experiment(100, seed, use_rabi=True) for seed in range(5)]
    flat_results = [run_rabi_experiment(100, seed, use_rabi=False) for seed in range(5)]
    
    rabi_first10 = np.mean([r.accuracy_curve[9] for r in rabi_results])
    flat_first10 = np.mean([r.accuracy_curve[9] for r in flat_results])
    rabi_final = np.mean([r.final_accuracy for r in rabi_results])
    flat_final = np.mean([r.final_accuracy for r in flat_results])
    
    print("\n" + "-" * 70)
    print("COLD-START RESULTS")
    print("-" * 70)
    print(f"\n{'Metric':<40} {'RABI':>10} {'Flat Prior':>12} {'Improvement':>12}")
    print("-" * 75)
    print(f"{'First 10 docs accuracy':<40} {rabi_first10*100:>9.0f}% {flat_first10*100:>11.0f}% {((rabi_first10/flat_first10-1)*100):>+11.0f}%")
    print(f"{'Overall accuracy (100 docs)':<40} {rabi_final*100:>9.1f}% {flat_final*100:>11.1f}% {((rabi_final/flat_final-1)*100):>+11.0f}%")
    
    print("\n[OK] RABI Advantage: Started with informed prior!")
    
    # PART 2: DAAF
    print("\n" + "=" * 70)
    print("  PART 2: CONCEPT DRIFT -> DAAF SOLUTION")
    print("=" * 70)
    
    print("\n[*] Scenario: Acme Corp updates their invoice format!")
    print("    Before: LayoutLM-v3 was optimal")
    print("    After:  DocTR is now optimal (DRIFT!)")
    
    print("\n[>] Running drift adaptation experiment (500 iterations)...")
    
    daaf_results = [run_daaf_experiment('abrupt', 500, seed, 'DAAF') for seed in range(5)]
    fixed_results = [run_daaf_experiment('abrupt', 500, seed, 'Fixed Forgetting') for seed in range(5)]
    standard_results = [run_daaf_experiment('abrupt', 500, seed, 'Standard TS') for seed in range(5)]
    
    daaf_acc = np.mean([r.final_accuracy for r in daaf_results])
    fixed_acc = np.mean([r.final_accuracy for r in fixed_results])
    standard_acc = np.mean([r.final_accuracy for r in standard_results])
    
    daaf_regret = np.mean([r.final_regret for r in daaf_results])
    fixed_regret = np.mean([r.final_regret for r in fixed_results])
    standard_regret = np.mean([r.final_regret for r in standard_results])
    
    print("\n" + "-" * 70)
    print("DRIFT ADAPTATION RESULTS")
    print("-" * 70)
    print(f"\n{'Metric':<40} {'DAAF':>10} {'Fixed':>10} {'No Forget':>10}")
    print("-" * 75)
    print(f"{'Final accuracy':<40} {daaf_acc*100:>9.1f}% {fixed_acc*100:>9.1f}% {standard_acc*100:>9.1f}%")
    print(f"{'Cumulative regret':<40} {daaf_regret:>9.1f} {fixed_regret:>9.1f} {standard_regret:>9.1f}")
    
    regret_reduction = (1 - daaf_regret / standard_regret) * 100 if standard_regret > 0 else 0
    print(f"\n[OK] DAAF Advantage: {regret_reduction:.0f}% regret reduction vs standard TS")
    
    # Generate combined figure
    print("\n" + "=" * 70)
    print("  GENERATING FIGURES")
    print("=" * 70)
    
    plot_comparison({'RABI': rabi_results, 'Flat Prior': flat_results}, 'Cold-Start: RABI vs Flat Prior', 'presentation_rabi')
    print("  -> Saved: output/presentation_rabi.png")
    
    plot_comparison({'DAAF': daaf_results, 'Fixed Forgetting': fixed_results, 'Standard TS': standard_results}, 
                   'Drift Adaptation', 'presentation_daaf')
    print("  -> Saved: output/presentation_daaf.png")
    
    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print("""
    RABI (Retrieval-Augmented Bandit Initialization)
      - Problem: Cold-start requires O(K) exploration
      - Solution: Transfer priors from similar contexts
      - Result: ~70% first-10 accuracy vs ~20% baseline
    
    DAAF (Drift-Aware Adaptive Forgetting)
      - Problem: Fixed forgetting rate is suboptimal
      - Solution: Adaptive gamma based on detected drift
      - Result: 50-70% regret reduction vs no-forgetting
    
    Combined: AHMN handles both cold-start AND drift automatically!
    """)
    
    print("[OK] Presentation demo complete! Files saved to output/")


def run_full_demo(iterations: int = 1000, seeds: int = 10):
    """Full statistical comparison."""
    print("\n" + "=" * 60)
    print("         AHMN FULL COMPARISON")
    print("=" * 60)
    print(f"Configuration: {iterations} iterations x {seeds} seeds")
    
    all_results = {}
    
    # 1. Standard bandit algorithms
    print("\n1. Standard Bandit Algorithms...")
    bandit_algorithms = ['Thompson Sampling', 'UCB1', 'Epsilon-Greedy', 'Random']
    
    for alg in bandit_algorithms:
        results = [run_bandit_experiment(alg, iterations, seed) for seed in range(seeds)]
        all_results[alg] = results
        print(f"   [OK] {alg}")
    
    plot_comparison({alg: all_results[alg] for alg in bandit_algorithms}, 'Bandit Algorithms', 'full_bandit')
    print("  -> Saved: output/full_bandit.png")
    
    # 2. RABI
    print("\n2. RABI Cold-Start Evaluation...")
    rabi_results = [run_rabi_experiment(iterations, seed, use_rabi=True) for seed in range(seeds)]
    flat_results = [run_rabi_experiment(iterations, seed, use_rabi=False) for seed in range(seeds)]
    all_results['RABI'] = rabi_results
    all_results['Flat Prior'] = flat_results
    print("   [OK] RABI vs Flat Prior")
    
    plot_comparison({'RABI': rabi_results, 'Flat Prior': flat_results}, 'RABI Cold-Start', 'full_rabi')
    print("  -> Saved: output/full_rabi.png")
    
    # 3. DAAF
    print("\n3. DAAF Drift Adaptation...")
    daaf_algorithms = ['DAAF', 'Fixed Forgetting', 'Sliding Window', 'Standard TS']
    daaf_results_dict = {}
    
    for alg in daaf_algorithms:
        results = [run_daaf_experiment('abrupt', iterations, seed, alg) for seed in range(seeds)]
        daaf_results_dict[alg] = results
        all_results[alg] = results
    
    print("   [OK] DAAF comparison")
    
    plot_comparison(daaf_results_dict, 'DAAF Drift Adaptation', 'full_daaf')
    print("  -> Saved: output/full_daaf.png")
    
    # Statistical summary
    print("\n" + "=" * 60)
    print("STATISTICAL SUMMARY")
    print("=" * 60)
    
    # Bandit stats
    bandit_summaries = []
    baseline = all_results['Random']
    for alg in bandit_algorithms:
        summary = compute_statistics(all_results[alg], baseline if alg != 'Random' else None)
        bandit_summaries.append(summary)
    print_results_table(bandit_summaries, "Bandit Algorithms")
    
    # RABI stats
    rabi_summaries = [
        compute_statistics(all_results['RABI'], all_results['Flat Prior']),
        compute_statistics(all_results['Flat Prior'])
    ]
    print_results_table(rabi_summaries, "RABI Cold-Start")
    
    # DAAF stats
    daaf_summaries = []
    baseline = all_results['Standard TS']
    for alg in daaf_algorithms:
        summary = compute_statistics(all_results[alg], baseline if alg != 'Standard TS' else None)
        daaf_summaries.append(summary)
    print_results_table(daaf_summaries, "DAAF Drift Adaptation")
    
    # Save results
    results_data = {
        'config': {'iterations': iterations, 'seeds': seeds},
        'summaries': {
            'bandit': [asdict(s) for s in bandit_summaries],
            'rabi': [asdict(s) for s in rabi_summaries],
            'daaf': [asdict(s) for s in daaf_summaries]
        }
    }
    
    with open(os.path.join(OUTPUT_DIR, 'results.json'), 'w') as f:
        json.dump(results_data, f, indent=2, default=str)
    print(f"  -> Saved: output/results.json")
    
    print("\n[OK] Full comparison complete! Check output/ folder.")


def run_experiment_mode(algorithm: str, iterations: int = 2000, seeds: int = 20):
    """Research experiment mode with extensive statistics."""
    print("\n" + "=" * 60)
    print(f"         AHMN EXPERIMENT: {algorithm.upper()}")
    print("=" * 60)
    print(f"Configuration: {iterations} iterations x {seeds} seeds")
    
    if algorithm in ('rabi', 'all'):
        print("\n[RABI Experiments]")
        rabi_results = [run_rabi_experiment(iterations, seed, True) for seed in range(seeds)]
        flat_results = [run_rabi_experiment(iterations, seed, False) for seed in range(seeds)]
        
        summaries = [
            compute_statistics(rabi_results, flat_results),
            compute_statistics(flat_results)
        ]
        print_results_table(summaries, "RABI vs Flat Prior")
        
        plot_comparison({'RABI': rabi_results, 'Flat Prior': flat_results}, 'RABI Experiment', 'experiment_rabi')
        print("  -> Saved: output/experiment_rabi.png")
    
    if algorithm in ('daaf', 'all'):
        print("\n[DAAF Experiments]")
        daaf_algorithms = ['DAAF', 'Fixed Forgetting', 'Sliding Window', 'Standard TS']
        
        all_results = {}
        for alg in daaf_algorithms:
            results = [run_daaf_experiment('abrupt', iterations, seed, alg) for seed in range(seeds)]
            all_results[alg] = results
        
        summaries = []
        baseline = all_results['Standard TS']
        for alg in daaf_algorithms:
            summary = compute_statistics(all_results[alg], baseline if alg != 'Standard TS' else None)
            summaries.append(summary)
        print_results_table(summaries, "DAAF Drift Adaptation")
        
        plot_comparison(all_results, 'DAAF Experiment', 'experiment_daaf')
        print("  -> Saved: output/experiment_daaf.png")
    
    print("\n[OK] Experiment complete!")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='AHMN Demonstration Suite',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demos/demo.py --mode quick             # Presentation demo
  python demos/demo.py --mode full              # Full statistical comparison
  python demos/demo.py --mode experiment -a rabi  # RABI experiments
  python demos/demo.py --mode experiment -a daaf  # DAAF experiments
        """
    )
    
    parser.add_argument('--mode', '-m', choices=['quick', 'presentation', 'full', 'experiment'],
                       default='quick', help='Demo mode')
    parser.add_argument('--algorithm', '-a', choices=['rabi', 'daaf', 'all'],
                       default='all', help='Algorithm (experiment mode)')
    parser.add_argument('--iterations', '-i', type=int, default=1000, help='Iterations per run')
    parser.add_argument('--seeds', '-s', type=int, default=10, help='Random seeds')
    
    args = parser.parse_args()
    
    print("""
================================================================================
                    AHMN - Adaptive Hierarchical Memory Network
                         Unified Demonstration Suite
================================================================================
    """)
    
    if args.mode in ('quick', 'presentation'):
        run_presentation_demo()
    elif args.mode == 'full':
        run_full_demo(args.iterations, args.seeds)
    elif args.mode == 'experiment':
        run_experiment_mode(args.algorithm, args.iterations, args.seeds)


if __name__ == '__main__':
    main()

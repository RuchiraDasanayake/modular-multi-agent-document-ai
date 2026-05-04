"""
Drift-Aware Adaptive Forgetting (DAAF) - Production Ready

A principled approach to non-stationary bandits that dynamically adjusts the
forgetting rate based on detected environmental drift.

Mathematical Foundation:
━━━━━━━━━━━━━━━━━━━━━━━━━

The key insight is to SEPARATE noise from drift:
- Noise (σ²): Inherent variance in Bernoulli rewards (within-window variance)
- Drift (Δ): Actual change in underlying mean (between-window shift)

Optimal Forgetting Rate — Bias-Variance Decomposition:
───────────────────────────────────────────────────────
The per-round regret of a Beta-Bernoulli bandit under drift decomposes into
two competing costs that depend on the forgetting rate γ ∈ (0, 1]:

  C_bias(γ)     = Δ² / γ
      Slow forgetting (small γ) keeps a long effective window n_eff = 1/γ.
      Stale evidence biases the posterior, costing Δ² per effective sample.

  C_variance(γ) = γ · ln(t)
      Fast forgetting (large γ) shrinks n_eff. Fewer effective samples
      increase estimation variance, bounded by the Hoeffding radius √(ln(t)/n_eff)
      squared and integrated over the horizon, which scales as γ·ln(t).

Minimising the total cost C(γ) = Δ²/γ + γ·ln(t) over γ:

    dC/dγ = -Δ²/γ² + ln(t) = 0
    γ²     = Δ² / ln(t)
    γ*     = Δ / √(ln(t))  =  √(Δ² / ln(t))     ... (bias-variance optimal)

Interpretation:
- Larger drift Δ → higher γ* → more aggressive forgetting (tracks change faster)
- More data t  → lower  γ* → gentler forgetting (longer effective window affordable)
- Noise σ² does NOT appear — noise affects C_variance only through the Hoeffding
  bound constant, which drops out of the optimisation. This is why DAAF is immune
  to noise-induced forgetting while remaining responsive to true mean shift.

Forgetting application (exponential decay of pseudocounts):
    α_new = 1 + (1 − γ) · (α_old − 1)
    β_new = 1 + (1 − γ) · (β_old − 1)

Author: AHMN Research Team
"""

import math
import numpy as np

from dataclasses import dataclass
from collections import deque
from enum import Enum

class DriftType(Enum):
    """Classification of detected drift."""
    NONE = "none"
    GRADUAL = "gradual"
    ABRUPT = "abrupt"

@dataclass
class DriftMetrics:
    """
    Metrics from drift detection.

    Key distinction:
    - drift_magnitude: statistically validated mean shift (0 when not significant)
    - raw_delta:       raw |μ_recent - μ_older| before significance test
    - noise_variance:  within-window variance (NOT drift)
    - z_score:         Welch z-statistic — how many SEs apart the two window means are
    """
    drift_magnitude: float      # Δ — validated mean shift used for γ* (0 if not significant)
    noise_variance: float       # σ² — inherent reward variance (NOT drift)
    optimal_gamma: float        # γ* — optimal forgetting rate
    is_drifting: bool           # True only when z-score clears significance threshold
    drift_type: DriftType       # Classification (requires both magnitude AND significance)
    confidence: float           # Confidence in estimate (0-1)
    trend_direction: float      # +1 improving, -1 degrading, 0 stable
    effective_horizon: int      # Estimated samples until drift invalidates
    z_score: float = 0.0        # Welch z-statistic for the two-window mean comparison
    raw_delta: float = 0.0      # Raw |μ_recent - μ_older| before significance filter

class DriftEstimator:
    """
    Principled online drift estimator.
    
    Key Design: SEPARATE drift from noise
    ─────────────────────────────────────
    - Noise σ² = Var(rewards within window) → inherent, ignore
    - Drift Δ = |mean(recent) - mean(older)| → actual shift, use for γ*
    """
    
    def __init__(
        self,
        window_size: int = 50,
        min_samples: int = 10,
        drift_threshold: float = 0.05,
        abrupt_threshold: float = 0.15
    ):
        self.window_size = window_size
        self.min_samples = min_samples
        self.drift_threshold = drift_threshold
        self.abrupt_threshold = abrupt_threshold
        
        # Two sliding windows for comparison
        self.recent_window: deque = deque(maxlen=window_size)
        self.older_window: deque = deque(maxlen=window_size)
        
        # Running statistics for efficiency
        self.total_samples = 0
        self._recent_sum = 0.0
        self._recent_sq_sum = 0.0
        self._older_sum = 0.0
        self._older_sq_sum = 0.0
        
    def update(self, reward: float) -> DriftMetrics:
        """Update with new observation and compute drift metrics."""
        reward = float(np.clip(reward, 0.0, 1.0))
        self.total_samples += 1
        
        # Shift oldest from recent to older window
        if len(self.recent_window) == self.window_size:
            shifted = self.recent_window[0]
            # Subtract the element that the deque will auto-evict on append
            if len(self.older_window) == self.window_size:
                evicted = self.older_window[0]
                self._older_sum -= evicted
                self._older_sq_sum -= evicted ** 2
            self.older_window.append(shifted)
            self._older_sum += shifted
            self._older_sq_sum += shifted ** 2
        
        # Update recent window stats
        if len(self.recent_window) == self.window_size:
            removed = self.recent_window[0]
            self._recent_sum -= removed
            self._recent_sq_sum -= removed ** 2
        
        self.recent_window.append(reward)
        self._recent_sum += reward
        self._recent_sq_sum += reward ** 2
        
        return self._compute_metrics()
    
    def _compute_metrics(self) -> DriftMetrics:
        """Compute drift metrics with proper noise/drift separation."""
        n_recent = len(self.recent_window)
        n_older = len(self.older_window)
        
        # Not enough data
        if n_recent < self.min_samples:
            return DriftMetrics(
                drift_magnitude=0.0,
                noise_variance=0.25,
                optimal_gamma=0.01,
                is_drifting=False,
                drift_type=DriftType.NONE,
                confidence=0.0,
                trend_direction=0.0,
                effective_horizon=max(1, self.total_samples)
            )
        
        # Window statistics
        recent_mean = self._recent_sum / n_recent
        
        # Within-window variance (noise σ²) — NOT drift, computed from recent window
        if n_recent > 1:
            noise_var = max(0.0, (self._recent_sq_sum / n_recent) - recent_mean ** 2)
        else:
            noise_var = 0.25

        # Between-window drift detection via Welch z-test
        # ─────────────────────────────────────────────────
        # Raw mean difference is a biased estimate of drift when n is small:
        # even with zero true drift, sampling noise produces |μ̂_recent - μ̂_older| > 0.
        # We use a two-sample z-test to reject the null (no drift) before acting.
        #
        # SE² = Var(μ̂_recent - μ̂_older) = σ²_recent/n_recent + σ²_older/n_older
        # z   = raw_delta / SE
        # Thresholds: z ≥ 2.0 → gradual (p < 0.05), z ≥ 3.0 → abrupt (p < 0.003)
        z_score = 0.0
        raw_delta = 0.0
        drift_magnitude = 0.0
        trend = 0.0

        if n_older >= self.min_samples:
            older_mean = self._older_sum / n_older
            var_older = max(0.0, (self._older_sq_sum / n_older) - older_mean ** 2)

            raw_delta = abs(recent_mean - older_mean)
            trend = 1.0 if recent_mean > older_mean else (-1.0 if recent_mean < older_mean else 0.0)

            se = math.sqrt(noise_var / n_recent + var_older / n_older)
            z_score = raw_delta / max(se, 1e-9)

        # Classify: require BOTH statistical significance AND minimum magnitude.
        # This prevents noise-induced false positives on stable reward streams.
        if z_score >= 3.0 and raw_delta >= self.abrupt_threshold:
            drift_type = DriftType.ABRUPT
            drift_magnitude = raw_delta      # statistically confirmed — use for γ*
        elif z_score >= 2.0 and raw_delta >= self.drift_threshold:
            drift_type = DriftType.GRADUAL
            drift_magnitude = raw_delta      # statistically confirmed — use for γ*
        else:
            drift_type = DriftType.NONE
            drift_magnitude = 0.0            # not significant — suppress forgetting
        
        is_drifting = drift_type != DriftType.NONE
        confidence = min(1.0, (n_recent + n_older) / (2 * self.window_size))
        
        # ═══════════════════════════════════════════════════════════════
        # OPTIMAL FORGETTING RATE — bias-variance minimisation
        #
        # C(γ) = Δ²/γ  +  γ·ln(t)
        # dC/dγ = 0  →  γ* = Δ / √(ln(t))
        #
        # C_bias    = Δ²/γ      : cost of slow forgetting (stale posterior)
        # C_variance = γ·ln(t)  : cost of fast forgetting (high variance)
        # Noise σ² cancels out — only true mean shift Δ drives forgetting.
        # ═══════════════════════════════════════════════════════════════
        if self.total_samples > 1 and drift_magnitude > 0:
            log_t = max(1.0, math.log(self.total_samples))
            bias_cost = drift_magnitude ** 2          # C_bias  ∝ Δ²/γ  → numerator
            variance_cost = log_t                     # C_var   ∝ γ·ln(t) → denominator
            gamma_star = math.sqrt(bias_cost / variance_cost)
        else:
            gamma_star = 0.001
        
        # Bound to [0.001, 0.3]
        gamma_star = max(0.001, min(0.3, gamma_star))
        
        # Boost for abrupt drift
        if drift_type == DriftType.ABRUPT:
            gamma_star = min(0.5, gamma_star * 2.0)
        
        # Effective horizon
        effective_horizon = int(1.0 / max(0.01, drift_magnitude)) if drift_magnitude > 0.01 else self.total_samples
        
        return DriftMetrics(
            drift_magnitude=drift_magnitude,
            noise_variance=noise_var,
            optimal_gamma=gamma_star,
            is_drifting=is_drifting,
            drift_type=drift_type,
            confidence=confidence,
            trend_direction=trend,
            effective_horizon=max(1, effective_horizon),
            z_score=z_score,
            raw_delta=raw_delta,
        )
    
    def reset(self):
        """Reset estimator (call after abrupt changepoint)."""
        self.recent_window.clear()
        self.older_window.clear()
        self.total_samples = 0
        self._recent_sum = 0.0
        self._recent_sq_sum = 0.0
        self._older_sum = 0.0
        self._older_sq_sum = 0.0

class AdaptiveForgettingBandit:
    """
    Thompson Sampling with Drift-Aware Adaptive Forgetting.
    
    Forgetting formula:
        α_new = 1 + (1-γ)·(α_old - 1)
        β_new = 1 + (1-γ)·(β_old - 1)
    """
    
    def __init__(
        self,
        window_size: int = 50,
        min_gamma: float = 0.001,
        max_gamma: float = 0.3,
        drift_threshold: float = 0.05
    ):
        self.window_size = window_size
        self.min_gamma = min_gamma
        self.max_gamma = max_gamma
        self.drift_threshold = drift_threshold
        
        self.arms: dict[str, dict] = {}
        self.drift_estimators: dict[str, DriftEstimator] = {}
        self.global_drift = DriftEstimator(window_size=window_size)
        
        self.total_updates = 0
        self.gamma_history: list[float] = []
        self.drift_history: list[float] = []
    
    def get_or_create_arm(self, arm_id: str, alpha: float = 1.0, beta: float = 1.0) -> dict:
        """Get or initialize arm."""
        if arm_id not in self.arms:
            self.arms[arm_id] = {
                "alpha": alpha,
                "beta": beta,
                "pulls": 0,
                "total_reward": 0.0,
                "last_gamma": self.min_gamma,
                "last_drift": 0.0
            }
            self.drift_estimators[arm_id] = DriftEstimator(
                window_size=self.window_size,
                drift_threshold=self.drift_threshold
            )
        return self.arms[arm_id]
    
    def select(self, arm_ids: list[str]) -> tuple[str, float]:
        """Thompson Sampling selection."""
        best_sample = -1.0
        best_arm = arm_ids[0]
        
        for arm_id in arm_ids:
            arm = self.get_or_create_arm(arm_id)
            sample = np.random.beta(max(0.01, arm["alpha"]), max(0.01, arm["beta"]))
            if sample > best_sample:
                best_sample = sample
                best_arm = arm_id
        
        return best_arm, float(best_sample)
    
    def update(self, arm_id: str, reward: float) -> DriftMetrics:
        """Update arm with adaptive forgetting."""
        arm = self.get_or_create_arm(arm_id)
        reward = float(np.clip(reward, 0.0, 1.0))
        self.total_updates += 1
        
        # Drift estimation
        arm_drift = self.drift_estimators[arm_id].update(reward)
        global_drift = self.global_drift.update(reward)
        
        drift_metrics = arm_drift if arm_drift.drift_magnitude > global_drift.drift_magnitude else global_drift
        gamma = max(self.min_gamma, min(self.max_gamma, drift_metrics.optimal_gamma))
        
        # Track
        self.gamma_history.append(gamma)
        self.drift_history.append(drift_metrics.drift_magnitude)
        arm["last_gamma"] = gamma
        arm["last_drift"] = drift_metrics.drift_magnitude
        
        # Apply forgetting
        retention = 1.0 - gamma
        arm["alpha"] = max(0.01, 1.0 + retention * (arm["alpha"] - 1.0))
        arm["beta"] = max(0.01, 1.0 + retention * (arm["beta"] - 1.0))
        
        # Bayesian update
        arm["alpha"] += reward
        arm["beta"] += (1.0 - reward)
        arm["pulls"] += 1
        arm["total_reward"] += reward
        
        # Aggressive reset for abrupt drift
        if drift_metrics.drift_type == DriftType.ABRUPT:
            arm["alpha"] = 1.0 + 0.5 * (arm["alpha"] - 1.0)
            arm["beta"] = 1.0 + 0.5 * (arm["beta"] - 1.0)
        
        return drift_metrics
    
    def get_arm_stats(self, arm_id: str) -> dict:
        """Get arm statistics."""
        arm = self.get_or_create_arm(arm_id)
        total = arm["alpha"] + arm["beta"]
        return {
            "alpha": arm["alpha"],
            "beta": arm["beta"],
            "pulls": arm["pulls"],
            "mean": arm["alpha"] / total,
            "variance": (arm["alpha"] * arm["beta"]) / (total ** 2 * (total + 1)),
            "last_gamma": arm["last_gamma"],
            "last_drift": arm["last_drift"],
            "effective_samples": total - 2
        }
    
    def get_summary(self) -> dict:
        """Get system summary."""
        if not self.gamma_history:
            return {"total_updates": 0}
        
        return {
            "total_updates": self.total_updates,
            "n_arms": len(self.arms),
            "avg_gamma": float(np.mean(self.gamma_history)),
            "max_gamma": float(np.max(self.gamma_history)),
            "min_gamma": float(np.min(self.gamma_history)),
            "avg_drift": float(np.mean(self.drift_history)),
            "max_drift": float(np.max(self.drift_history)),
            "drift_events": sum(1 for d in self.drift_history if d > self.drift_threshold)
        }

# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCTION FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

def create_adaptive_forgetting_bandit(
    window_size: int = 50,
    sensitivity: float = 1.0  # Kept for backward compatibility
) -> AdaptiveForgettingBandit:
    """Create production-ready DAAF bandit."""
    return AdaptiveForgettingBandit(
        window_size=window_size,
        min_gamma=0.001,
        max_gamma=0.3,
        drift_threshold=0.05
    )

def create_drift_estimator(window_size: int = 50) -> DriftEstimator:
    """Create standalone drift estimator."""
    return DriftEstimator(window_size=window_size)

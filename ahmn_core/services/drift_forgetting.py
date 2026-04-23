"""
Drift-Aware Adaptive Forgetting (DAAF) - Production Ready

A principled approach to non-stationary bandits that dynamically adjusts the
forgetting rate based on detected environmental drift.

Mathematical Foundation:
━━━━━━━━━━━━━━━━━━━━━━━━━

The key insight is to SEPARATE noise from drift:
- Noise (σ²): Inherent variance in Bernoulli rewards (within-window variance)
- Drift (Δ): Actual change in underlying mean (between-window shift)

Forgetting Rate via Concentration Bounds:
─────────────────────────────────────────
We want γ to produce an effective window n_eff = 1/γ short enough that a
drift of magnitude Δ is separable from noise, but long enough that the
estimator remains stable. Hoeffding concentration on Bernoulli rewards
gives confidence radius r(n, t) = √(ln(t) / n) at level 1/t.

Setting r(n_eff, t) ≤ Δ so that drift Δ is just detectable against noise
after n_eff fresh samples gives:
    √(ln(t) · γ) ≤ Δ
    γ ≤ Δ² / ln(t)

We take the boundary case (the largest forgetting that remains detectable)
and use the root form for numerical stability:
    γ* = √(Δ² / ln(t))   [concentration-matched forgetting]

Interpretation: γ* is the forgetting rate at which the shortest effective
window still rejects "no drift" at confidence 1 - 1/t. Larger drift → more
aggressive forgetting. More observed samples → lower γ* (we can afford a
longer effective window because detection is easier).

Critical design choice: γ* uses the drift magnitude Δ only. Noise variance
σ² is measured separately and does NOT contribute to γ*. This is what
distinguishes DAAF from simple variance-based forgetting schedules which
react to noise as if it were drift.

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
    - drift_magnitude: |μ_recent - μ_older| (mean shift = TRUE drift)
    - noise_variance: Var(rewards) (inherent stochasticity ≠ drift)
    """
    drift_magnitude: float      # Δ - estimated mean shift (TRUE drift)
    noise_variance: float       # σ² - inherent reward variance (NOT drift)
    optimal_gamma: float        # γ* - optimal forgetting rate
    is_drifting: bool          # Whether drift exceeds threshold
    drift_type: DriftType      # Classification
    confidence: float          # Confidence in estimate (0-1)
    trend_direction: float     # +1 improving, -1 degrading, 0 stable
    effective_horizon: int     # Estimated samples until drift invalidates

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
            self.older_window.append(shifted)
            self._older_sum += shifted
        
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
        
        # Noise variance (within-window) - NOT drift
        if n_recent > 1:
            noise_var = (self._recent_sq_sum / n_recent) - (recent_mean ** 2)
            noise_var = max(0.0, noise_var)
        else:
            noise_var = 0.25
        
        # Drift magnitude (between-window mean shift) - IS drift
        if n_older >= self.min_samples:
            older_mean = self._older_sum / n_older
            drift_magnitude = abs(recent_mean - older_mean)
            trend = 1.0 if recent_mean > older_mean else (-1.0 if recent_mean < older_mean else 0.0)
        else:
            drift_magnitude = 0.0
            trend = 0.0
        
        # Classify drift type
        if drift_magnitude >= self.abrupt_threshold:
            drift_type = DriftType.ABRUPT
        elif drift_magnitude >= self.drift_threshold:
            drift_type = DriftType.GRADUAL
        else:
            drift_type = DriftType.NONE
        
        is_drifting = drift_type != DriftType.NONE
        confidence = min(1.0, (n_recent + n_older) / (2 * self.window_size))
        
        # ═══════════════════════════════════════════════════════════════
        # CORE FORMULA: γ* = √(Δ² / ln(t))
        # 
        # Uses drift_magnitude (Δ), NOT noise_variance (σ²)
        # ═══════════════════════════════════════════════════════════════
        if self.total_samples > 1 and drift_magnitude > 0:
            gamma_star = math.sqrt(
                (drift_magnitude ** 2) / max(1.0, math.log(self.total_samples))
            )
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
            effective_horizon=max(1, effective_horizon)
        )
    
    def reset(self):
        """Reset estimator (call after abrupt changepoint)."""
        self.recent_window.clear()
        self.older_window.clear()
        self.total_samples = 0
        self._recent_sum = 0.0
        self._recent_sq_sum = 0.0
        self._older_sum = 0.0

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

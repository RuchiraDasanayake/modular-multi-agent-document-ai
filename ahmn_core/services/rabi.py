"""
RABI: Retrieval-Augmented Bandit Initialization - Production Ready

Solves the cold-start problem in contextual bandits by transferring
knowledge from similar historical contexts via vector similarity.

Mathematical Foundation:
━━━━━━━━━━━━━━━━━━━━━━━━━

Prior Transfer Formula:
    α_init = 1 + Σᵢ wᵢ·(αᵢ - 1)
    β_init = 1 + Σᵢ wᵢ·(βᵢ - 1)

Where weights are computed via softmax:
    wᵢ = exp(sim_i / τ) / Σⱼ exp(sim_j / τ)

Theoretical Justification:
─────────────────────────
Under Lipschitz continuity: |μ(x) - μ(x')| ≤ L·||x - x'||

If neighbor posteriors are accurate, RABI reduces cold-start regret from
O(K) to O(L·d_avg) where d_avg is average distance to neighbors.

Key insight: We transfer (α-1, β-1) not (α, β) to preserve the
interpretation of "pseudocounts from observations" vs "prior beliefs".

Author: AHMN Research Team
"""

import math
import numpy as np

from dataclasses import dataclass

@dataclass
class RABIPrior:
    """Initialized prior from RABI."""
    alpha: float = 1.0
    beta: float = 1.0
    confidence: float = 0.0
    n_neighbors: int = 0
    avg_similarity: float = 0.0
    transfer_source: str = "flat_prior"
    
    @property
    def mean(self) -> float:
        """Expected value E[θ] = α/(α+β)."""
        return self.alpha / (self.alpha + self.beta)
    
    @property
    def variance(self) -> float:
        """Variance of Beta distribution."""
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total ** 2 * (total + 1))
    
    @property
    def effective_samples(self) -> float:
        """Effective sample size from prior."""
        return self.alpha + self.beta - 2

@dataclass  
class NeighborInfo:
    """Information about a neighbor used in RABI."""
    context_hash: str
    policy_id: str
    alpha: float
    beta: float
    similarity: float
    n_samples: int  # α + β - 2
    
    @property
    def mean_reward(self) -> float:
        """Neighbor's estimated mean reward."""
        return self.alpha / (self.alpha + self.beta)

class RABIInitializer:
    """
    Retrieval-Augmented Bandit Initialization.
    
    Production-ready implementation with:
    - Softmax temperature weighting
    - Similarity thresholding
    - Minimum sample requirements
    - Graceful degradation to flat prior
    """
    
    def __init__(
        self,
        k: int = 5,
        similarity_threshold: float = 0.3,
        temperature: float = 0.5,
        min_samples_for_transfer: int = 5,
        max_transfer_strength: float = 10.0
    ):
        """
        Args:
            k: Number of nearest neighbors
            similarity_threshold: Minimum cosine similarity (0-1)
            temperature: Softmax temperature (lower = sharper weighting)
            min_samples_for_transfer: Minimum observations neighbor needs
            max_transfer_strength: Cap on transferred pseudocounts
        """
        self.k = k
        self.similarity_threshold = similarity_threshold
        self.temperature = max(0.01, temperature)  # Prevent division by zero
        self.min_samples_for_transfer = min_samples_for_transfer
        self.max_transfer_strength = max_transfer_strength
    
    def compute_weights(self, similarities: list[float]) -> list[float]:
        """
        Compute normalized softmax weights.
        
        w_i = exp(sim_i / τ) / Σ exp(sim_j / τ)
        """
        if not similarities:
            return []
        
        # Softmax with temperature
        scaled = [s / self.temperature for s in similarities]
        max_scaled = max(scaled)  # Numerical stability
        exp_scaled = [math.exp(s - max_scaled) for s in scaled]
        total = sum(exp_scaled)
        
        return [e / total for e in exp_scaled] if total > 0 else [1/len(similarities)] * len(similarities)
    
    def initialize_prior(self, neighbors: list[NeighborInfo]) -> RABIPrior:
        """
        Initialize prior from k-nearest neighbors.
        
        Formula:
            α_init = 1 + Σᵢ wᵢ·(αᵢ - 1)
            β_init = 1 + Σᵢ wᵢ·(βᵢ - 1)
        """
        # Filter valid neighbors
        valid = [
            n for n in neighbors
            if n.similarity >= self.similarity_threshold
            and n.n_samples >= self.min_samples_for_transfer
        ]
        
        # Fall back to flat prior
        if not valid:
            return RABIPrior(
                alpha=1.0,
                beta=1.0,
                confidence=0.0,
                n_neighbors=0,
                avg_similarity=0.0,
                transfer_source="flat_prior (no valid neighbors)"
            )
        
        # Compute weights
        similarities = [n.similarity for n in valid]
        weights = self.compute_weights(similarities)
        
        # Transfer pseudocounts (not raw α,β)
        alpha_transfer = sum(w * (n.alpha - 1.0) for w, n in zip(weights, valid))
        beta_transfer = sum(w * (n.beta - 1.0) for w, n in zip(weights, valid))
        
        # Cap transfer strength
        total_transfer = abs(alpha_transfer) + abs(beta_transfer)
        if total_transfer > self.max_transfer_strength:
            scale = self.max_transfer_strength / total_transfer
            alpha_transfer *= scale
            beta_transfer *= scale
        
        # Final prior
        alpha_init = max(0.1, 1.0 + alpha_transfer)
        beta_init = max(0.1, 1.0 + beta_transfer)
        
        # Confidence metric
        avg_sim = sum(similarities) / len(similarities)
        total_samples = sum(n.n_samples for n in valid)
        confidence = min(1.0, avg_sim * math.log1p(total_samples) / 5)
        
        # Source description
        policies = list(set(n.policy_id for n in valid))[:3]
        source = f"RABI({len(valid)} neighbors): {policies}"
        
        return RABIPrior(
            alpha=alpha_init,
            beta=beta_init,
            confidence=confidence,
            n_neighbors=len(valid),
            avg_similarity=avg_sim,
            transfer_source=source
        )
    
    def get_expected_reward(self, prior: RABIPrior) -> float:
        """Zero-shot prediction: E[θ] = α/(α+β)."""
        return prior.mean
    
    def get_uncertainty(self, prior: RABIPrior) -> float:
        """Uncertainty in prediction."""
        return prior.variance

class RABIThompsonSampling:
    """
    Thompson Sampling with RABI initialization.
    
    Combines:
    - RABI for cold-start (new contexts)
    - Standard TS for online learning (updates)
    - Optional decay of transferred knowledge
    """
    
    def __init__(
        self,
        rabi: RABIInitializer | None = None,
        decay_transfer: bool = True,
        decay_rate: float = 0.05
    ):
        self.rabi = rabi or RABIInitializer()
        self.decay_transfer = decay_transfer
        self.decay_rate = decay_rate
        self.arms: dict[str, dict] = {}
    
    def initialize_arm(self, arm_id: str, neighbors: list[NeighborInfo]) -> RABIPrior:
        """Initialize new arm using RABI."""
        prior = self.rabi.initialize_prior(neighbors)
        
        self.arms[arm_id] = {
            "alpha": prior.alpha,
            "beta": prior.beta,
            "pulls": 0,
            "transferred_alpha": prior.alpha - 1.0,
            "transferred_beta": prior.beta - 1.0,
            "rabi_prior": prior
        }
        return prior
    
    def select(self, arm_ids: list[str]) -> tuple[str, float]:
        """Thompson Sampling selection."""
        best_sample = -1.0
        best_arm = arm_ids[0]
        
        for arm_id in arm_ids:
            if arm_id not in self.arms:
                sample = np.random.beta(1.0, 1.0)  # Flat prior for unknown
            else:
                arm = self.arms[arm_id]
                sample = np.random.beta(
                    max(0.01, arm["alpha"]),
                    max(0.01, arm["beta"])
                )
            
            if sample > best_sample:
                best_sample = sample
                best_arm = arm_id
        
        return best_arm, float(best_sample)
    
    def update(self, arm_id: str, reward: float):
        """Update arm after observing reward."""
        reward = float(np.clip(reward, 0.0, 1.0))
        
        if arm_id not in self.arms:
            self.arms[arm_id] = {
                "alpha": 1.0,
                "beta": 1.0,
                "pulls": 0,
                "transferred_alpha": 0.0,
                "transferred_beta": 0.0,
                "rabi_prior": None
            }
        
        arm = self.arms[arm_id]
        
        # Decay transferred knowledge
        if self.decay_transfer and arm["transferred_alpha"] > 0:
            decay = (1 - self.decay_rate) ** arm["pulls"]
            prev_decay = (1 - self.decay_rate) ** max(0, arm["pulls"] - 1) if arm["pulls"] > 0 else 1.0
            
            # Use the *previously decayed* transfer to compute own observations
            prev_decayed_alpha = arm["transferred_alpha"] * prev_decay
            prev_decayed_beta = arm["transferred_beta"] * prev_decay
            own_successes = arm["alpha"] - 1.0 - prev_decayed_alpha
            own_failures = arm["beta"] - 1.0 - prev_decayed_beta
            
            decayed_transfer_alpha = arm["transferred_alpha"] * decay
            decayed_transfer_beta = arm["transferred_beta"] * decay
            
            arm["alpha"] = 1.0 + own_successes + decayed_transfer_alpha
            arm["beta"] = 1.0 + own_failures + decayed_transfer_beta
        
        # Bayesian update
        arm["alpha"] += reward
        arm["beta"] += (1 - reward)
        arm["pulls"] += 1
    
    def get_arm_stats(self, arm_id: str) -> dict | None:
        """Get arm statistics."""
        if arm_id not in self.arms:
            return None
        
        arm = self.arms[arm_id]
        total = arm["alpha"] + arm["beta"]
        return {
            "alpha": arm["alpha"],
            "beta": arm["beta"],
            "mean": arm["alpha"] / total,
            "pulls": arm["pulls"],
            "transferred": arm["transferred_alpha"] + arm["transferred_beta"],
            "rabi_confidence": arm["rabi_prior"].confidence if arm["rabi_prior"] else 0.0
        }

# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCTION FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

def create_rabi_for_production(
    k: int = 5,
    similarity_threshold: float = 0.4,
    temperature: float = 0.5
) -> RABIInitializer:
    """
    Create production-ready RABI.
    
    Defaults based on experiments:
    - k=5: Good coverage without noise
    - similarity_threshold=0.4: Filters dissimilar contexts
    - temperature=0.5: Sharper weighting toward most similar
    """
    return RABIInitializer(
        k=k,
        similarity_threshold=similarity_threshold,
        temperature=temperature,
        min_samples_for_transfer=5,
        max_transfer_strength=10.0
    )

"""
Selection strategies for multi-armed bandit policy selection.

Implements multiple baseline algorithms for comparison with Thompson Sampling:
- Thompson Sampling (Beta-Bernoulli)
- Upper Confidence Bound (UCB1)
- Epsilon-Greedy with decay
"""
import random
import math
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class BanditArm:
    """Represents a bandit arm (policy) with its statistics."""
    policy_id: str
    policy_data: dict
    context_hash: str
    alpha: float = 1.0
    beta: float = 1.0
    pulls: int = 0  # Total number of times this arm was selected
    
    @property
    def mean_reward(self) -> float:
        """Empirical mean reward (alpha / (alpha + beta))."""
        return self.alpha / (self.alpha + self.beta)
    
    @property
    def total_reward(self) -> float:
        """Total accumulated reward."""
        return self.alpha - 1.0  # Subtract initial prior


class SelectionStrategy:
    """Base class for selection strategies."""
    
    def __init__(self, name: str):
        self.name = name
    
    def select(self, arms: List[BanditArm], total_rounds: int) -> Tuple[BanditArm, float]:
        """
        Select an arm and return it with the selection score.
        
        Args:
            arms: List of available bandit arms
            total_rounds: Total number of rounds played so far
            
        Returns:
            Tuple of (selected_arm, selection_score)
        """
        raise NotImplementedError


class ThompsonSamplingStrategy(SelectionStrategy):
    """
    Thompson Sampling with Beta-Bernoulli prior.
    
    Samples from Beta(alpha, beta) for each arm and selects the highest sample.
    This naturally balances exploration and exploitation.
    
    Reference: Thompson (1933), "On the Likelihood that One Unknown Probability
    Exceeds Another in View of the Evidence of Two Samples"
    """
    
    def __init__(self):
        super().__init__("Thompson Sampling")
    
    def select(self, arms: List[BanditArm], total_rounds: int) -> Tuple[BanditArm, float]:
        if not arms:
            raise ValueError("Cannot select from empty arms list")
        
        best_sample = -1.0
        best_arm = arms[0]  # Initialize with first arm
        
        for arm in arms:
            # Sample from Beta distribution
            sample = random.betavariate(arm.alpha, arm.beta)
            
            if sample > best_sample:
                best_sample = sample
                best_arm = arm
        
        return best_arm, best_sample


class UCB1Strategy(SelectionStrategy):
    """
    Upper Confidence Bound (UCB1) algorithm.
    
    Selects the arm with highest upper confidence bound:
    UCB(i) = mean_reward(i) + sqrt(2 * ln(t) / n(i))
    
    where:
    - mean_reward(i) is the empirical mean of arm i
    - t is the total number of rounds
    - n(i) is the number of times arm i was pulled
    
    Reference: Auer et al. (2002), "Finite-time Analysis of the Multiarmed Bandit Problem"
    """
    
    def __init__(self, c: float = 2.0):
        """
        Args:
            c: Exploration parameter (default: 2.0, theoretical optimum for UCB1)
        """
        super().__init__("UCB1")
        self.c = c
    
    def select(self, arms: List[BanditArm], total_rounds: int) -> Tuple[BanditArm, float]:
        if not arms:
            raise ValueError("Cannot select from empty arms list")
        
        # Ensure all arms have been pulled at least once
        for arm in arms:
            if arm.pulls == 0:
                return arm, float('inf')
        
        best_ucb = -1.0
        best_arm = arms[0]  # Initialize with first arm
        
        for arm in arms:
            # UCB formula: mean + sqrt(c * ln(t) / n)
            exploitation = arm.mean_reward
            exploration = math.sqrt(self.c * math.log(max(1, total_rounds)) / max(1, arm.pulls))
            ucb = exploitation + exploration
            
            if ucb > best_ucb:
                best_ucb = ucb
                best_arm = arm
        
        return best_arm, best_ucb


class EpsilonGreedyStrategy(SelectionStrategy):
    """
    Epsilon-Greedy with exponential decay.
    
    With probability epsilon: explore (select random arm)
    With probability 1-epsilon: exploit (select best arm by mean reward)
    
    Epsilon decays over time: epsilon(t) = epsilon_0 * exp(-decay_rate * t)
    
    Reference: Sutton & Barto (2018), "Reinforcement Learning: An Introduction"
    """
    
    def __init__(self, epsilon_0: float = 1.0, decay_rate: float = 0.001, epsilon_min: float = 0.01):
        """
        Args:
            epsilon_0: Initial exploration probability (default: 1.0, pure exploration)
            decay_rate: Rate of epsilon decay (default: 0.001)
            epsilon_min: Minimum epsilon value (default: 0.01, maintains 1% exploration)
        """
        super().__init__("Epsilon-Greedy")
        self.epsilon_0 = epsilon_0
        self.decay_rate = decay_rate
        self.epsilon_min = epsilon_min
    
    def select(self, arms: List[BanditArm], total_rounds: int) -> Tuple[BanditArm, float]:
        # Compute current epsilon with decay
        epsilon = max(self.epsilon_min, self.epsilon_0 * math.exp(-self.decay_rate * total_rounds))
        
        if random.random() < epsilon:
            # Explore: random selection
            selected_arm = random.choice(arms)
            return selected_arm, epsilon  # Return epsilon as the "score"
        else:
            # Exploit: select arm with highest mean reward
            best_arm = max(arms, key=lambda a: a.mean_reward)
            return best_arm, best_arm.mean_reward


class RandomStrategy(SelectionStrategy):
    """
    Random baseline - selects arms uniformly at random.
    
    This serves as the simplest baseline for comparison.
    Expected regret is linear in the number of rounds.
    """
    
    def __init__(self):
        super().__init__("Random")
    
    def select(self, arms: List[BanditArm], total_rounds: int) -> Tuple[BanditArm, float]:
        selected_arm = random.choice(arms)
        return selected_arm, 0.0  # No meaningful score for random


def get_strategy(strategy_name: str) -> SelectionStrategy:
    """
    Factory function to get strategy by name.
    
    Args:
        strategy_name: One of ["thompson", "ucb", "epsilon_greedy", "random"]
        
    Returns:
        SelectionStrategy instance
    """
    strategies = {
        "thompson": ThompsonSamplingStrategy(),
        "ucb": UCB1Strategy(c=2.0),
        "epsilon_greedy": EpsilonGreedyStrategy(epsilon_0=1.0, decay_rate=0.001, epsilon_min=0.01),
        "random": RandomStrategy()
    }
    
    if strategy_name not in strategies:
        raise ValueError(f"Unknown strategy: {strategy_name}. Choose from {list(strategies.keys())}")
    
    return strategies[strategy_name]

from .selection_strategies import ThompsonSamplingStrategy, UCB1Strategy, EpsilonGreedyStrategy, RandomStrategy, BanditArm
from .rabi import RABIInitializer, RABIPrior, NeighborInfo
from .drift_forgetting import DriftEstimator, AdaptiveForgettingBandit, DriftType, DriftMetrics

__all__ = [
    "ThompsonSamplingStrategy", "UCB1Strategy", "EpsilonGreedyStrategy",
    "RandomStrategy", "BanditArm", "RABIInitializer", "RABIPrior", "NeighborInfo",
    "DriftEstimator", "AdaptiveForgettingBandit", "DriftType", "DriftMetrics",
    "EmbeddingService",
]


def __getattr__(name):
    # Pure bandit simulations must not import the optional model runtime.
    if name == "EmbeddingService":
        from .embedding import EmbeddingService
        return EmbeddingService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

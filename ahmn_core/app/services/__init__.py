"""
AHMN Services Module

Contains core business logic:
- embedding: Vector embedding generation using SentenceTransformers
- memory: Three-tier memory management (STM/MTM/LTM)
- selection_strategies: Multi-armed bandit algorithms (Thompson, UCB1, ε-greedy)

Note: Imports are lazy to avoid requiring sentence_transformers for standalone demos.
Import directly from submodules if needed:
    from app.services.selection_strategies import BanditArm
    from app.services.embedding import EmbeddingService
"""

# Lazy imports - only import selection_strategies by default (no heavy dependencies)
from .selection_strategies import (
    BanditArm,
    SelectionStrategy,
    ThompsonSamplingStrategy,
    UCB1Strategy,
    EpsilonGreedyStrategy,
    RandomStrategy,
    get_strategy
)

# EmbeddingService and MemoryService require sentence_transformers/psycopg
# Import them explicitly when needed:
#   from app.services.embedding import EmbeddingService
#   from app.services.memory import MemoryService

__all__ = [
    "BanditArm",
    "SelectionStrategy",
    "ThompsonSamplingStrategy",
    "UCB1Strategy", 
    "EpsilonGreedyStrategy",
    "RandomStrategy",
    "get_strategy"
]

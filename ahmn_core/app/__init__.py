"""
AHMN (Adaptive Hierarchical Memory Network) - Core Application Module

This module provides the core functionality for the AHMN system:
- config: Configuration and hyperparameters
- database: PostgreSQL and Redis connection management
- schemas: Pydantic data models
- services: Business logic (embedding, memory, selection strategies)
"""

from .config import settings, AHMNConfig

__all__ = ["settings", "AHMNConfig"]

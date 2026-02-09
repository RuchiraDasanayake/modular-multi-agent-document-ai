"""Dashboard schemas — data transfer objects for charts/tables."""

from pydantic import BaseModel
from typing import Any


class StatsResponse(BaseModel):
    total_advice: int
    total_outcomes: int
    total_ltm_policies: int
    total_experiments: int
    total_users: int


class MemoryEntry(BaseModel):
    id: str
    data: dict[str, Any]
    created_at: str


class LTMEntry(BaseModel):
    id: str
    context_hash: str
    policy_id: str
    alpha: float
    beta: float
    confidence_score: float
    last_promoted_at: str


class ExperimentEntry(BaseModel):
    id: str
    method: str
    scenario: str
    seed: int
    total_regret: float
    final_accuracy: float | None
    convergence_round: int | None
    created_at: str


class SimulationRequest(BaseModel):
    """Request to run an interactive simulation (RABI / DAAF demo)."""
    demo_type: str  # "rabi" | "daaf" | "experiment"
    params: dict[str, Any] = {}

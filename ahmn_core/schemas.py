"""Pydantic schemas for the AHMN memory service API."""

from pydantic import BaseModel, Field
from typing import Any, Literal
from uuid import UUID

class DocumentContext(BaseModel):
    doc_type: str
    vendor: str | None = None
    content_profile: str | None = None
    extra_context: dict[str, Any] = Field(default_factory=dict)

class OutcomeMetrics(BaseModel):
    f1_score: float
    cost: float
    processing_time_ms: float
    success: bool
    precision: float | None = None
    recall: float | None = None

class LogRequest(BaseModel):
    advice_id: UUID
    policy_id_used: str
    metrics: OutcomeMetrics

class FeedbackRequest(BaseModel):
    advice_id: UUID
    human_corrected: bool

class PolicyResponse(BaseModel):
    advice_id: UUID
    policy_id: str
    policy_data: dict[str, Any]
    retrieval_source: Literal["LTM", "MTM", "DEFAULT"]
    confidence: float = Field(description="Confidence score [0-1] for this recommendation")
    rabi_used: bool = Field(default=False, description="Whether RABI initialization was used")
    n_neighbors: int | None = Field(default=None, description="Number of neighbors used for RABI")

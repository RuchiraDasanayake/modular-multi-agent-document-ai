"""Pydantic schemas for the AHMN memory service API."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

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
    schema_valid: bool | None = None
    missing_required_count: int | None = None
    hallucinated_field_count: int | None = None
    grounding_coverage: float | None = None
    defer_status: str | None = None
    direct_scored: bool | None = None

class LogRequest(BaseModel):
    advice_id: UUID
    policy_id_used: str
    metrics: OutcomeMetrics
    document_context: dict[str, Any] | None = Field(
        default=None,
        description="Actual document context discovered during processing. "
        "When provided, overrides the stale pre-processing context stored in STM.",
    )

class FeedbackRequest(BaseModel):
    advice_id: UUID
    human_corrected: bool
    feedback_type: str | None = Field(
        default=None,
        description="Original reviewer verdict: correct, incorrect, partially_correct, needs_more_context",
    )


class ReviewFeedbackRequest(BaseModel):
    advice_id: UUID
    policy_id_used: str
    document_context: dict[str, Any]
    review_source: Literal["ai", "human"]
    review_weight: float = Field(gt=0.0)
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    field_state_counts: dict[str, int] = Field(default_factory=dict)
    job_id: str | None = None
    overlay_key: str | None = None

class PolicyResponse(BaseModel):
    advice_id: UUID
    policy_id: str
    policy_data: dict[str, Any]
    retrieval_source: Literal["LTM", "MTM", "DEFAULT"]
    confidence: float = Field(description="Confidence score [0-1] for this recommendation")
    rabi_used: bool = Field(default=False, description="Whether RABI initialization was used")
    n_neighbors: int | None = Field(default=None, description="Number of neighbors used for RABI")

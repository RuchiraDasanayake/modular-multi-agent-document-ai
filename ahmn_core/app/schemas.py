from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Literal
from uuid import UUID

class DocumentContext(BaseModel):
    doc_type: str
    vendor: Optional[str] = None
    extra_context: Dict[str, Any] = Field(default_factory=dict)

class OutcomeMetrics(BaseModel):
    f1_score: float
    cost: float
    processing_time_ms: float
    success: bool

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
    policy_data: Dict[str, Any]
    retrieval_source: Literal["LTM", "MTM", "DEFAULT"]

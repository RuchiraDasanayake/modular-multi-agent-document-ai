"""HITL schemas — request/response models for human-in-the-loop feedback."""

from typing import Literal
from pydantic import BaseModel, Field


FeedbackType = Literal["correct", "incorrect", "partially_correct", "needs_more_context"]
FeedbackPriority = Literal["low", "medium", "high", "critical"]


class FeedbackSubmitRequest(BaseModel):
    question: str
    original_answer: str
    feedback_type: FeedbackType
    corrected_answer: str | None = None
    explanation_quality: int = Field(ge=1, le=5, default=3)
    highlight_accuracy: int = Field(ge=1, le=5, default=3)
    xai_helpfulness: int = Field(ge=1, le=5, default=3)
    additional_context: str | None = None
    knowledge_update: str | None = None


class FeedbackResponse(BaseModel):
    feedback_id: str
    status: str


class FeedbackRatings(BaseModel):
    explanation_quality: int
    highlight_accuracy: int
    xai_helpfulness: int


class HITLFeedback(BaseModel):
    feedback_id: str
    timestamp: str
    question: str
    original_answer: str
    feedback_type: FeedbackType
    is_answer_correct: bool
    corrected_answer: str | None = None
    ratings: FeedbackRatings
    additional_context: str | None = None
    knowledge_update: str | None = None
    priority: FeedbackPriority = "medium"
    reviewer_notes: str | None = None
    tags: list[str] = []


class FeedbackHistory(BaseModel):
    items: list[HITLFeedback]
    total: int
    accuracy_rate: float


class HITLStats(BaseModel):
    total_feedback: int
    correct_count: int
    accuracy_rate: float
    avg_explanation_quality: float
    pending_reviews: int

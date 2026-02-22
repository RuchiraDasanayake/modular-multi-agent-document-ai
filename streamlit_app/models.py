"""
Data Models for Finance Q&A Bot with XAI
=========================================
Contains all data classes and enums used across the application.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class FeedbackType(Enum):
    """Types of human feedback"""
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIALLY_CORRECT = "partially_correct"
    NEEDS_MORE_CONTEXT = "needs_more_context"
    XAI_UNCLEAR = "xai_unclear"


class FeedbackPriority(Enum):
    """Priority levels for feedback"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class HITLFeedback:
    """Structure for human feedback data"""
    feedback_id: str
    timestamp: str
    question: str
    original_answer: str
    feedback_type: FeedbackType
    is_answer_correct: bool
    corrected_answer: Optional[str] = None
    explanation_quality: int = 3  # 1-5 scale
    highlight_accuracy: int = 3  # 1-5 scale
    xai_helpfulness: int = 3  # 1-5 scale
    additional_context: Optional[str] = None
    knowledge_update: Optional[str] = None
    priority: FeedbackPriority = FeedbackPriority.MEDIUM
    reviewer_notes: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API submission"""
        return {
            "feedback_id": self.feedback_id,
            "timestamp": self.timestamp,
            "question": self.question,
            "original_answer": self.original_answer,
            "feedback_type": self.feedback_type.value,
            "is_answer_correct": self.is_answer_correct,
            "corrected_answer": self.corrected_answer,
            "ratings": {
                "explanation_quality": self.explanation_quality,
                "highlight_accuracy": self.highlight_accuracy,
                "xai_helpfulness": self.xai_helpfulness
            },
            "additional_context": self.additional_context,
            "knowledge_update": self.knowledge_update,
            "priority": self.priority.value,
            "reviewer_notes": self.reviewer_notes,
            "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HITLFeedback":
        """Create HITLFeedback from dictionary"""
        ratings = data.get("ratings", {})
        return cls(
            feedback_id=data.get("feedback_id", ""),
            timestamp=data.get("timestamp", ""),
            question=data.get("question", ""),
            original_answer=data.get("original_answer", ""),
            feedback_type=FeedbackType(data.get("feedback_type", "correct")),
            is_answer_correct=data.get("is_answer_correct", False),
            corrected_answer=data.get("corrected_answer"),
            explanation_quality=ratings.get("explanation_quality", 3),
            highlight_accuracy=ratings.get("highlight_accuracy", 3),
            xai_helpfulness=ratings.get("xai_helpfulness", 3),
            additional_context=data.get("additional_context"),
            knowledge_update=data.get("knowledge_update"),
            priority=FeedbackPriority(data.get("priority", "medium")),
            reviewer_notes=data.get("reviewer_notes"),
            tags=data.get("tags", [])
        )

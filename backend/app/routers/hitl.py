"""
HITL router — Human-in-the-Loop feedback endpoints (/api/hitl).
Collects reviewer feedback and exposes history / stats.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..schemas.hitl import (
    FeedbackSubmitRequest,
    FeedbackResponse,
    FeedbackHistory,
    HITLFeedback,
    FeedbackRatings,
    HITLStats,
)

router = APIRouter(prefix="/api/hitl", tags=["hitl"])

# In-memory store until a real DB table is added
_feedback_store: list[HITLFeedback] = []


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit human feedback on a Q&A result."""
    feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
    entry = HITLFeedback(
        feedback_id=feedback_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        question=body.question,
        original_answer=body.original_answer,
        feedback_type=body.feedback_type,
        is_answer_correct=body.feedback_type == "correct",
        corrected_answer=body.corrected_answer,
        ratings=FeedbackRatings(
            explanation_quality=body.explanation_quality,
            highlight_accuracy=body.highlight_accuracy,
            xai_helpfulness=body.xai_helpfulness,
        ),
        additional_context=body.additional_context,
        knowledge_update=body.knowledge_update,
    )
    _feedback_store.append(entry)

    return FeedbackResponse(feedback_id=feedback_id, status="accepted")


@router.get("/history", response_model=FeedbackHistory)
async def get_feedback_history(
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    """Return recent feedback entries."""
    items = _feedback_store[-limit:]
    total = len(_feedback_store)
    correct = sum(1 for f in _feedback_store if f.is_answer_correct)
    accuracy = (correct / total * 100) if total > 0 else 0.0

    return FeedbackHistory(items=items, total=total, accuracy_rate=accuracy)


@router.get("/feedback/{feedback_id}", response_model=HITLFeedback)
async def get_feedback_by_id(
    feedback_id: str,
    user: dict = Depends(get_current_user),
):
    """Retrieve a single feedback entry."""
    for entry in _feedback_store:
        if entry.feedback_id == feedback_id:
            return entry
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Feedback not found")


@router.get("/stats", response_model=HITLStats)
async def get_hitl_stats(
    user: dict = Depends(get_current_user),
):
    """Aggregate HITL statistics."""
    total = len(_feedback_store)
    correct = sum(1 for f in _feedback_store if f.is_answer_correct)
    avg_quality = (
        sum(f.ratings.explanation_quality for f in _feedback_store) / total
        if total > 0
        else 0.0
    )

    return HITLStats(
        total_feedback=total,
        correct_count=correct,
        accuracy_rate=(correct / total * 100) if total > 0 else 0.0,
        avg_explanation_quality=avg_quality,
        pending_reviews=0,
    )

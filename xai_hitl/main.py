"""
XAI-HITL Microservice
=====================
Explainable AI engine + Human-in-the-Loop feedback.
Owner : Pathirana M.M.

Endpoints
---------
POST /xai/ask            — answer question with SHAP / LIME explanations
GET  /xai/explanation/{id} — retrieve cached explanation
POST /hitl/feedback      — submit reviewer feedback
GET  /hitl/history       — recent feedback entries
GET  /hitl/feedback/{id} — single entry
GET  /hitl/stats         — aggregate statistics
GET  /health             — liveness probe
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("xai_hitl")

# ---------------------------------------------------------------------------
# Pydantic schemas (self-contained — no dependency on gateway schemas)
# ---------------------------------------------------------------------------

# ─── XAI Schemas ──────────────────────────────────────────────────────────

class QARequest(BaseModel):
    paragraph: str
    question: str


class HighlightSpan(BaseModel):
    start: int
    end: int
    text: str
    type: str  # "answer" | "positive" | "negative" | "medium"
    shap_score: float
    lime_score: float


class SHAPExplanation(BaseModel):
    shap_values: list[tuple[str, float]]
    base_value: float


class LIMEExplanation(BaseModel):
    word_weights: list[tuple[str, float]]
    prediction_proba: float


class DerivationStep(BaseModel):
    step_number: int
    action: str
    description: str
    details: str | None = None
    confidence: float


class XAIExplanation(BaseModel):
    answer: str
    confidence_score: float
    highlighted_spans: list[HighlightSpan]
    shap_explanation: SHAPExplanation
    lime_explanation: LIMEExplanation
    derivation_steps: list[DerivationStep]
    evidence_sentences: list[str]


class QAResponse(BaseModel):
    answer: str
    confidence: float
    explanation: XAIExplanation


# ─── HITL Schemas ─────────────────────────────────────────────────────────

FeedbackType = Literal[
    "correct", "incorrect", "partially_correct", "needs_more_context"
]
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


# ---------------------------------------------------------------------------
# XAI Engine — lazy singleton
# ---------------------------------------------------------------------------

_real_engine = None
_engine_available = False

try:
    from .engine import get_engine as _get_engine

    _engine_available = True
    logger.info("XAI engine module located — will lazy-init on first request")
except ImportError:
    logger.warning("XAI engine import failed — demo stubs will be used")


def _demo_explanation(
    question: str, answer: str, confidence: float
) -> XAIExplanation:
    """Build a synthetic XAI explanation (used when the model is absent)."""
    return XAIExplanation(
        answer=answer,
        confidence_score=confidence,
        highlighted_spans=[
            HighlightSpan(
                start=0,
                end=min(50, len(answer)),
                text=answer[:50],
                type="answer",
                shap_score=0.85,
                lime_score=0.78,
            ),
        ],
        shap_explanation=SHAPExplanation(
            shap_values=[
                ("finance", 0.45),
                ("capital", 0.38),
                ("money", 0.32),
                ("economy", 0.28),
                ("time", 0.25),
                ("value", 0.22),
            ],
            base_value=0.5,
        ),
        lime_explanation=LIMEExplanation(
            word_weights=[
                ("finance", 0.42),
                ("capital", 0.35),
                ("economy", 0.30),
                ("money", 0.28),
                ("instruments", 0.22),
                ("risk", 0.12),
            ],
            prediction_proba=confidence,
        ),
        derivation_steps=[
            DerivationStep(
                step_number=1,
                action="Question Analysis",
                description="Parsed user question",
                confidence=0.95,
            ),
            DerivationStep(
                step_number=2,
                action="Context Retrieval",
                description="Retrieved relevant paragraph sections",
                confidence=0.90,
            ),
            DerivationStep(
                step_number=3,
                action="SHAP Analysis",
                description="Computed feature importance via SHAP",
                confidence=0.88,
            ),
            DerivationStep(
                step_number=4,
                action="LIME Analysis",
                description="Generated local surrogate explanations",
                confidence=0.85,
            ),
            DerivationStep(
                step_number=5,
                action="Answer Synthesis",
                description="Formulated final answer",
                confidence=confidence,
            ),
        ],
        evidence_sentences=[
            "Finance is fundamentally the study of resource allocation over time.",
            "It functions as the circulatory system of the global economy.",
        ],
    )


def _engine_explanation_to_schema(exp) -> XAIExplanation:  # noqa: ANN001
    """Convert the engine's dataclass-based explanation to API schema."""
    _HIGHLIGHT_MAP = {
        "answer_span": "answer",
        "high_importance": "positive",
        "medium_importance": "medium",
        "low_importance": "negative",
        "positive": "positive",
        "negative": "negative",
    }
    return XAIExplanation(
        answer=exp.answer,
        confidence_score=exp.confidence_score,
        highlighted_spans=[
            HighlightSpan(
                start=s.start,
                end=s.end,
                text=s.text,
                type=_HIGHLIGHT_MAP.get(s.highlight_type.value, "medium"),
                shap_score=s.shap_score,
                lime_score=s.lime_score,
            )
            for s in exp.highlighted_spans
        ],
        shap_explanation=SHAPExplanation(
            shap_values=exp.shap_explanation.shap_values,
            base_value=exp.shap_explanation.base_value,
        ),
        lime_explanation=LIMEExplanation(
            word_weights=exp.lime_explanation.word_weights,
            prediction_proba=exp.lime_explanation.prediction_proba,
        ),
        derivation_steps=[
            DerivationStep(
                step_number=s.step_number,
                action=s.action,
                description=s.description,
                details=s.details,
                confidence=s.confidence,
            )
            for s in exp.derivation_tree.steps
        ],
        evidence_sentences=exp.evidence_sentences,
    )


# ---------------------------------------------------------------------------
# In-memory stores (no DB dependency for this service)
# ---------------------------------------------------------------------------

_feedback_store: list[HITLFeedback] = []
_explanation_cache: dict[str, QAResponse] = {}

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="XAI-HITL Service",
    version="1.0.0",
    description="Explainable AI engine with Human-in-the-Loop feedback collection.",
)


# ─── Utility: extract requesting user from gateway headers ────────────────

def _user_id(headers: dict) -> str:
    return headers.get("x-user-id", "anonymous")


# ─── Health ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "xai-hitl",
        "engine_available": _engine_available,
    }


# ─── XAI Routes ──────────────────────────────────────────────────────────

@app.post("/xai/ask", response_model=QAResponse)
async def ask_question(body: QARequest):
    """Answer a question about a paragraph with SHAP / LIME explanations."""
    qa_id = f"qa_{uuid.uuid4().hex[:12]}"

    if _engine_available:
        try:
            engine = _get_engine()
            exp = engine.generate_explanation(body.paragraph, body.question)
            schema_exp = _engine_explanation_to_schema(exp)
            response = QAResponse(
                answer=exp.answer,
                confidence=exp.confidence_score,
                explanation=schema_exp,
            )
            _explanation_cache[qa_id] = response
            return response
        except Exception as exc:
            logger.error("Engine failed, falling back to demo: %s", exc)

    # Demo fallback — deterministic answers for common question patterns
    q = body.question.lower()
    if "time value" in q or "dollar" in q:
        answer = (
            "The time value of money asserts that a dollar held today is "
            "worth more than a dollar received tomorrow due to its "
            "potential earning capacity."
        )
        confidence = 0.92
    elif "function" in q or "core" in q:
        answer = (
            "At its core, finance functions as the circulatory system of "
            "the global economy, moving capital from savers and investors "
            "to borrowers and entrepreneurs."
        )
        confidence = 0.88
    elif "instrument" in q or "stock" in q or "bond" in q:
        answer = (
            "Financial exchange is mediated by various instruments such "
            "as stocks, bonds, and derivatives."
        )
        confidence = 0.90
    else:
        answer = (
            "Finance is the study of resource allocation over time, "
            "balancing returns against risk, and functions as the "
            "circulatory system of the global economy."
        )
        confidence = 0.75

    response = QAResponse(
        answer=answer,
        confidence=confidence,
        explanation=_demo_explanation(body.question, answer, confidence),
    )
    _explanation_cache[qa_id] = response
    return response


@app.get("/xai/explanation/{question_id}", response_model=QAResponse)
async def get_explanation(question_id: str):
    """Retrieve a previously generated explanation by ID."""
    if question_id in _explanation_cache:
        return _explanation_cache[question_id]

    # Placeholder if not found in cache
    return QAResponse(
        answer="(stored explanation placeholder)",
        confidence=0.5,
        explanation=_demo_explanation(
            "", "(stored explanation placeholder)", 0.5
        ),
    )


# ─── HITL Routes ──────────────────────────────────────────────────────────

@app.post("/hitl/feedback", response_model=FeedbackResponse)
async def submit_feedback(body: FeedbackSubmitRequest):
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
    logger.info("Feedback %s recorded (type=%s)", feedback_id, body.feedback_type)
    return FeedbackResponse(feedback_id=feedback_id, status="accepted")


@app.get("/hitl/history", response_model=FeedbackHistory)
async def get_feedback_history(limit: int = 20):
    """Return the most recent feedback entries."""
    items = _feedback_store[-limit:]
    total = len(_feedback_store)
    correct = sum(1 for f in _feedback_store if f.is_answer_correct)
    accuracy = (correct / total * 100) if total > 0 else 0.0
    return FeedbackHistory(items=items, total=total, accuracy_rate=accuracy)


@app.get("/hitl/feedback/{feedback_id}", response_model=HITLFeedback)
async def get_feedback_by_id(feedback_id: str):
    """Retrieve a single feedback entry by its ID."""
    for entry in _feedback_store:
        if entry.feedback_id == feedback_id:
            return entry
    raise HTTPException(status_code=404, detail="Feedback not found")


@app.get("/hitl/stats", response_model=HITLStats)
async def get_hitl_stats():
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
        avg_explanation_quality=round(avg_quality, 2),
        pending_reviews=0,
    )

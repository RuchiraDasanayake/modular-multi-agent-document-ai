"""
XAI router — Explainable Q&A endpoints (/api/xai).
Provides question-answering with SHAP / LIME explanations.

Delegates to the xai_hitl.engine module for real transformer-based Q&A.
Falls back to demo stubs if the model is unavailable (e.g. CI, light tests).
"""

import logging
import uuid

from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..schemas.xai import (
    QARequest,
    QAResponse,
    XAIExplanation,
    HighlightSpan,
    SHAPExplanation,
    LIMEExplanation,
    DerivationStep,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/xai", tags=["xai"])

# Try to load the real engine; fall back to demo if model unavailable
_real_engine = None
try:
    from xai_hitl.engine import get_engine as _get_engine
    _real_engine = True  # Lazy — will call _get_engine() on first request
    logger.info("XAI: real engine module available")
except ImportError:
    logger.warning("XAI: xai_hitl not found — using demo stubs")


def _demo_explanation(question: str, answer: str, confidence: float) -> XAIExplanation:
    """Build a demo XAI explanation until the real engine is wired in."""
    return XAIExplanation(
        answer=answer,
        confidence_score=confidence,
        highlighted_spans=[
            HighlightSpan(
                start=0, end=min(50, len(answer)),
                text=answer[:50],
                type="answer",
                shap_score=0.85,
                lime_score=0.78,
            ),
        ],
        shap_explanation=SHAPExplanation(
            shap_values=[
                ("finance", 0.45), ("capital", 0.38), ("money", 0.32),
                ("economy", 0.28), ("time", 0.25), ("value", 0.22),
            ],
            base_value=0.5,
        ),
        lime_explanation=LIMEExplanation(
            word_weights=[
                ("finance", 0.42), ("capital", 0.35), ("economy", 0.30),
                ("money", 0.28), ("instruments", 0.22), ("risk", 0.12),
            ],
            prediction_proba=confidence,
        ),
        derivation_steps=[
            DerivationStep(step_number=1, action="Question Analysis", description="Parsed user question", confidence=0.95),
            DerivationStep(step_number=2, action="Context Retrieval", description="Retrieved relevant paragraph sections", confidence=0.90),
            DerivationStep(step_number=3, action="SHAP Analysis", description="Computed feature importance", confidence=0.88),
            DerivationStep(step_number=4, action="LIME Analysis", description="Generated local explanations", confidence=0.85),
            DerivationStep(step_number=5, action="Answer Synthesis", description="Formulated final answer", confidence=confidence),
        ],
        evidence_sentences=[
            "Finance is fundamentally the study of resource allocation over time.",
            "It functions as the circulatory system of the global economy.",
        ],
    )


def _engine_explanation_to_schema(exp) -> XAIExplanation:
    """Convert xai_hitl XAIExplanation dataclass to API schema."""
    # Map engine HighlightType enum values → frontend-compatible type strings
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
                start=s.start, end=s.end, text=s.text,
                type=_HIGHLIGHT_MAP.get(s.highlight_type.value, "medium"),
                shap_score=s.shap_score, lime_score=s.lime_score,
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
                step_number=s.step_number, action=s.action,
                description=s.description, details=s.details,
                confidence=s.confidence,
            )
            for s in exp.derivation_tree.steps
        ],
        evidence_sentences=exp.evidence_sentences,
    )


@router.post("/ask", response_model=QAResponse)
async def ask_question(
    body: QARequest,
    user: dict = Depends(get_current_user),
):
    """Answer a question about a paragraph with XAI analysis."""
    if _real_engine:
        try:
            engine = _get_engine()
            exp = engine.generate_explanation(body.paragraph, body.question)
            schema_exp = _engine_explanation_to_schema(exp)
            return QAResponse(
                answer=exp.answer,
                confidence=exp.confidence_score,
                explanation=schema_exp,
            )
        except Exception as e:
            logger.error("Real engine failed, falling back to demo: %s", e)

    # Demo fallback
    q = body.question.lower()
    if "time value" in q or "dollar" in q:
        answer = "The time value of money asserts that a dollar held today is worth more than a dollar received tomorrow due to its potential earning capacity."
        confidence = 0.92
    elif "function" in q or "core" in q:
        answer = "At its core, finance functions as the circulatory system of the global economy, moving capital from savers and investors to borrowers and entrepreneurs."
        confidence = 0.88
    elif "instrument" in q or "stock" in q or "bond" in q:
        answer = "Financial exchange is mediated by various instruments such as stocks, bonds, and derivatives."
        confidence = 0.90
    else:
        answer = "Finance is the study of resource allocation over time, balancing returns against risk, and functions as the circulatory system of the global economy."
        confidence = 0.75

    return QAResponse(
        answer=answer,
        confidence=confidence,
        explanation=_demo_explanation(body.question, answer, confidence),
    )


@router.get("/explanation/{question_id}", response_model=QAResponse)
async def get_explanation(
    question_id: str,
    user: dict = Depends(get_current_user),
):
    """Retrieve a previously generated explanation by ID."""
    return QAResponse(
        answer="(stored explanation placeholder)",
        confidence=0.5,
        explanation=_demo_explanation("", "(stored explanation placeholder)", 0.5),
    )

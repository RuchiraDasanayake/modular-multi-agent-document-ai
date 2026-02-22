"""
XAI router — Explainable Q&A endpoints (/api/xai).
Provides question-answering with SHAP / LIME explanations.
"""

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

router = APIRouter(prefix="/api/xai", tags=["xai"])


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


@router.post("/ask", response_model=QAResponse)
async def ask_question(
    body: QARequest,
    user: dict = Depends(get_current_user),
):
    """Answer a question about a paragraph with XAI analysis."""
    # TODO: replace demo logic with real XAIEngine integration
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
    # TODO: look up stored explanations by question_id
    return QAResponse(
        answer="(stored explanation placeholder)",
        confidence=0.5,
        explanation=_demo_explanation("", "(stored explanation placeholder)", 0.5),
    )

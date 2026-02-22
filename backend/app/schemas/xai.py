"""XAI schemas — request/response models for explainable Q&A."""

from pydantic import BaseModel


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

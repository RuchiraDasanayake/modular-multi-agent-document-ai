"""
XAI & HITL — Explainable AI Engine + Human-in-the-Loop Feedback
Transformer-based Q&A with SHAP/LIME explanations and human review loop.

Component Owner: Pathirana M.M. (Malith)
"""

__version__ = "1.0.0"

from .engine.xai_engine import (
    XAIEngine,
    XAIExplanation,
    TransformerQAModel,
    get_engine,
    HighlightType,
    TextSpan,
    DerivationStep,
    DerivationTree,
    SHAPExplanation,
    LIMEExplanation,
    ModelPrediction,
)
from .hitl.models import (
    HITLFeedback,
    FeedbackType,
    FeedbackPriority,
)

__all__ = [
    # XAI
    "XAIEngine",
    "XAIExplanation",
    "TransformerQAModel",
    "get_engine",
    "HighlightType",
    "TextSpan",
    "DerivationStep",
    "DerivationTree",
    "SHAPExplanation",
    "LIMEExplanation",
    "ModelPrediction",
    # HITL
    "HITLFeedback",
    "FeedbackType",
    "FeedbackPriority",
]

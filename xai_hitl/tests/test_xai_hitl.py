"""
Tests for XAI engine data classes and HITL models.

NOTE: Full engine tests require the DistilBERT model download (~250 MB).
These tests cover the data model layer and can run without GPU/model.
"""

import pytest

from xai_hitl.engine.xai_engine import (
    HighlightType,
    TextSpan,
    DerivationStep,
    DerivationTree,
    SHAPExplanation,
    LIMEExplanation,
    ModelPrediction,
)
from xai_hitl.hitl.models import (
    HITLFeedback,
    FeedbackType,
    FeedbackPriority,
)

# ═══════════════════════════════════════════════════════════════
# XAI Data Classes
# ═══════════════════════════════════════════════════════════════

def test_text_span_to_dict():
    span = TextSpan(
        text="finance",
        start=0,
        end=7,
        highlight_type=HighlightType.HIGH_IMPORTANCE,
        shap_score=0.9,
        lime_score=0.8,
        combined_score=0.85,
        explanation="High importance",
    )
    d = span.to_dict()
    assert d["text"] == "finance"
    assert d["highlight_type"] == "high_importance"
    assert d["combined_score"] == 0.85

def test_derivation_step_to_dict():
    step = DerivationStep(
        step_number=1,
        action="Tokenize",
        description="Tokenized input",
        details="DistilBERT tokenizer",
        confidence=0.99,
    )
    d = step.to_dict()
    assert d["step_number"] == 1
    assert d["confidence"] == 0.99

def test_derivation_tree_to_dict():
    tree = DerivationTree(
        question="What is finance?",
        steps=[
            DerivationStep(1, "Parse", "Parsed question"),
            DerivationStep(2, "Answer", "Generated answer"),
        ],
        final_answer="Finance is...",
        overall_confidence=0.90,
    )
    d = tree.to_dict()
    assert len(d["steps"]) == 2
    assert d["overall_confidence"] == 0.90

def test_shap_explanation_to_dict():
    shap = SHAPExplanation(
        base_value=0.5,
        shap_values=[("finance", 0.9), ("risk", 0.7)],
        feature_names=["finance", "risk"],
    )
    d = shap.to_dict()
    assert d["base_value"] == 0.5
    assert len(d["shap_values"]) == 2

def test_lime_explanation_to_dict():
    lime = LIMEExplanation(
        word_weights=[("finance", 0.8), ("market", 0.6)],
        prediction_proba=0.85,
    )
    d = lime.to_dict()
    assert d["prediction_proba"] == 0.85

# ═══════════════════════════════════════════════════════════════
# HITL Models
# ═══════════════════════════════════════════════════════════════

def test_feedback_types():
    assert FeedbackType.CORRECT.value == "correct"
    assert FeedbackType.INCORRECT.value == "incorrect"
    assert FeedbackType.XAI_UNCLEAR.value == "xai_unclear"

def test_feedback_priorities():
    assert FeedbackPriority.LOW.value == "low"
    assert FeedbackPriority.CRITICAL.value == "critical"

def test_hitl_feedback_to_dict():
    fb = HITLFeedback(
        feedback_id="fb_001",
        timestamp="2025-01-01T00:00:00",
        question="What is Q?",
        original_answer="A is the answer",
        feedback_type=FeedbackType.CORRECT,
        is_answer_correct=True,
        explanation_quality=4,
        highlight_accuracy=5,
        xai_helpfulness=3,
    )
    d = fb.to_dict()
    assert d["feedback_id"] == "fb_001"
    assert d["feedback_type"] == "correct"
    assert d["ratings"]["explanation_quality"] == 4
    assert d["ratings"]["highlight_accuracy"] == 5

def test_hitl_feedback_from_dict():
    data = {
        "feedback_id": "fb_002",
        "timestamp": "2025-01-01T00:00:00",
        "question": "Q?",
        "original_answer": "A",
        "feedback_type": "incorrect",
        "is_answer_correct": False,
        "corrected_answer": "B",
        "ratings": {
            "explanation_quality": 2,
            "highlight_accuracy": 1,
            "xai_helpfulness": 2,
        },
        "priority": "high",
        "tags": ["important"],
    }
    fb = HITLFeedback.from_dict(data)
    assert fb.feedback_type == FeedbackType.INCORRECT
    assert fb.priority == FeedbackPriority.HIGH
    assert fb.corrected_answer == "B"
    assert fb.tags == ["important"]

def test_hitl_feedback_roundtrip():
    fb = HITLFeedback(
        feedback_id="fb_rt",
        timestamp="2025-06-01T12:00:00",
        question="Test?",
        original_answer="Yes",
        feedback_type=FeedbackType.PARTIALLY_CORRECT,
        is_answer_correct=False,
        corrected_answer="Maybe",
        tags=["test", "roundtrip"],
    )
    d = fb.to_dict()
    fb2 = HITLFeedback.from_dict(d)
    assert fb2.feedback_id == fb.feedback_id
    assert fb2.feedback_type == fb.feedback_type
    assert fb2.corrected_answer == fb.corrected_answer
    assert fb2.tags == fb.tags

"""
XAI Engine for Finance Q&A using Transformer Models + Attention Importance & LIME

Uses a proper transformer-based Q&A model for intelligent reasoning,
with attention-based token importance and LIME for explainability.

Features:
- RoBERTa-base-squad2 for extractive Q&A with unanswerable detection
- Question Decomposition for comparison queries (highest, lowest, etc.)
- Full XAI explanations (SHAP-style attention + LIME) for each sub-query
- Fast mode support for slower machines

Note: The "SHAP" data structures are retained for API compatibility,
but the values represent attention-derived importance scores, not true
Shapley values. LIME explanations use proper perturbation-based local
interpretability.

Model: RoBERTa fine-tuned on SQuAD 2.0 for extractive Q&A

Author: Pathirana M.M. (Malith)
"""

# Disable TensorFlow to avoid conflicts
import os
os.environ['USE_TF'] = '0'
os.environ['USE_TORCH'] = '1'

import numpy as np
from dataclasses import dataclass, field
from typing import Any, cast
from enum import Enum
import re
import logging
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

# Transformer model
from transformers import (
    AutoModelForQuestionAnswering,
    AutoTokenizer,
    pipeline
)
import torch

# XAI Libraries
# NOTE: shap removed — attention weights are used instead of true Shapley values.
# Data structures retain "shap" in names for API backward compatibility.
from lime.lime_text import LimeTextExplainer

# Scikit-learn for additional analysis
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ═══════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════

class HighlightType(Enum):
    """Types of highlights for text spans"""
    HIGH_IMPORTANCE = "high_importance"
    MEDIUM_IMPORTANCE = "medium_importance"
    LOW_IMPORTANCE = "low_importance"
    POSITIVE_CONTRIBUTION = "positive"
    NEGATIVE_CONTRIBUTION = "negative"
    ANSWER_SPAN = "answer_span"

@dataclass
class TextSpan:
    """Represents a highlighted text span with XAI scores"""
    text: str
    start: int
    end: int
    highlight_type: HighlightType
    shap_score: float
    lime_score: float
    combined_score: float
    explanation: str

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "highlight_type": self.highlight_type.value,
            "shap_score": self.shap_score,
            "lime_score": self.lime_score,
            "combined_score": self.combined_score,
            "explanation": self.explanation,
        }

@dataclass
class DerivationStep:
    """Represents a single step in the derivation logic"""
    step_number: int
    action: str
    description: str
    details: str | None = None
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "action": self.action,
            "description": self.description,
            "details": self.details,
            "confidence": self.confidence,
        }

@dataclass
class DerivationTree:
    """Complete derivation logic tree"""
    question: str
    steps: list[DerivationStep]
    final_answer: str
    overall_confidence: float

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "steps": [step.to_dict() for step in self.steps],
            "final_answer": self.final_answer,
            "overall_confidence": self.overall_confidence,
        }

@dataclass
class SHAPExplanation:
    """SHAP-specific explanation data"""
    base_value: float
    shap_values: list[tuple[str, float]]
    feature_names: list[str]

    def to_dict(self) -> dict:
        return {
            "base_value": self.base_value,
            "shap_values": self.shap_values,
            "feature_names": self.feature_names,
        }

@dataclass
class LIMEExplanation:
    """LIME-specific explanation data"""
    word_weights: list[tuple[str, float]]
    prediction_proba: float

    def to_dict(self) -> dict:
        return {
            "word_weights": self.word_weights,
            "prediction_proba": self.prediction_proba,
        }

@dataclass
class ModelPrediction:
    """Transformer model's prediction"""
    answer: str
    confidence: float
    start_index: int
    end_index: int
    top_k_answers: list[dict[str, Any]]
    is_unanswerable: bool = False  # True if model detects question cannot be answered

@dataclass
class SubQuestionResult:
    """Result from a sub-question in question decomposition"""
    sub_question: str
    entity_name: str
    answer: str
    value: float | None  # Numeric value if extracted
    confidence: float
    shap_explanation: SHAPExplanation
    lime_explanation: LIMEExplanation
    derivation_tree: DerivationTree

    def to_dict(self) -> dict:
        return {
            "sub_question": self.sub_question,
            "entity_name": self.entity_name,
            "answer": self.answer,
            "value": self.value,
            "confidence": self.confidence,
            "shap_explanation": self.shap_explanation.to_dict(),
            "lime_explanation": self.lime_explanation.to_dict(),
            "derivation_tree": self.derivation_tree.to_dict(),
        }

@dataclass
class DecomposedExplanation:
    """Explanation for comparison questions using question decomposition"""
    original_question: str
    comparison_type: str  # "highest", "lowest", "most", "least", etc.
    attribute: str  # "coupon rate", "maturity", "price", etc.
    sub_results: list[SubQuestionResult]
    winner: SubQuestionResult | None
    aggregation_logic: str  # Human-readable explanation of how answer was derived
    overall_confidence: float

    def to_dict(self) -> dict:
        return {
            "original_question": self.original_question,
            "comparison_type": self.comparison_type,
            "attribute": self.attribute,
            "sub_results": [r.to_dict() for r in self.sub_results],
            "winner": self.winner.to_dict() if self.winner else None,
            "aggregation_logic": self.aggregation_logic,
            "overall_confidence": self.overall_confidence,
        }

@dataclass
class XAIExplanation:
    """Complete XAI explanation combining SHAP and LIME"""
    paragraph: str
    question: str
    answer: str
    highlighted_spans: list[TextSpan]
    shap_explanation: SHAPExplanation
    lime_explanation: LIMEExplanation
    derivation_tree: DerivationTree
    confidence_score: float
    evidence_sentences: list[str]
    model_prediction: ModelPrediction | None = None
    decomposed_explanation: DecomposedExplanation | None = None  # For comparison questions

    def to_dict(self) -> dict:
        result = {
            "paragraph": self.paragraph,
            "question": self.question,
            "answer": self.answer,
            "highlighted_spans": [span.to_dict() for span in self.highlighted_spans],
            "shap_explanation": self.shap_explanation.to_dict(),
            "lime_explanation": self.lime_explanation.to_dict(),
            "derivation_tree": self.derivation_tree.to_dict(),
            "confidence_score": self.confidence_score,
            "evidence_sentences": self.evidence_sentences,
        }
        if self.model_prediction:
            result["model_prediction"] = {
                "answer": self.model_prediction.answer,
                "confidence": self.model_prediction.confidence,
                "start_index": self.model_prediction.start_index,
                "end_index": self.model_prediction.end_index,
            }
        if self.decomposed_explanation:
            result["decomposed_explanation"] = self.decomposed_explanation.to_dict()
        return result

# ═══════════════════════════════════════════════════════════════
# Transformer Q&A Model
# ═══════════════════════════════════════════════════════════════

class TransformerQAModel:
    """
    Transformer-based Question Answering Model.
    Uses RoBERTa fine-tuned on SQuAD 2.0 for extractive Q&A with unanswerable detection.
    """

    def __init__(self, model_name: str = "deepset/roberta-base-squad2"):
        logger.info("Loading transformer model: %s", model_name)
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        # Use eager attention implementation for faster inference with output_attentions=True
        self.model = AutoModelForQuestionAnswering.from_pretrained(
            model_name,
            attn_implementation="eager"  # Avoid slow fallback for attention extraction
        )
        # SQuAD 2.0 pipeline with handle_impossible_answer for unanswerable detection
        self.qa_pipeline = pipeline(
            "question-answering",
            model=self.model,
            tokenizer=self.tokenizer,
            handle_impossible_answer=True,  # Enable "no answer" detection
        )
        self.no_answer_threshold = 0.5  # Threshold for "no answer" vs real answer
        logger.info("Model loaded successfully (SQuAD 2.0 with unanswerable detection)")

    def predict(self, context: str, question: str, top_k: int = 3) -> ModelPrediction:
        """Get answer prediction from the transformer model.

        RoBERTa-SQuAD2 returns both answer score and no-answer score.
        If no_answer_score > answer_score, the question is likely unanswerable.
        """
        raw_results = self.qa_pipeline(question=question, context=context, top_k=top_k)

        if isinstance(raw_results, dict):
            results = cast(list[dict[str, Any]], [raw_results])
        else:
            results = cast(list[dict[str, Any]], list(raw_results))

        top_answer: dict[str, Any] = results[0]

        # Check if model thinks question is unanswerable
        # Empty answer with very low score indicates unanswerable
        answer_text = str(top_answer.get("answer", "")).strip()
        answer_score = float(top_answer.get("score", 0.0))

        # If answer is empty or score is very low, mark as unanswerable
        is_unanswerable = not answer_text or answer_score < 0.01

        return ModelPrediction(
            answer=answer_text if answer_text else "[NO ANSWER]",
            confidence=answer_score,
            start_index=int(top_answer.get("start", 0)),
            end_index=int(top_answer.get("end", 0)),
            top_k_answers=results,
            is_unanswerable=is_unanswerable,
        )

    def get_token_importance(self, context: str, question: str) -> dict[str, float]:
        """Get token importance scores using attention weights (optimized)."""
        # Truncate context to reduce computation time
        max_context_words = 200
        context_words = context.split()
        if len(context_words) > max_context_words:
            context = " ".join(context_words[:max_context_words])

        inputs = self.tokenizer(
            question, context,
            return_tensors="pt",
            max_length=384,  # Reduced from 512
            truncation=True,
        )

        with torch.no_grad():
            outputs = self.model(**inputs, output_attentions=True)

        # Use last layer attention, averaged across heads
        attention = outputs.attentions[-1].mean(dim=1)[0]
        tokens = self.tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])
        token_importance = attention.mean(dim=0).numpy()

        importance_dict: dict[str, float] = {}
        for token, score in zip(tokens, token_importance):
            clean_token = token.replace("##", "").lower()
            if clean_token not in ["[cls]", "[sep]", "[pad]"] and len(clean_token) > 1:
                if clean_token in importance_dict:
                    importance_dict[clean_token] = max(importance_dict[clean_token], float(score))
                else:
                    importance_dict[clean_token] = float(score)

        return importance_dict

# ═══════════════════════════════════════════════════════════════
# XAI Engine
# ═══════════════════════════════════════════════════════════════

class XAIEngine:
    """
    Explainable AI Engine using Transformer Model + Attention Importance & LIME.

    Pipeline:
    1. Uses RoBERTa-SQuAD2 for intelligent Q&A with unanswerable detection
    2. Uses attention weights for token-level importance scoring
    3. Applies LIME for local interpretable explanations
    4. Builds derivation trees for step-by-step reasoning
    """

    def __init__(self):
        logger.info("Initializing XAI Engine...")
        self.qa_model = TransformerQAModel()
        self.lime_explainer = LimeTextExplainer(
            class_names=["Low Relevance", "High Relevance"],
            split_expression=r"\W+",
            bow=True,
        )
        self.tfidf = TfidfVectorizer(stop_words="english", max_features=1000)
        logger.info("XAI Engine ready")

    # ─── helpers ─────────────────────────────────────────────

    def _split_sentences(self, text: str) -> list[tuple[str, int, int]]:
        sentences = []
        for match in re.finditer(r"[^.!?]*[.!?]+", text):
            sentence = match.group().strip()
            if sentence and len(sentence) > 10:
                sentences.append((sentence, match.start(), match.end()))
        return sentences

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\b\w+\b", text.lower())

    def _get_sentence_relevance_scores(
        self, paragraph: str, question: str
    ) -> list[tuple[str, float]]:
        sentences = [s[0] for s in self._split_sentences(paragraph)]
        if not sentences:
            return []
        # Use TF-IDF cosine similarity for fast sentence relevance instead of
        # running the full QA pipeline per sentence (which was O(n) model calls).
        try:
            corpus = [question] + sentences
            tfidf_matrix = self.tfidf.fit_transform(corpus)
            query_vec = tfidf_matrix[0:1]
            sentence_vecs = tfidf_matrix[1:]
            scores = cosine_similarity(query_vec, sentence_vecs)[0]
            scored = list(zip(sentences, [float(s) for s in scores]))
        except Exception:
            scored = [(s, 0.0) for s in sentences]
        return sorted(scored, key=lambda x: x[1], reverse=True)

    def _create_relevance_predictor(self, paragraph: str, question: str):
        # Cache predictions to avoid re-computing identical perturbations
        _cache: dict[str, list[float]] = {}

        def predict_fn(texts):
            probas = []
            for text in texts:
                cache_key = text[:200]  # truncate key for memory
                if cache_key in _cache:
                    probas.append(_cache[cache_key])
                    continue
                try:
                    ctx = text if len(text) > 10 else paragraph
                    result = cast(dict[str, Any], self.qa_model.qa_pipeline(
                        question=question,
                        context=ctx,
                    ))
                    score = float(result["score"])
                    row = [1 - score, score]
                except Exception:
                    row = [0.5, 0.5]
                _cache[cache_key] = row
                probas.append(row)
            return np.array(probas)
        return predict_fn

    # ─── Attention-Based Token Importance ─────────────────────
    # NOTE: This uses transformer attention weights as a proxy for
    # feature importance. These are NOT true Shapley values (which
    # require coalitional value computation). We retain the SHAP
    # data structure name for API compatibility, but the values
    # represent attention-derived importance scores.

    def _get_shap_explanation(
        self, paragraph: str, question: str, prediction: ModelPrediction
    ) -> SHAPExplanation:
        token_importance = self.qa_model.get_token_importance(paragraph, question)
        shap_values = sorted(
            token_importance.items(), key=lambda x: abs(x[1]), reverse=True
        )[:20]
        if shap_values:
            max_score = max(abs(s) for _, s in shap_values)
            shap_values = [(w, s / max_score) for w, s in shap_values]
        return SHAPExplanation(
            base_value=0.5,
            shap_values=shap_values,
            feature_names=[w for w, _ in shap_values],
        )

    # ─── LIME ────────────────────────────────────────────────

    def _get_lime_explanation(
        self, paragraph: str, question: str, num_features: int = 10
    ) -> LIMEExplanation:
        try:
            predict_fn = self._create_relevance_predictor(paragraph, question)
            # Reduced to 15-20 samples for fast response while maintaining
            # meaningful local explanations. LIME's linear surrogate converges
            # quickly for focused Q&A tasks.
            num_samples = min(20, max(15, len(paragraph.split()) // 5))
            exp = self.lime_explainer.explain_instance(
                paragraph, predict_fn,
                num_features=num_features,
                num_samples=num_samples,
            )
            word_weights = exp.as_list()
            proba = predict_fn([paragraph])[0][1]
            return LIMEExplanation(word_weights=word_weights, prediction_proba=float(proba))
        except Exception as e:
            logger.warning("LIME explanation failed: %s", e)
            return LIMEExplanation(word_weights=[], prediction_proba=0.5)

    # ─── spans ───────────────────────────────────────────────

    def _find_word_spans(self, paragraph: str, word: str) -> list[tuple[int, int]]:
        spans = []
        pattern = r"\b" + re.escape(word) + r"\b"
        for match in re.finditer(pattern, paragraph, re.IGNORECASE):
            spans.append((match.start(), match.end()))
        return spans

    def _calculate_combined_scores(
        self, shap_exp: SHAPExplanation, lime_exp: LIMEExplanation
    ) -> dict[str, dict[str, float]]:
        word_scores: dict[str, dict[str, float]] = {}
        for word, score in shap_exp.shap_values:
            word_scores[word.lower()] = {"shap": score, "lime": 0}
        for word, score in lime_exp.word_weights:
            wl = word.lower()
            if wl in word_scores:
                word_scores[wl]["lime"] = score
            else:
                word_scores[wl] = {"shap": 0, "lime": score}
        return word_scores

    def _create_highlighted_spans(
        self,
        paragraph: str,
        word_scores: dict,
        prediction: ModelPrediction,
    ) -> list[TextSpan]:
        spans: list[TextSpan] = []

        # Answer span from model
        if prediction.answer and prediction.start_index >= 0:
            spans.append(TextSpan(
                text=prediction.answer,
                start=prediction.start_index,
                end=prediction.end_index,
                highlight_type=HighlightType.ANSWER_SPAN,
                shap_score=1.0,
                lime_score=1.0,
                combined_score=1.0,
                explanation=f"Model answer (confidence: {prediction.confidence:.1%})",
            ))

        for word, scores in word_scores.items():
            shap_score = scores.get("shap", 0)
            lime_score = scores.get("lime", 0)
            combined_score = (abs(shap_score) + abs(lime_score)) / 2
            if combined_score < 0.1:
                continue

            for start, end in self._find_word_spans(paragraph, word):
                if prediction.start_index <= start < prediction.end_index:
                    continue
                if prediction.start_index < end <= prediction.end_index:
                    continue

                if combined_score > 0.5:
                    hl_type = HighlightType.HIGH_IMPORTANCE
                elif combined_score > 0.25:
                    hl_type = HighlightType.MEDIUM_IMPORTANCE
                else:
                    hl_type = HighlightType.LOW_IMPORTANCE

                avg_score = (shap_score + lime_score) / 2
                if avg_score > 0.1:
                    hl_type = HighlightType.POSITIVE_CONTRIBUTION
                elif avg_score < -0.1:
                    hl_type = HighlightType.NEGATIVE_CONTRIBUTION

                spans.append(TextSpan(
                    text=paragraph[start:end],
                    start=start,
                    end=end,
                    highlight_type=hl_type,
                    shap_score=shap_score,
                    lime_score=lime_score,
                    combined_score=combined_score,
                    explanation=f"SHAP: {shap_score:.3f}, LIME: {lime_score:.3f}",
                ))

        spans = self._remove_overlapping_spans(spans)
        spans.sort(key=lambda x: x.start)
        return spans

    def _remove_overlapping_spans(self, spans: list[TextSpan]) -> list[TextSpan]:
        if not spans:
            return spans
        spans.sort(key=lambda x: (
            x.highlight_type != HighlightType.ANSWER_SPAN,
            -x.combined_score,
            x.start,
        ))
        result: list[TextSpan] = []
        occupied: set[int] = set()
        for span in spans:
            positions = set(range(span.start, span.end))
            if not positions & occupied:
                result.append(span)
                occupied.update(positions)
        return result

    # ─── answer construction ─────────────────────────────────

    def _validate_answer(self, question: str, answer: str, context: str) -> tuple[bool, str]:
        """Validate if the answer is relevant to the question.

        Returns (is_valid, reason) tuple.
        Detects cases where the model returns irrelevant answers.
        """
        import re
        q_lower = question.lower()
        a_lower = answer.lower().strip()

        # Skip validation for very short or generic answers
        if len(a_lower) < 2:
            return False, "Answer too short"

        # Question type detection and expected answer patterns
        question_patterns = {
            "amount": (["amount", "how much", "price", "cost", "value", "worth"], r'[\$£€]?\s*[\d,]+\.?\d*'),
            "discount": (["discount", "reduction", "off", "savings"], r'[\$£€%]?\s*[\d,]+\.?\d*\s*%?'),
            "tax": (["tax", "vat", "gst"], r'[\$£€%]?\s*[\d,]+\.?\d*\s*%?'),
            "total": (["total", "grand total", "sum", "amount due"], r'[\$£€]?\s*[\d,]+\.?\d*'),
            "subtotal": (["subtotal", "sub-total", "sub total"], r'[\$£€]?\s*[\d,]+\.?\d*'),
            "date": (["date", "when", "due date", "invoice date"], r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|\w+\s+\d{1,2},?\s+\d{4}'),
            "number": (["number", "invoice #", "po #", "order #", "#"], r'[\d\-]+'),
            "name": (["name", "who", "company", "customer", "vendor", "merchant"], r'[A-Za-z\s]+'),
        }

        # Find which question type this is
        detected_type = None
        for qtype, (keywords, _) in question_patterns.items():
            if any(kw in q_lower for kw in keywords):
                detected_type = qtype
                break

        # Check if question keyword exists in context (is the info even there?)
        if detected_type:
            keywords, expected_pattern = question_patterns[detected_type]
            keyword_in_context = any(kw in context.lower() for kw in keywords)

            if not keyword_in_context:
                # The document doesn't even mention this concept
                return False, f"No {detected_type} information found in document"

            # Check if answer matches expected pattern
            if detected_type in ["amount", "discount", "tax", "total", "subtotal"]:
                # For financial questions, answer should contain numbers
                has_numbers = bool(re.search(r'\d', answer))
                if not has_numbers:
                    return False, f"Answer '{answer}' doesn't look like a {detected_type}"

        # Check if answer is just a generic word from the document
        generic_words = ["item", "name", "description", "total", "amount", "date", "price", "quantity",
                        "bill", "invoice", "notes", "terms", "conditions", "thank", "you"]
        if a_lower in generic_words:
            return False, f"Answer '{answer}' is a generic field label, not a value"

        return True, "Valid"

    def _check_unanswerable(self, question: str, answer: str, context: str, confidence: float) -> bool:
        """Determine if the question is unanswerable from the context."""
        import re
        q_lower = question.lower()

        # Keywords that indicate specific fields
        field_keywords = {
            "discount": ["discount", "reduction", "off", "savings", "deduction"],
            "shipping": ["shipping", "delivery", "freight"],
            "deposit": ["deposit", "down payment", "advance"],
            "balance": ["balance", "remaining", "outstanding"],
        }

        for field, keywords in field_keywords.items():
            if any(kw in q_lower for kw in keywords):
                # Check if this field actually exists in the context
                field_in_context = any(kw in context.lower() for kw in keywords)
                if not field_in_context:
                    return True  # Unanswerable

        # If confidence is very low and answer doesn't contain relevant content
        if confidence < 0.15:
            # Check if answer contains any numbers for financial questions
            financial_words = ["total", "amount", "price", "cost", "tax", "discount", "subtotal"]
            if any(fw in q_lower for fw in financial_words):
                if not re.search(r'\d', answer):
                    return True

        return False

    def _boost_confidence(self, prediction: ModelPrediction, context: str, question: str) -> tuple[float, bool]:
        """Boost confidence and detect unanswerable questions.

        Returns (boosted_confidence, is_unanswerable) tuple.
        Uses RoBERTa-SQuAD2's native unanswerable detection + additional validation.
        """
        import re
        answer = prediction.answer.strip()
        base_conf = prediction.confidence

        # Check model's native unanswerable detection (SQuAD 2.0)
        if prediction.is_unanswerable or answer == "[NO ANSWER]":
            logger.debug("Model detected unanswerable question")
            return base_conf, True

        # First validate the answer
        is_valid, reason = self._validate_answer(question, answer, context)
        if not is_valid:
            logger.debug("Answer validation failed: %s", reason)
            return base_conf, True  # Mark as unanswerable

        # Check if question is unanswerable using keyword detection
        if self._check_unanswerable(question, answer, context, base_conf):
            return base_conf, True

        # Check if answer appears in context (exact or partial match)
        answer_in_context = answer.lower() in context.lower()

        # Check if it's a financial value (numbers, currency)
        is_financial = bool(re.search(r'[\$£€]\s*[\d,]+\.?\d*|[\d,]+\.?\d*\s*(?:LKR|USD|EUR|GBP)?', answer))

        # Boost confidence if answer is found and looks valid
        if answer_in_context:
            if is_financial:
                boosted = max(base_conf, 0.75)
            else:
                boosted = max(base_conf, 0.55)
        else:
            answer_nums = re.findall(r'[\d,]+\.?\d*', answer)
            if answer_nums and any(num in context for num in answer_nums):
                boosted = max(base_conf, 0.50)
            else:
                boosted = base_conf

        return boosted, False

    def _construct_answer(
        self,
        prediction: ModelPrediction,
        relevant_sentences: list[tuple[str, float]],
        boosted_confidence: float | None = None,
        is_unanswerable: bool = False,
        question: str = "",
    ) -> str:
        """Build a simple, human-friendly answer."""
        # Handle unanswerable questions
        if is_unanswerable:
            # Extract the field being asked about
            import re
            q_lower = question.lower()
            field_matches = re.findall(r'(?:what(?:\'s| is) (?:the )?|how much is (?:the )?)([\w\s]+?)(?:\?|$)', q_lower)
            if field_matches:
                field = field_matches[0].strip()
                return f"I couldn't find any {field} information in this document."
            return "I couldn't find that information in this document."

        answer = prediction.answer.strip()
        confidence = boosted_confidence if boosted_confidence is not None else prediction.confidence

        # Add natural conversational framing based on confidence
        if confidence >= 0.7:
            return f"The answer is {answer}."
        elif confidence >= 0.5:
            return f"Based on the document, it's {answer}."
        elif confidence >= 0.3:
            return f"I found {answer} in the document."
        else:
            return f"The document shows {answer}."

    # ─── derivation tree ─────────────────────────────────────

    def _build_derivation_tree(
        self,
        question: str,
        answer: str,
        prediction: ModelPrediction,
        shap_exp: SHAPExplanation,
        lime_exp: LIMEExplanation,
    ) -> DerivationTree:
        steps = [
            DerivationStep(1, "📝 Input Tokenization",
                "Tokenized question and context using RoBERTa tokenizer",
                "Model: deepset/roberta-base-squad2 (SQuAD 2.0)", 0.99),
            DerivationStep(2, "🧠 Contextual Encoding",
                "Encoded text through 12 RoBERTa transformer layers with self-attention",
                "Created contextualized representations for each token", 0.95),
            DerivationStep(3, "🎯 Answer Span Prediction",
                f'Identified answer span: "{prediction.answer}"',
                f"Start: position {prediction.start_index}, End: position {prediction.end_index}",
                prediction.confidence),
        ]

        top_shap = shap_exp.shap_values[:5]
        shap_details = ", ".join([f"'{w}': {s:.3f}" for w, s in top_shap])
        steps.append(DerivationStep(4, "🔬 Attention-based SHAP Analysis",
            "Analyzed attention weights for feature importance",
            f"Top features: {shap_details}" if shap_details else "No significant features",
            0.88))

        top_lime = lime_exp.word_weights[:5]
        lime_details = ", ".join([f"'{w}': {s:.3f}" for w, s in top_lime])
        steps.append(DerivationStep(5, "🍋 LIME Local Explanation",
            "Generated local interpretable explanation via perturbation",
            f"Key words: {lime_details}" if lime_details else "No significant words",
            0.85))

        steps.append(DerivationStep(6, "✨ Answer Synthesis",
            "Combined model prediction with XAI insights",
            f"Final confidence: {prediction.confidence:.1%}",
            prediction.confidence))

        overall = 1.0
        for step in steps:
            overall *= step.confidence

        return DerivationTree(
            question=question,
            steps=steps,
            final_answer=answer,
            overall_confidence=round(overall, 4),
        )

    # ─── question decomposition for comparison questions ───────

    def _detect_comparison_question(self, question: str) -> tuple[bool, str | None, str | None]:
        """Detect if this is a comparison question.

        Returns (is_comparison, comparison_type, attribute) tuple.
        Examples:
          - "which bond has highest coupon rate?" → (True, "highest", "coupon rate")
          - "what bond has the lowest maturity?" → (True, "lowest", "maturity")
        """
        q_lower = question.lower().strip()

        # Comparison patterns: which/what [entity] has/with highest/lowest/most/least [attribute]
        comparison_keywords = {
            "highest": "max",
            "highest rate": "max",
            "most": "max",
            "largest": "max",
            "biggest": "max",
            "greatest": "max",
            "best": "max",
            "top": "max",
            "maximum": "max",
            "lowest": "min",
            "least": "min",
            "smallest": "min",
            "minimum": "min",
            "worst": "min",
            "cheapest": "min",
        }

        comparison_type = None
        for keyword, ctype in comparison_keywords.items():
            if keyword in q_lower:
                comparison_type = keyword
                break

        if not comparison_type:
            return False, None, None

        # Extract the attribute being compared
        # Pattern: "highest/lowest [attribute]" or "[attribute] is highest/lowest"
        import re

        # Try to extract attribute after comparison keyword
        pattern = rf'{comparison_type}\s+([\w\s]+?)(?:\?|$|\.)'
        match = re.search(pattern, q_lower)
        if match:
            attribute = match.group(1).strip()
            # Clean up common suffixes
            attribute = re.sub(r'\s*(of all|among|between|in|for).*', '', attribute)
            if attribute:
                return True, comparison_type, attribute

        # Fallback: try common financial attributes
        common_attributes = [
            "coupon rate", "coupon", "rate", "maturity", "yield", "price",
            "face value", "par value", "interest rate", "duration", "principal"
        ]
        for attr in common_attributes:
            if attr in q_lower:
                return True, comparison_type, attr

        return True, comparison_type, "value"  # Default attribute

    def _extract_entities_for_comparison(
        self, paragraph: str, question: str
    ) -> list[str]:
        """Extract entity names from document for comparison.

        Identifies items to compare (e.g., bond names, product names).
        Uses multiple strategies for robust extraction.
        """
        import re
        q_lower = question.lower()

        entities = []
        seen = set()

        # Strategy 1: Bond-specific patterns (various formats)
        bond_patterns = [
            # Sri Lankan Treasury Bond format: 09.00%2028 'A', 11.00%2029 'B'
            r"\d{1,2}\.\d{2}%\d{4}\s*'[A-Z]'",
            # ISIN codes: LKB01628G019
            r'LK[A-Z]\d{8,10}',
            # Sri Lankan bonds: SLGB 2030, SLFB 2027A, TB 2025
            r'(?:SLGB|SLFB|SLB|TB|TBill|T-Bill)\s*\d{2,4}[A-Z]?(?:/\d{2,4})?',
            # Generic bond codes: Bond-2030, BOND2025
            r'(?:Bond|BOND)[\s\-]?\d{2,4}[A-Z]?',
            # Series/Issue identifiers
            r'(?:Series|Issue|Tranche)\s*[A-Z0-9\-]+',
            # Year-based: 2030 Bond, 2025 Treasury
            r'\d{4}\s+(?:Bond|Treasury|Govt|Government)',
            # Maturity-based: 5-Year Bond, 10Y Treasury
            r'\d{1,2}[\-\s]?(?:Year|Yr|Y)\s*(?:Bond|Treasury)?',
        ]

        for pattern in bond_patterns:
            matches = re.findall(pattern, paragraph, re.IGNORECASE)
            for m in matches:
                m_clean = m.strip()
                if m_clean.upper() not in seen and len(m_clean) >= 3:
                    seen.add(m_clean.upper())
                    entities.append(m_clean)

        # Strategy 2: Look for text near "coupon rate" or similar financial terms
        # This captures entities mentioned in context with financial attributes
        context_patterns = [
            r'(\b[A-Z][A-Za-z0-9\-]+(?:\s+\d{4})?)\s*(?:has|with|at|:)\s*(?:a\s+)?(?:coupon|rate|yield)',
            r'(?:coupon|rate|yield)\s*(?:of|for|:)\s*(\b[A-Z][A-Za-z0-9\-]+(?:\s+\d{4})?)',
            r'(\b[A-Z]{2,}\s*\d{2,4})\s*[:\-\|]\s*\d+\.?\d*\s*%',  # "ABC 2030: 12.5%"
        ]
        for pattern in context_patterns:
            matches = re.findall(pattern, paragraph, re.IGNORECASE)
            for m in matches:
                m_clean = m.strip()
                if m_clean.upper() not in seen and len(m_clean) >= 3:
                    seen.add(m_clean.upper())
                    entities.append(m_clean)

        # Strategy 3: Table-like structure detection
        # Look for repeated patterns that suggest tabular data
        # Pattern: Word/Code followed by percentage (common in bond tables)
        table_pattern = r'([A-Z][A-Za-z0-9\s\-]{2,20}?)\s*[\|:\-]?\s*(\d+\.?\d*)\s*%'
        table_matches = re.findall(table_pattern, paragraph)
        for name, _ in table_matches:
            name_clean = name.strip()
            if name_clean.upper() not in seen and len(name_clean) >= 3:
                # Filter out generic words
                if name_clean.lower() not in ['coupon', 'rate', 'yield', 'interest', 'maturity', 'price']:
                    seen.add(name_clean.upper())
                    entities.append(name_clean)

        # Strategy 4: Product/Item patterns (for non-bond documents)
        if "product" in q_lower or "item" in q_lower or not entities:
            product_patterns = [
                r'(?:Item|Product|SKU)\s*[:#]?\s*([\w\-]+)',
                r'(?:Product|Item)\s+([A-Z0-9\-]+)',
            ]
            for pattern in product_patterns:
                matches = re.findall(pattern, paragraph, re.IGNORECASE)
                for m in matches:
                    m_clean = m.strip()
                    if m_clean.upper() not in seen:
                        seen.add(m_clean.upper())
                        entities.append(m_clean)

        # Strategy 5: Fallback - capitalized multi-word phrases (potential entity names)
        if not entities:
            fallback_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
            matches = re.findall(fallback_pattern, paragraph)
            for m in matches[:10]:
                if m.upper() not in seen and len(m) > 5:
                    seen.add(m.upper())
                    entities.append(m)

        logger.info("Extracted %d entities for comparison: %s", len(entities), entities[:5])
        return entities[:10]  # Limit to 10 entities max

    def _generate_sub_question(
        self, original_question: str, entity: str, attribute: str
    ) -> str:
        """Generate a sub-question for a specific entity."""
        # Clean question patterns
        templates = {
            "coupon rate": f"What is the coupon rate of {entity}?",
            "coupon": f"What is the coupon rate of {entity}?",
            "rate": f"What is the rate for {entity}?",
            "maturity": f"What is the maturity date of {entity}?",
            "yield": f"What is the yield of {entity}?",
            "price": f"What is the price of {entity}?",
            "face value": f"What is the face value of {entity}?",
            "par value": f"What is the par value of {entity}?",
            "interest rate": f"What is the interest rate for {entity}?",
            "duration": f"What is the duration of {entity}?",
            "principal": f"What is the principal of {entity}?",
            "total": f"What is the total for {entity}?",
            "amount": f"What is the amount for {entity}?",
        }

        # Use template if available
        attr_lower = attribute.lower()
        if attr_lower in templates:
            return templates[attr_lower]

        # Generic template
        return f"What is the {attribute} of {entity}?"

    def _extract_numeric_value(self, answer: str) -> float | None:
        """Extract numeric value from an answer string."""
        import re

        # Remove currency symbols and common text
        cleaned = re.sub(r'[^\d.,\-%]', ' ', answer)

        # Try to find percentage
        pct_match = re.search(r'([\d.]+)\s*%', answer)
        if pct_match:
            try:
                return float(pct_match.group(1))
            except ValueError:
                pass

        # Try to find number
        num_match = re.search(r'[\d,]+\.?\d*', cleaned)
        if num_match:
            try:
                return float(num_match.group().replace(',', ''))
            except ValueError:
                pass

        return None

    def _run_sub_question_with_xai(
        self, paragraph: str, sub_question: str, entity: str
    ) -> SubQuestionResult:
        """Run a sub-question through the full XAI pipeline."""
        prediction = self.qa_model.predict(paragraph, sub_question)
        boosted_conf, is_unanswerable = self._boost_confidence(
            prediction, paragraph, sub_question
        )

        # Get XAI explanations (respecting fast mode)
        if os.getenv("XAI_FAST_MODE", "true").lower() == "true":
            shap_exp = SHAPExplanation(base_value=0.5, shap_values=[], feature_names=[])
            lime_exp = LIMEExplanation(word_weights=[], prediction_proba=boosted_conf)
            derivation = DerivationTree(
                question=sub_question,
                steps=[
                    DerivationStep(1, "🔍 Sub-Query", f"Extracted info for: {entity}", "RoBERTa-SQuAD2", 0.95),
                    DerivationStep(2, "🎯 Answer", f"Found: {prediction.answer}", f"Confidence: {boosted_conf:.1%}", boosted_conf),
                ],
                final_answer=prediction.answer,
                overall_confidence=boosted_conf,
            )
        else:
            shap_exp = self._get_shap_explanation(paragraph, sub_question, prediction)
            lime_exp = self._get_lime_explanation(paragraph, sub_question)
            derivation = self._build_derivation_tree(
                sub_question, prediction.answer, prediction, shap_exp, lime_exp
            )

        answer = prediction.answer if not is_unanswerable else "Not found"
        value = self._extract_numeric_value(answer) if not is_unanswerable else None

        return SubQuestionResult(
            sub_question=sub_question,
            entity_name=entity,
            answer=answer,
            value=value,
            confidence=boosted_conf if not is_unanswerable else 0.0,
            shap_explanation=shap_exp,
            lime_explanation=lime_exp,
            derivation_tree=derivation,
        )

    def _aggregate_comparison_results(
        self,
        sub_results: list[SubQuestionResult],
        comparison_type: str,
        attribute: str,
    ) -> tuple[SubQuestionResult | None, str]:
        """Aggregate sub-question results to find the winner.

        Returns (winner, explanation_logic) tuple.
        """
        # Filter results with valid numeric values
        valid_results = [r for r in sub_results if r.value is not None and r.confidence > 0.1]

        if not valid_results:
            return None, "Could not extract comparable values from any entities."

        # Determine if we want max or min
        is_max = comparison_type in ["highest", "most", "largest", "biggest", "greatest", "best", "top", "maximum"]

        if is_max:
            winner = max(valid_results, key=lambda r: r.value or 0)
            logic_type = "maximum"
        else:
            winner = min(valid_results, key=lambda r: r.value or 0)
            logic_type = "minimum"

        # Build explanation
        values_str = ", ".join([f"{r.entity_name}: {r.value}" for r in valid_results])
        logic = (
            f"Compared {len(valid_results)} entities by {attribute}. "
            f"Values found: [{values_str}]. "
            f"Selected {logic_type}: {winner.entity_name} with {attribute} = {winner.value}."
        )

        return winner, logic

    def _handle_comparison_question(
        self, paragraph: str, question: str, comparison_type: str, attribute: str
    ) -> XAIExplanation:
        """Handle comparison questions using question decomposition."""
        logger.info("Decomposing comparison question: %s", question[:50])

        # Extract entities to compare
        entities = self._extract_entities_for_comparison(paragraph, question)

        if not entities:
            # No entities found, fall back to regular Q&A
            logger.info("No entities found for comparison, falling back to regular Q&A")
            return self._generate_regular_explanation(paragraph, question)

        logger.info("Found %d entities for comparison: %s", len(entities), entities)

        # Generate and run sub-questions for each entity
        sub_results: list[SubQuestionResult] = []
        for entity in entities:
            sub_q = self._generate_sub_question(question, entity, attribute)
            logger.debug("Sub-question for %s: %s", entity, sub_q)
            result = self._run_sub_question_with_xai(paragraph, sub_q, entity)
            sub_results.append(result)
            logger.debug("  -> Answer: %s (value=%s, conf=%.2f)", result.answer, result.value, result.confidence)

        # Aggregate results
        winner, aggregation_logic = self._aggregate_comparison_results(
            sub_results, comparison_type, attribute
        )

        # Build decomposed explanation
        avg_confidence = sum(r.confidence for r in sub_results) / len(sub_results) if sub_results else 0.0
        decomposed = DecomposedExplanation(
            original_question=question,
            comparison_type=comparison_type,
            attribute=attribute,
            sub_results=sub_results,
            winner=winner,
            aggregation_logic=aggregation_logic,
            overall_confidence=winner.confidence if winner else 0.0,
        )

        # Construct final answer
        if winner:
            answer = f"{winner.entity_name} has the {comparison_type} {attribute} at {winner.value}."
            confidence = winner.confidence
        else:
            answer = f"I couldn't compare the {attribute} across the entities in this document."
            confidence = -1.0  # Hide confidence for failed comparisons

        # Build combined derivation tree showing the decomposition
        steps = [
            DerivationStep(1, "🔄 Question Decomposition",
                f"Detected comparison question asking for {comparison_type} {attribute}",
                f"Identified {len(entities)} entities to compare", 0.95),
        ]
        for i, r in enumerate(sub_results, 2):
            steps.append(DerivationStep(i, f"📊 Sub-Query: {r.entity_name}",
                f"Q: {r.sub_question}",
                f"A: {r.answer} (value={r.value})", r.confidence))

        steps.append(DerivationStep(len(sub_results) + 2, "🏆 Aggregation",
            aggregation_logic,
            f"Winner: {winner.entity_name}" if winner else "No winner determined",
            winner.confidence if winner else 0.0))

        derivation = DerivationTree(
            question=question,
            steps=steps,
            final_answer=answer,
            overall_confidence=confidence if confidence > 0 else 0.0,
        )

        # Combined SHAP/LIME from all sub-results
        all_shap_values = []
        all_lime_weights = []
        for r in sub_results:
            all_shap_values.extend(r.shap_explanation.shap_values)
            all_lime_weights.extend(r.lime_explanation.word_weights)

        return XAIExplanation(
            paragraph=paragraph,
            question=question,
            answer=answer,
            highlighted_spans=[],
            shap_explanation=SHAPExplanation(
                base_value=0.5,
                shap_values=all_shap_values[:20],
                feature_names=[w for w, _ in all_shap_values[:20]],
            ),
            lime_explanation=LIMEExplanation(
                word_weights=all_lime_weights[:10],
                prediction_proba=avg_confidence,
            ),
            derivation_tree=derivation,
            confidence_score=confidence,
            evidence_sentences=[],
            model_prediction=None,
            decomposed_explanation=decomposed,
        )

    def _generate_regular_explanation(self, paragraph: str, question: str) -> XAIExplanation:
        """Generate regular (non-comparison) explanation. Extracted for reuse."""
        prediction = self.qa_model.predict(paragraph, question)
        logger.debug("Answer: '%s' (raw %.1f%%)", prediction.answer, prediction.confidence * 100)

        boosted_conf, is_unanswerable = self._boost_confidence(prediction, paragraph, question)
        logger.debug("Boosted confidence: %.1f%%, Unanswerable: %s", boosted_conf * 100, is_unanswerable)

        relevant_sentences = self._get_sentence_relevance_scores(paragraph, question)
        evidence = [s for s, score in relevant_sentences if score > 0.01][:3]

        answer = self._construct_answer(prediction, relevant_sentences, boosted_conf, is_unanswerable, question)

        if is_unanswerable:
            logger.info("Question unanswerable: %s", question[:50])
            return XAIExplanation(
                paragraph=paragraph,
                question=question,
                answer=answer,
                highlighted_spans=[],
                shap_explanation=SHAPExplanation(base_value=0.5, shap_values=[], feature_names=[]),
                lime_explanation=LIMEExplanation(word_weights=[], prediction_proba=0.0),
                derivation_tree=DerivationTree(
                    question=question, steps=[], final_answer=answer, overall_confidence=0.0
                ),
                confidence_score=-1.0,
                evidence_sentences=[],
                model_prediction=prediction,
            )

        if os.getenv("XAI_FAST_MODE", "true").lower() == "true":
            logger.info("Fast mode: skipping SHAP/LIME explanations")
            shap_exp = SHAPExplanation(base_value=0.5, shap_values=[], feature_names=[])
            lime_exp = LIMEExplanation(word_weights=[], prediction_proba=boosted_conf)
            spans = []
            derivation = DerivationTree(
                question=question,
                steps=[
                    DerivationStep(1, "📝 Question Analysis", f"Analyzed: {question[:50]}...", "RoBERTa-SQuAD2", 0.95),
                    DerivationStep(2, "🎯 Answer Extraction", f"Found answer: {answer}", f"Confidence: {boosted_conf:.1%}", boosted_conf),
                ],
                final_answer=answer,
                overall_confidence=boosted_conf,
            )
        else:
            shap_exp = self._get_shap_explanation(paragraph, question, prediction)
            logger.debug("SHAP features: %d", len(shap_exp.shap_values))

            lime_exp = self._get_lime_explanation(paragraph, question)
            logger.debug("LIME features: %d", len(lime_exp.word_weights))

            word_scores = self._calculate_combined_scores(shap_exp, lime_exp)
            spans = self._create_highlighted_spans(paragraph, word_scores, prediction)
            logger.debug("Highlighted spans: %d", len(spans))

            derivation = self._build_derivation_tree(question, answer, prediction, shap_exp, lime_exp)

        logger.info("Explanation complete for: %s", question[:50])

        return XAIExplanation(
            paragraph=paragraph,
            question=question,
            answer=answer,
            highlighted_spans=spans,
            shap_explanation=shap_exp,
            lime_explanation=lime_exp,
            derivation_tree=derivation,
            confidence_score=boosted_conf,
            evidence_sentences=evidence,
            model_prediction=prediction,
        )

    # ─── conversational handling ──────────────────────────────

    def _handle_conversation(self, question: str) -> str | None:
        """Handle greetings and common conversational phrases."""
        q = question.lower().strip()

        # Greetings
        greetings = ['hello', 'hi', 'hey', 'good morning', 'good afternoon',
                     'good evening', 'howdy', 'greetings', 'hola']
        if any(q.startswith(g) or q == g for g in greetings):
            return "Hello! I'm your document assistant. Ask me anything about this document - like prices, dates, totals, or any other details you need."

        # How are you
        if any(phrase in q for phrase in ['how are you', 'how r u', "how's it going", 'whats up', "what's up"]):
            return "I'm doing great, thanks for asking! Ready to help you with any questions about your document."

        # Thanks
        if q in ['thanks', 'thank you', 'thx', 'ty'] or q.startswith('thanks ') or q.startswith('thank you'):
            return "You're welcome! Let me know if you have any other questions about the document."

        # Help
        if q in ['help', 'help me'] or any(p in q for p in ['what can you do', 'what do you do', 'how can you help']):
            return "I can help you find information in your document. Try asking questions like 'What is the total?', 'What's the date?', or 'Who is the vendor?'"

        # Goodbye
        if any(phrase in q for phrase in ['bye', 'goodbye', 'see you', 'later', 'exit', 'quit']):
            return "Goodbye! Feel free to come back if you have more questions."

        # Who are you
        if any(phrase in q for phrase in ['who are you', 'what are you', 'your name']):
            return "I'm an AI document assistant. I can analyze documents and answer your questions about their content."

        return None  # Not a conversational message

    # ─── main entry point ────────────────────────────────────

    def generate_explanation(self, paragraph: str, question: str) -> XAIExplanation:
        """Generate complete XAI explanation using Transformer + SHAP + LIME.

        For comparison questions (highest, lowest, etc.), uses Question Decomposition
        to break down into sub-questions with full XAI for each, then aggregates.
        """
        logger.info("Processing question: %s", question)

        # Check for conversational messages first
        conv_response = self._handle_conversation(question)
        if conv_response:
            logger.info("Handled as conversation: %s", question[:30])
            return XAIExplanation(
                paragraph=paragraph,
                question=question,
                answer=conv_response,
                highlighted_spans=[],
                shap_explanation=SHAPExplanation(base_value=0.5, shap_values=[], feature_names=[]),
                lime_explanation=LIMEExplanation(word_weights=[], prediction_proba=1.0),
                derivation_tree=DerivationTree(
                    question=question, steps=[], final_answer=conv_response, overall_confidence=1.0
                ),
                confidence_score=-1.0,  # Negative = don't show confidence
                evidence_sentences=[],
                model_prediction=None,
            )

        # Check for comparison questions (highest, lowest, most, least, etc.)
        is_comparison, comparison_type, attribute = self._detect_comparison_question(question)
        if is_comparison and comparison_type and attribute:
            logger.info("Detected comparison question: type=%s, attribute=%s", comparison_type, attribute)
            return self._handle_comparison_question(paragraph, question, comparison_type, attribute)

        # Regular question - use standard Q&A pipeline
        return self._generate_regular_explanation(paragraph, question)

# ═══════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════

_engine_instance: XAIEngine | None = None

def get_engine() -> XAIEngine:
    """Lazy-load singleton XAI engine."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = XAIEngine()
    return _engine_instance

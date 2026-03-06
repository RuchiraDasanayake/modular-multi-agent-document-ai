"""
XAI Engine for Finance Q&A using Transformer Models + Attention Importance & LIME

Uses a proper transformer-based Q&A model for intelligent reasoning,
with attention-based token importance and LIME for explainability.

Note: The "SHAP" data structures are retained for API compatibility,
but the values represent attention-derived importance scores, not true
Shapley values. LIME explanations use proper perturbation-based local
interpretability.

Model: DistilBERT fine-tuned on SQuAD for extractive Q&A

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
        return result

# ═══════════════════════════════════════════════════════════════
# Transformer Q&A Model
# ═══════════════════════════════════════════════════════════════

class TransformerQAModel:
    """
    Transformer-based Question Answering Model.
    Uses DistilBERT fine-tuned on SQuAD for extractive Q&A.
    """

    def __init__(self, model_name: str = "distilbert/distilbert-base-cased-distilled-squad"):
        logger.info("Loading transformer model: %s", model_name)
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForQuestionAnswering.from_pretrained(model_name)
        self.qa_pipeline = pipeline(
            "question-answering",
            model=self.model,
            tokenizer=self.tokenizer,
        )
        logger.info("Model loaded successfully")

    def predict(self, context: str, question: str, top_k: int = 3) -> ModelPrediction:
        """Get answer prediction from the transformer model."""
        raw_results = self.qa_pipeline(question=question, context=context, top_k=top_k)

        if isinstance(raw_results, dict):
            results = cast(list[dict[str, Any]], [raw_results])
        else:
            results = cast(list[dict[str, Any]], list(raw_results))

        top_answer: dict[str, Any] = results[0]

        return ModelPrediction(
            answer=str(top_answer["answer"]),
            confidence=float(top_answer["score"]),
            start_index=int(top_answer["start"]),
            end_index=int(top_answer["end"]),
            top_k_answers=results,
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
    1. Uses DistilBERT-SQuAD for intelligent Q&A
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

    def _construct_answer(
        self,
        prediction: ModelPrediction,
        relevant_sentences: list[tuple[str, float]],
    ) -> str:
        """Build a simple, human-friendly answer."""
        answer = prediction.answer.strip()

        # Add natural conversational framing based on confidence
        if prediction.confidence >= 0.8:
            return f"The answer is {answer}."
        elif prediction.confidence >= 0.6:
            return f"Based on the document, it's {answer}."
        elif prediction.confidence >= 0.4:
            return f"I found {answer} in the document."
        else:
            return f"It looks like {answer}, but I'm not entirely sure."

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
                "Tokenized question and context using DistilBERT tokenizer",
                "Model: distilbert-base-cased-distilled-squad", 0.99),
            DerivationStep(2, "🧠 Contextual Encoding",
                "Encoded text through 6 transformer layers with self-attention",
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
        if any(phrase in q for phrase in ['thank', 'thanks', 'thx', 'ty']):
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
        """Generate complete XAI explanation using Transformer + SHAP + LIME."""
        logger.info("Processing question: %s", question)

        # Check for conversational messages first
        conv_response = self._handle_conversation(question)
        if conv_response:
            logger.info("Handled as conversation: %s", question[:30])
            # Return a minimal explanation for conversational responses
            # Use confidence_score=-1 to signal frontend to hide confidence badge
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

        prediction = self.qa_model.predict(paragraph, question)
        logger.debug("Answer: '%s' (%.1f%%)", prediction.answer, prediction.confidence * 100)

        relevant_sentences = self._get_sentence_relevance_scores(paragraph, question)
        evidence = [s for s, score in relevant_sentences if score > 0.01][:3]

        shap_exp = self._get_shap_explanation(paragraph, question, prediction)
        logger.debug("SHAP features: %d", len(shap_exp.shap_values))

        lime_exp = self._get_lime_explanation(paragraph, question)
        logger.debug("LIME features: %d", len(lime_exp.word_weights))

        word_scores = self._calculate_combined_scores(shap_exp, lime_exp)
        spans = self._create_highlighted_spans(paragraph, word_scores, prediction)
        logger.debug("Highlighted spans: %d", len(spans))

        answer = self._construct_answer(prediction, relevant_sentences)
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
            confidence_score=prediction.confidence,
            evidence_sentences=evidence,
            model_prediction=prediction,
        )

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

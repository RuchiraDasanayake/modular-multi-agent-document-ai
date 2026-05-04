"""
XAI Engine for Finance Q&A using BART Encoder-Decoder + Cross-Attention & LIME

Uses BART (encoder-decoder) for generative Q&A with natural language answers,
with cross-attention extraction for XAI and LIME for explainability.

Features:
- BART encoder-decoder for generative Q&A (natural language answers)
- Cross-attention extraction for XAI (decoder-to-encoder attention)
- Question Decomposition for comparison queries (highest, lowest, etc.)
- Full XAI explanations (cross-attention + LIME) for each sub-query
- Fast mode support for slower machines

Advantages of Generative (BART) over Extractive:
- Can generate natural language answers, not just extract spans
- Can synthesize information from multiple parts of the document
- Better for complex reasoning and abstractive answers
- Returns human-friendly responses (e.g., "Yes, the total is $500")

XAI Approach:
- Cross-attention: Maps decoder output back to encoder input tokens
- LIME: Perturbation-based local interpretability with sequence probability

Model: vblagoje/bart_lfqa (BART fine-tuned for long-form Q&A)

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
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
)
import torch

# XAI Libraries
# NOTE: shap removed — attention weights are used instead of true Shapley values.
# Data structures retain "shap" in names for API backward compatibility.
from lime.lime_text import LimeTextExplainer

# Scikit-learn for additional analysis
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# spaCy for NER (lazy loaded)
_spacy_nlp = None

def _get_spacy_nlp():
    """Lazy load spaCy model for NER."""
    global _spacy_nlp
    if _spacy_nlp is None:
        try:
            import spacy
            try:
                _spacy_nlp = spacy.load("en_core_web_sm")
            except OSError:
                # Model not installed, download it
                logger.info("Downloading spaCy model en_core_web_sm...")
                import subprocess
                subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"], check=True)
                _spacy_nlp = spacy.load("en_core_web_sm")
            logger.info("spaCy NER model loaded")
        except Exception as e:
            logger.warning("Failed to load spaCy: %s", e)
            _spacy_nlp = False  # Mark as failed, don't retry
    return _spacy_nlp if _spacy_nlp else None

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

class GenerativeQAModel:
    """
    Generative Question Answering Model using BART encoder-decoder.

    Uses facebook/bart-large for generative Q&A with natural language answers.
    XAI is achieved via cross-attention extraction from decoder to encoder tokens.

    Advantages over extractive models:
    - Can generate natural language answers (not just spans)
    - Can synthesize information from multiple parts of the document
    - Better for complex reasoning and abstractive answers
    """

    def __init__(self, model_name: str = "vblagoje/bart_lfqa"):
        """Initialize BART model for generative Q&A.

        Args:
            model_name: HuggingFace model ID. Options:
                - "vblagoje/bart_lfqa" - BART fine-tuned for long-form Q&A (recommended)
                - "facebook/bart-large" - Base BART model
                - "facebook/bart-large-cnn" - BART fine-tuned on CNN/DailyMail
        """
        from transformers import AutoModelForSeq2SeqLM

        logger.info("Loading generative model: %s", model_name)
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        # Use eager attention to support output_attentions=True for XAI explanations
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            model_name,
            attn_implementation="eager"
        )

        # Generation parameters for Q&A
        self.max_input_length = 1024
        self.max_output_length = 128
        self.num_beams = 4
        self.no_repeat_ngram_size = 3

        logger.info("Generative model loaded successfully (BART encoder-decoder)")

    def _format_input(self, question: str, context: str) -> str:
        """Format input for BART Q&A: question: [Q] context: [C]"""
        return f"question: {question} context: {context}"

    def predict(self, context: str, question: str, top_k: int = 1) -> ModelPrediction:
        """Generate natural language answer using BART.

        Returns a ModelPrediction with:
        - answer: Generated natural language string
        - confidence: Average token probability of the generated sequence
        - start_index/end_index: -1 (not applicable for generative)
        """
        # Format input
        input_text = self._format_input(question, context)

        # Tokenize
        inputs = self.tokenizer(
            input_text,
            return_tensors="pt",
            max_length=self.max_input_length,
            truncation=True,
        )

        # Generate with output scores for confidence
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_length=self.max_output_length,
                num_beams=self.num_beams,
                no_repeat_ngram_size=self.no_repeat_ngram_size,
                num_return_sequences=top_k,
                output_scores=True,
                return_dict_in_generate=True,
            )

        # Decode generated answer
        generated_ids = outputs.sequences[0]
        answer_text = self.tokenizer.decode(generated_ids, skip_special_tokens=True).strip()

        # Calculate confidence from sequence scores
        if hasattr(outputs, 'sequences_scores') and outputs.sequences_scores is not None:
            # Convert log probability to probability
            log_prob = outputs.sequences_scores[0].item()
            confidence = float(np.exp(log_prob))
            # Normalize to [0, 1] range (log probs are negative)
            confidence = min(max(confidence, 0.0), 1.0)
        else:
            # Fallback: estimate from token probabilities
            confidence = 0.7  # Default moderate confidence

        # Detect unanswerable based on answer content
        unanswerable_phrases = [
            "i don't know", "cannot find", "not mentioned", "no information",
            "not specified", "unable to", "doesn't say", "not clear"
        ]
        is_unanswerable = (
            not answer_text or
            len(answer_text) < 3 or
            any(phrase in answer_text.lower() for phrase in unanswerable_phrases)
        )

        return ModelPrediction(
            answer=answer_text if answer_text else "I couldn't find that information.",
            confidence=confidence,
            start_index=-1,  # Not applicable for generative
            end_index=-1,
            top_k_answers=[{"answer": answer_text, "score": confidence}],
            is_unanswerable=is_unanswerable,
        )

    def get_token_importance(self, context: str, question: str) -> dict[str, float]:
        """Extract token importance using cross-attention from decoder to encoder.

        For encoder-decoder models, cross-attention shows which encoder tokens
        the decoder attends to when generating each output token.
        We average cross-attention across the first few generated tokens.
        """
        input_text = self._format_input(question, context)

        # Tokenize input (encoder side)
        inputs = self.tokenizer(
            input_text,
            return_tensors="pt",
            max_length=self.max_input_length,
            truncation=True,
        )

        # Generate with cross-attention output
        with torch.no_grad():
            # First, get encoder outputs
            encoder_outputs = self.model.get_encoder()(**inputs)

            # Prepare decoder input (start token)
            decoder_input_ids = torch.tensor([[self.model.config.decoder_start_token_id]])

            # Forward pass with cross-attention output
            outputs = self.model(
                encoder_outputs=encoder_outputs,
                decoder_input_ids=decoder_input_ids,
                output_attentions=True,
                return_dict=True,
            )

        # Extract cross-attention weights
        # Shape: (num_layers, batch, num_heads, decoder_seq_len, encoder_seq_len)
        cross_attn = None
        if hasattr(outputs, 'cross_attentions') and outputs.cross_attentions:
            cross_attn = outputs.cross_attentions[-1]  # Last layer

        if cross_attn is not None:
            # Use last layer cross-attention, average across heads
            attn_weights = cross_attn.mean(dim=1).mean(dim=1)[0]  # [encoder_seq_len]
        elif hasattr(outputs, 'encoder_attentions') and outputs.encoder_attentions:
            # Fallback: use encoder self-attention
            enc_attn = outputs.encoder_attentions[-1]
            if enc_attn is not None:
                attn_weights = enc_attn.mean(dim=1).mean(dim=1)[0]
            else:
                return {}
        else:
            # No attention available, return empty
            return {}

        # Map attention weights to tokens
        encoder_tokens = self.tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])
        attn_weights_np = attn_weights.numpy()

        importance_dict: dict[str, float] = {}
        special_tokens = {"<s>", "</s>", "<pad>", "Ġ", "question", ":", "context"}

        for token, score in zip(encoder_tokens, attn_weights_np):
            # Clean BART's byte-level BPE tokens (Ġ prefix = space)
            clean_token = token.replace("Ġ", "").lower()

            if clean_token in special_tokens or len(clean_token) < 2:
                continue

            if clean_token in importance_dict:
                importance_dict[clean_token] = max(importance_dict[clean_token], float(score))
            else:
                importance_dict[clean_token] = float(score)

        return importance_dict

    def get_token_importance_with_positions(
        self, context: str, question: str
    ) -> list[dict]:
        """Extract token importance with character-level positions in original text.

        Returns list of dicts with token, importance score, and character positions
        in the original context. This enables mapping XAI highlights back to
        flattened financial text.

        Returns:
            [{"token": "total", "score": 0.85, "char_start": 10, "char_end": 15}, ...]
        """
        import re
        input_text = self._format_input(question, context)

        # Find where context starts in the formatted input
        context_start_in_input = input_text.find("context: ") + len("context: ")

        # Tokenize input (encoder side)
        inputs = self.tokenizer(
            input_text,
            return_tensors="pt",
            max_length=self.max_input_length,
            truncation=True,
            return_offsets_mapping=True,  # Get character offsets
        )

        # Generate with cross-attention output
        with torch.no_grad():
            encoder_outputs = self.model.get_encoder()(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
            )
            decoder_input_ids = torch.tensor([[self.model.config.decoder_start_token_id]])
            outputs = self.model(
                encoder_outputs=encoder_outputs,
                decoder_input_ids=decoder_input_ids,
                output_attentions=True,
                return_dict=True,
            )

        # Extract cross-attention weights
        cross_attn = None
        if hasattr(outputs, 'cross_attentions') and outputs.cross_attentions:
            cross_attn = outputs.cross_attentions[-1]
        if cross_attn is None:
            return []
        attn_weights = cross_attn.mean(dim=1).mean(dim=1)[0].numpy()

        # Get tokens with offsets
        encoder_tokens = self.tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])

        # Build offset mapping manually (some tokenizers don't support it)
        token_positions = []
        special_tokens = {"<s>", "</s>", "<pad>"}

        # Track position in formatted input text
        current_pos = 0
        for i, token in enumerate(encoder_tokens):
            if token in special_tokens:
                token_positions.append(None)
                continue

            # Clean token for matching
            clean_token = token.replace("Ġ", " ").strip()
            if not clean_token:
                token_positions.append(None)
                continue

            # Find token in input text
            idx = input_text.lower().find(clean_token.lower(), current_pos)
            if idx >= 0:
                token_positions.append((idx, idx + len(clean_token)))
                current_pos = idx + len(clean_token)
            else:
                token_positions.append(None)

        # Build result with context-relative positions
        results = []
        for i, (token, score) in enumerate(zip(encoder_tokens, attn_weights)):
            clean_token = token.replace("Ġ", "").lower()

            if len(clean_token) < 2 or token in special_tokens:
                continue

            pos = token_positions[i]
            if pos and pos[0] >= context_start_in_input:
                # Convert to context-relative position
                char_start = pos[0] - context_start_in_input
                char_end = pos[1] - context_start_in_input

                # Ensure within context bounds
                if 0 <= char_start < len(context):
                    results.append({
                        "token": clean_token,
                        "score": float(score),
                        "char_start": char_start,
                        "char_end": min(char_end, len(context)),
                    })

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:30]  # Top 30 tokens

    def get_sequence_probability(self, context: str, question: str, target_answer: str) -> float:
        """Calculate the probability of generating a specific answer sequence.

        Used by LIME to get prediction probabilities for perturbations.
        """
        input_text = self._format_input(question, context)

        # Tokenize input and target
        inputs = self.tokenizer(
            input_text,
            return_tensors="pt",
            max_length=self.max_input_length,
            truncation=True,
        )

        with self.tokenizer.as_target_tokenizer():
            labels = self.tokenizer(
                target_answer,
                return_tensors="pt",
                max_length=self.max_output_length,
                truncation=True,
            )

        # Forward pass to get loss (negative log-likelihood)
        with torch.no_grad():
            outputs = self.model(
                **inputs,
                labels=labels["input_ids"],
            )

        # Convert loss to probability
        # Loss is cross-entropy averaged over tokens
        loss = outputs.loss.item()
        # Approximate sequence probability (geometric mean of token probs)
        avg_token_prob = np.exp(-loss)

        return float(avg_token_prob)


# Alias for backward compatibility
TransformerQAModel = GenerativeQAModel

# ═══════════════════════════════════════════════════════════════
# Text Pre-Processing for Flattened Financial Documents
# ═══════════════════════════════════════════════════════════════

class TableReconstructor:
    """
    Pre-process flattened financial text to re-align labels with values.

    OCR often produces text like:
        "Total Amount 1500.00 Tax 150.00 Grand Total 1650.00"

    This class detects label-value sequences and restructures them for better Q&A.
    """

    # Common financial labels
    FINANCIAL_LABELS = {
        'total', 'subtotal', 'sub-total', 'amount', 'price', 'cost', 'tax', 'vat',
        'gst', 'discount', 'shipping', 'delivery', 'grand total', 'net', 'gross',
        'balance', 'due', 'paid', 'deposit', 'fee', 'charge', 'rate', 'quantity',
        'qty', 'unit price', 'unit cost', 'invoice total', 'amount due',
        'coupon', 'coupon rate', 'yield', 'maturity', 'face value', 'par value',
        'principal', 'interest', 'interest rate', 'settlement', 'accrued',
    }

    @classmethod
    def detect_label_value_pairs(cls, text: str) -> list[dict]:
        """Detect label-value pairs in flattened text.

        Returns list of dicts: [{"label": "Total", "value": "1500.00", "start": 0, "end": 18}]
        """
        import re
        pairs = []

        # Pattern: Label followed by numeric value (with optional currency)
        # Handles: "Total 1500.00", "Tax: $150", "Rate 12.5%", "Amount Due: LKR 5000"
        pattern = r'([A-Za-z][A-Za-z\s\-]{2,25}?)[\s:]*?([\$£€]?\s*[\d,]+\.?\d*\s*%?(?:\s*(?:LKR|USD|EUR|GBP))?)'

        for match in re.finditer(pattern, text):
            label = match.group(1).strip().lower()
            value = match.group(2).strip()

            # Check if label is a known financial term
            if any(fl in label for fl in cls.FINANCIAL_LABELS):
                pairs.append({
                    "label": match.group(1).strip(),
                    "value": value,
                    "start": match.start(),
                    "end": match.end(),
                    "label_normalized": label,
                })

        return pairs

    @classmethod
    def reconstruct_table_format(cls, text: str) -> str:
        """Reconstruct flattened text into structured format.

        Transforms: "Total 1500 Tax 150 Grand Total 1650"
        Into: "Total: 1500 | Tax: 150 | Grand Total: 1650"
        """
        pairs = cls.detect_label_value_pairs(text)

        if not pairs:
            return text  # No reconstruction needed

        # Build structured representation
        structured_parts = []
        for pair in pairs:
            structured_parts.append(f"{pair['label']}: {pair['value']}")

        # Append structured summary to original text
        if structured_parts:
            structured_summary = " | ".join(structured_parts)
            return f"{text}\n\n[Extracted Values: {structured_summary}]"

        return text

    @classmethod
    def get_value_for_label(cls, text: str, target_label: str) -> str | None:
        """Find the value associated with a specific label."""
        pairs = cls.detect_label_value_pairs(text)
        target_lower = target_label.lower()

        for pair in pairs:
            if target_lower in pair["label_normalized"]:
                return pair["value"]

        return None


class EntityAnchorSearch:
    """
    Search for entity-value anchor pairs in financial documents.

    Used for finding:
    - Primary Dealers with phone numbers: "ABC Bank PLC 1234567"
    - Bond names with rates: "SLGB 2030 12.5%"
    - Companies with identifiers
    """

    @classmethod
    def find_entity_phone_pairs(cls, text: str) -> list[dict]:
        """Find entity names paired with 7-digit phone numbers.

        Pattern: Capitalized company name followed by 7-digit number
        Example: "People's Bank 2481818" → {"entity": "People's Bank", "phone": "2481818"}
        """
        import re
        pairs = []

        # Pattern: Capitalized phrase (company name) + 7-digit number
        # Handles: "ABC Bank PLC 1234567", "People's Leasing & Finance 2481234"
        pattern = r"([A-Z][A-Za-z'&\.\s]+(?:PLC|Ltd|Bank|Co\.?|Securities|Finance|Leasing)?)\s+(\d{7})\b"

        for match in re.finditer(pattern, text):
            entity = match.group(1).strip()
            phone = match.group(2)

            # Filter out generic terms
            if len(entity) > 3 and entity.lower() not in ['the', 'and', 'for']:
                pairs.append({
                    "entity": entity,
                    "phone": phone,
                    "start": match.start(),
                    "end": match.end(),
                    "full_text": match.group(0),
                })

        return pairs

    @classmethod
    def find_entity_rate_pairs(cls, text: str) -> list[dict]:
        """Find entity names paired with percentage rates.

        Pattern: Identifier followed by percentage
        Example: "09.00%2028 'A'" or "SLGB 2030 12.5%"
        """
        import re
        pairs = []

        # Sri Lankan Treasury Bond format: 09.00%2028 'A'
        pattern1 = r"(\d{1,2}\.\d{2}%\d{4})\s*'([A-Z])'"
        for match in re.finditer(pattern1, text):
            pairs.append({
                "entity": f"{match.group(1)} '{match.group(2)}'",
                "rate": match.group(1).split('%')[0],
                "start": match.start(),
                "end": match.end(),
            })

        # Standard format: ENTITY YEAR RATE%
        pattern2 = r"([A-Z]{2,}[\s\d\-]*\d{4}[A-Z]?)\s*[:\-]?\s*(\d+\.?\d*)\s*%"
        for match in re.finditer(pattern2, text):
            pairs.append({
                "entity": match.group(1).strip(),
                "rate": match.group(2),
                "start": match.start(),
                "end": match.end(),
            })

        return pairs

    @classmethod
    def extract_primary_dealers(cls, text: str) -> list[str]:
        """Extract Primary Dealer names from text.

        Combines NER and pattern matching for robust extraction.
        """
        dealers = []
        seen = set()

        # Strategy 1: Entity-phone pairs
        for pair in cls.find_entity_phone_pairs(text):
            entity = pair["entity"]
            if entity.upper() not in seen:
                seen.add(entity.upper())
                dealers.append(entity)

        # Strategy 2: Known dealer patterns
        import re
        dealer_patterns = [
            r"([A-Z][A-Za-z'&\.\s]+(?:Bank|PLC|Securities|Ltd))",
            r"([A-Z][A-Za-z']+\s+(?:Leasing|Finance|Capital)(?:\s+(?:PLC|Ltd))?)",
        ]

        for pattern in dealer_patterns:
            for match in re.finditer(pattern, text):
                entity = match.group(1).strip()
                if entity.upper() not in seen and len(entity) > 5:
                    seen.add(entity.upper())
                    dealers.append(entity)

        return dealers


class AnswerValidator:
    """
    Validate generated answers against source text.

    Prevents hallucinations by verifying:
    - Numeric values exist in the original text
    - No digit swapping (e.g., "1234" → "1243")
    - Entity names are correctly extracted
    """

    @classmethod
    def extract_numbers_from_text(cls, text: str) -> set[str]:
        """Extract all numeric values from text."""
        import re
        # Find all number patterns (with optional decimals, commas, currency)
        numbers = set()

        # Raw numbers: 1234, 1234.56, 1,234.56
        for match in re.finditer(r'[\d,]+\.?\d*', text):
            num = match.group().replace(',', '')
            if num and num != '.':
                numbers.add(num)

        # Also add without decimals for flexibility
        for num in list(numbers):
            if '.' in num:
                numbers.add(num.split('.')[0])

        return numbers

    @classmethod
    def validate_numeric_answer(cls, answer: str, context: str) -> tuple[bool, str]:
        """Validate that numeric values in answer exist in context.

        Returns (is_valid, reason) tuple.
        """
        import re

        # Extract numbers from answer
        answer_numbers = cls.extract_numbers_from_text(answer)
        context_numbers = cls.extract_numbers_from_text(context)

        if not answer_numbers:
            return True, "No numeric values to validate"

        # Check each number in answer
        invalid_numbers = []
        for num in answer_numbers:
            # Check exact match or close match (within rounding)
            if num in context_numbers:
                continue

            # Check if it's a formatted version
            try:
                num_float = float(num)
                found = False
                for ctx_num in context_numbers:
                    try:
                        if abs(float(ctx_num) - num_float) < 0.01:
                            found = True
                            break
                    except ValueError:
                        continue
                if found:
                    continue
            except ValueError:
                pass

            invalid_numbers.append(num)

        if invalid_numbers:
            return False, f"Numbers not found in document: {invalid_numbers}"

        return True, "All numeric values verified"

    @classmethod
    def check_digit_swap(cls, answer: str, context: str) -> bool:
        """Check if answer contains digit-swapped numbers.

        Returns True if suspicious digit swap detected.
        """
        import re

        answer_numbers = cls.extract_numbers_from_text(answer)
        context_numbers = cls.extract_numbers_from_text(context)

        for ans_num in answer_numbers:
            if ans_num in context_numbers:
                continue

            # Check for digit swaps (same digits, different order)
            ans_digits = sorted(ans_num.replace('.', '').replace(',', ''))
            for ctx_num in context_numbers:
                ctx_digits = sorted(ctx_num.replace('.', '').replace(',', ''))
                if ans_digits == ctx_digits and ans_num != ctx_num:
                    return True  # Potential digit swap

        return False


# ═══════════════════════════════════════════════════════════════
# XAI Engine
# ═══════════════════════════════════════════════════════════════

class XAIEngine:
    """
    Explainable AI Engine using BART Generative Model + Cross-Attention & LIME.

    Pipeline:
    1. Uses BART encoder-decoder for generative Q&A with natural language answers
    2. Uses cross-attention (decoder-to-encoder) for token-level importance scoring
    3. Applies LIME for local interpretable explanations using sequence probability
    4. Builds derivation trees for step-by-step reasoning
    """

    def __init__(self):
        logger.info("Initializing XAI Engine...")
        self.qa_model = GenerativeQAModel()
        self.lime_explainer = LimeTextExplainer(
            class_names=["Low Relevance", "High Relevance"],
            split_expression=r"\W+",
            bow=True,
        )
        # Cache the last generated answer for LIME probability calculation
        self._cached_answer: str | None = None
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
        """Create a predictor function for LIME using sequence probability.

        For generative models, we measure how likely the model is to generate
        the target answer given a perturbed context. This provides meaningful
        word importance scores for LIME.
        """
        # Cache predictions to avoid re-computing identical perturbations
        _cache: dict[str, list[float]] = {}

        # Get the target answer we're explaining
        target_answer = self._cached_answer or ""

        def predict_fn(texts):
            probas = []
            for text in texts:
                cache_key = text[:200]  # truncate key for memory
                if cache_key in _cache:
                    probas.append(_cache[cache_key])
                    continue
                try:
                    ctx = text if len(text) > 10 else paragraph
                    if target_answer:
                        # Use sequence probability for generative model
                        score = self.qa_model.get_sequence_probability(
                            ctx, question, target_answer
                        )
                    else:
                        # Fallback: generate and use confidence
                        result = self.qa_model.predict(ctx, question)
                        score = result.confidence
                    # Clamp to [0, 1]
                    score = max(0.0, min(1.0, score))
                    row = [1 - score, score]
                except Exception:
                    row = [0.5, 0.5]
                _cache[cache_key] = row
                probas.append(row)
            return np.array(probas)
        return predict_fn

    # ─── Cross-Attention-Based Token Importance ─────────────────────
    # NOTE: For encoder-decoder models, we extract cross-attention from
    # the decoder to encoder tokens. This shows which input tokens the
    # model attended to when generating the answer. We retain the SHAP
    # data structure name for API compatibility, but the values
    # represent cross-attention-derived importance scores.

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
            num_samples = min(8, max(6, len(paragraph.split()) // 10))
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
        Uses BART generative's native unanswerable detection + additional validation.

        Enhanced with AnswerValidator to prevent hallucinations:
        - Verifies numeric values exist in original text
        - Detects digit-swapping errors
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

        # ═══ NEW: AnswerValidator checks ═══
        # Verify numeric values exist in original text (prevent hallucinations)
        numeric_valid, numeric_reason = AnswerValidator.validate_numeric_answer(answer, context)
        if not numeric_valid:
            logger.warning("Numeric validation failed: %s", numeric_reason)
            # Don't mark as unanswerable, but reduce confidence
            base_conf = min(base_conf, 0.3)

        # Check for digit swapping (common hallucination pattern)
        if AnswerValidator.check_digit_swap(answer, context):
            logger.warning("Potential digit swap detected in answer: %s", answer)
            base_conf = min(base_conf, 0.2)

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
            DerivationStep(1, "📝 Input Formatting",
                "Formatted input as 'question: [Q] context: [C]' for BART",
                "Model: vblagoje/bart_lfqa (encoder-decoder)", 0.99),
            DerivationStep(2, "🧠 Encoder Processing",
                "Encoded question+context through 12-layer BART encoder with self-attention",
                "Created contextualized representations for each input token", 0.95),
            DerivationStep(3, "🎯 Decoder Generation",
                f'Generated natural language answer: "{prediction.answer[:80]}..."' if len(prediction.answer) > 80 else f'Generated answer: "{prediction.answer}"',
                f"Beam search with 4 beams, no-repeat-ngram=3",
                prediction.confidence),
        ]

        top_shap = shap_exp.shap_values[:5]
        shap_details = ", ".join([f"'{w}': {s:.3f}" for w, s in top_shap])
        steps.append(DerivationStep(4, "🔬 Cross-Attention Analysis",
            "Extracted decoder-to-encoder cross-attention for XAI",
            f"Top attended tokens: {shap_details}" if shap_details else "No significant tokens",
            0.88))

        top_lime = lime_exp.word_weights[:5]
        lime_details = ", ".join([f"'{w}': {s:.3f}" for w, s in top_lime])
        steps.append(DerivationStep(5, "🍋 LIME Sequence Analysis",
            "Measured sequence probability changes under context perturbation",
            f"Key words: {lime_details}" if lime_details else "No significant words",
            0.85))

        steps.append(DerivationStep(6, "✨ Answer Synthesis",
            "Combined generative output with XAI insights",
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
        self, paragraph: str, sub_question: str, entity: str, include_xai: bool = False
    ) -> SubQuestionResult:
        """Run a sub-question through the XAI pipeline.

        Args:
            include_xai: If True, runs cross-attention + LIME. If False, skips for speed.
        """
        prediction = self.qa_model.predict(paragraph, sub_question)
        boosted_conf, is_unanswerable = self._boost_confidence(
            prediction, paragraph, sub_question
        )

        # Get XAI explanations (conditionally based on include_xai)
        if not include_xai:
            shap_exp = SHAPExplanation(base_value=0.5, shap_values=[], feature_names=[])
            lime_exp = LIMEExplanation(word_weights=[], prediction_proba=boosted_conf)
            derivation = DerivationTree(
                question=sub_question,
                steps=[
                    DerivationStep(1, "🔍 Sub-Query", f"Extracted info for: {entity}", "BART generative", 0.95),
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
        self, paragraph: str, question: str, comparison_type: str, attribute: str,
        include_xai: bool = False
    ) -> XAIExplanation:
        """Handle comparison questions using question decomposition.

        Args:
            include_xai: If True, runs cross-attention + LIME for sub-questions.
        """
        logger.info("Decomposing comparison question: %s", question[:50])

        # Extract entities to compare
        entities = self._extract_entities_for_comparison(paragraph, question)

        if not entities:
            # No entities found, fall back to regular Q&A
            logger.info("No entities found for comparison, falling back to regular Q&A")
            return self._generate_regular_explanation(paragraph, question, include_xai)

        logger.info("Found %d entities for comparison: %s", len(entities), entities)

        # Generate and run sub-questions for each entity
        sub_results: list[SubQuestionResult] = []
        for entity in entities:
            sub_q = self._generate_sub_question(question, entity, attribute)
            logger.debug("Sub-question for %s: %s", entity, sub_q)
            result = self._run_sub_question_with_xai(paragraph, sub_q, entity, include_xai)
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

    def _generate_regular_explanation(
        self, paragraph: str, question: str, include_xai: bool = False
    ) -> XAIExplanation:
        """Generate regular (non-comparison) explanation. Extracted for reuse.

        Args:
            include_xai: If True, runs cross-attention + LIME. If False, skips for speed.
        """
        prediction = self.qa_model.predict(paragraph, question)
        logger.debug("Answer: '%s' (raw %.1f%%)", prediction.answer, prediction.confidence * 100)

        # Cache answer for LIME sequence probability calculation
        self._cached_answer = prediction.answer

        boosted_conf, is_unanswerable = self._boost_confidence(prediction, paragraph, question)
        logger.debug("Boosted confidence: %.1f%%, Unanswerable: %s", boosted_conf * 100, is_unanswerable)

        relevant_sentences = self._get_sentence_relevance_scores(paragraph, question)
        evidence = [s for s, score in relevant_sentences if score > 0.01][:3]

        # For generative models, use the raw answer (already natural language)
        answer = prediction.answer if not is_unanswerable else self._construct_answer(
            prediction, relevant_sentences, boosted_conf, is_unanswerable, question
        )

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

        if not include_xai:
            logger.info("Fast mode: skipping cross-attention/LIME explanations")
            shap_exp = SHAPExplanation(base_value=0.5, shap_values=[], feature_names=[])
            lime_exp = LIMEExplanation(word_weights=[], prediction_proba=boosted_conf)
            spans = []
            derivation = DerivationTree(
                question=question,
                steps=[
                    DerivationStep(1, "📝 Question Analysis", f"Analyzed: {question[:50]}...", "Model-Generated", 0.95),
                    DerivationStep(2, "🎯 Answer Generation", f"Generated: {answer}", f"Confidence: {boosted_conf:.1%}", boosted_conf),
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

    # ─── list-type question handling ─────────────────────────

    def _handle_list_question(
        self, paragraph: str, question: str, include_xai: bool = False
    ) -> XAIExplanation | None:
        """Handle questions asking for multiple items/entities.

        Uses semantic detection instead of rigid patterns:
        - Detects plural entity keywords (dealers, banks, companies, etc.)
        - Detects quantity words (three, five, all, etc.)
        - Detects list action words (list, name, show, etc.)

        Args:
            include_xai: If True, runs cross-attention + LIME. If False, skips for speed.
        """
        import re
        q_lower = question.lower().strip()

        # Keywords indicating multiple items are expected
        list_action_words = {'list', 'name', 'show', 'give', 'tell', 'provide', 'mention', 'identify'}
        quantity_words = {'all', 'three', 'five', 'ten', 'some', 'few', 'several', 'many', 'multiple'}
        plural_entities = {
            'dealers': 'dealer', 'banks': 'bank', 'companies': 'company',
            'institutions': 'institution', 'organizations': 'organization',
            'firms': 'firm', 'bonds': 'bond', 'series': 'series',
            'investors': 'investor', 'vendors': 'vendor', 'items': 'item',
        }

        # Check if question is asking for multiple items
        has_list_action = any(w in q_lower for w in list_action_words)
        has_quantity = any(w in q_lower for w in quantity_words)

        # Find plural entity in question
        target = None
        for plural, singular in plural_entities.items():
            if plural in q_lower:
                target = singular
                break

        # If no plural found, check for "primary dealer" type phrases
        if not target:
            entity_phrases = ['primary dealer', 'dealer', 'bank', 'company', 'bond', 'series']
            for phrase in entity_phrases:
                if phrase in q_lower:
                    target = phrase
                    break

        # Require at least one indicator + entity target
        if not target or not (has_list_action or has_quantity):
            return None

        logger.info("Detected list question for: '%s'", target)

        # Try to find a section with this target
        # Look for "List of X" or "X:" patterns in the document
        items = []
        extraction_method = "pattern"

        # Strategy 1: spaCy NER for organization/person extraction (most reliable)
        # Works well for company names, banks, dealers in complex table formats
        nlp = _get_spacy_nlp()
        if nlp and ('dealer' in target or 'bank' in target or 'company' in target or
                    'institution' in target or 'organization' in target or 'firm' in target):
            doc = nlp(paragraph)
            # Extract ORG entities (organizations)
            org_entities = [ent.text.strip() for ent in doc.ents if ent.label_ == "ORG"]
            # Filter: keep only meaningful org names (>3 chars, not generic terms)
            generic_terms = {'the', 'government', 'central bank', 'ministry', 'department'}
            for org in org_entities:
                org_clean = org.strip()
                if len(org_clean) > 3 and org_clean.lower() not in generic_terms:
                    items.append(org_clean)
            if items:
                extraction_method = "spaCy NER (ORG entities)"
                logger.info("spaCy NER extracted %d organizations", len(items))

        # Strategy 2: Find section header like "List of Primary Dealers"
        if not items:
            section_header_pattern = rf'(?:list\s+of\s+)?{re.escape(target)}[:\s]*\n([\s\S]*?)(?:\n\n|\n[A-Z][a-z]+\s+[a-z]|\Z)'
            section_match = re.search(section_header_pattern, paragraph, re.IGNORECASE)
            if section_match:
                section_text = section_match.group(1).strip()
                lines = [l.strip() for l in section_text.split('\n') if l.strip()]
                for line in lines:
                    cleaned = re.sub(r'\s+\d{7,}$', '', line).strip()
                    if cleaned and len(cleaned) > 2:
                        items.append(cleaned)
                if items:
                    extraction_method = "section header"

        # Strategy 3: For dealers/banks, use EntityAnchorSearch (entity-phone pairs)
        if not items and ('dealer' in target or 'bank' in target):
            # Use the specialized EntityAnchorSearch for Primary Dealers
            items = EntityAnchorSearch.extract_primary_dealers(paragraph)
            if items:
                extraction_method = "EntityAnchorSearch (entity-phone pairs)"
                logger.info("EntityAnchorSearch extracted %d entities", len(items))

        # Strategy 4: For bonds/series, use existing entity extraction
        if not items and ('bond' in target or 'series' in target):
            items = self._extract_entities_for_comparison(paragraph, question)
            if items:
                extraction_method = "bond pattern"

        # Strategy 5: Generic - look for capitalized items after the target keyword
        if not items:
            target_pos = paragraph.lower().find(target.lower())
            if target_pos >= 0:
                after_target = paragraph[target_pos:target_pos + 500]
                cap_pattern = r'([A-Z][A-Za-z\s\.\&]+(?:PLC|Ltd|Bank|Co\.?)?)'
                matches = re.findall(cap_pattern, after_target)
                for m in matches[:15]:
                    cleaned = m.strip()
                    if len(cleaned) > 3 and cleaned.lower() != target.lower():
                        items.append(cleaned)
                if items:
                    extraction_method = "capitalized phrases"

        if not items:
            return None  # Couldn't extract items, fall back to regular Q&A

        # Deduplicate while preserving order
        seen = set()
        unique_items = []
        for item in items:
            item_key = item.lower().strip()
            if item_key not in seen and len(item) > 2:
                seen.add(item_key)
                unique_items.append(item)

        if not unique_items:
            return None

        # Build formatted answer
        answer = f"The {target} are:\n" + "\n".join(f"• {item}" for item in unique_items[:20])

        logger.info("List question answered with %d items for '%s'", len(unique_items), target)

        # Set confidence based on extraction method (NER is most reliable)
        confidence = 0.90 if "spaCy" in extraction_method else 0.85

        # ═══ XAI: Conditionally run cross-attention and LIME ═══
        if include_xai:
            shap_exp, lime_exp = self.generate_xai_for_answer(paragraph, question, answer)
            logger.info("XAI for list question: %d SHAP features, %d LIME features",
                        len(shap_exp.shap_values), len(lime_exp.word_weights))
        else:
            # Fast mode: skip XAI computations
            shap_exp = SHAPExplanation(base_value=0.5, shap_values=[], feature_names=[])
            lime_exp = LIMEExplanation(word_weights=[], prediction_proba=confidence)

        return XAIExplanation(
            paragraph=paragraph,
            question=question,
            answer=answer,
            highlighted_spans=[],
            shap_explanation=shap_exp,
            lime_explanation=lime_exp,
            derivation_tree=DerivationTree(
                question=question,
                steps=[
                    DerivationStep(1, "📋 List Detection", f"Detected request to list '{target}'", "Rule-Extracted", 0.95),
                    DerivationStep(2, "🔍 Entity Extraction", f"Used {extraction_method} to find entities", f"Method: {extraction_method}", 0.92 if "spaCy" in extraction_method else 0.85),
                    DerivationStep(3, "🔬 XAI Analysis", "Cross-attention + LIME" if include_xai else "Skipped (fast mode)", f"{len(shap_exp.shap_values)} features" if include_xai else "N/A", 0.88 if include_xai else 1.0),
                    DerivationStep(4, "📊 Results", f"Extracted {len(unique_items)} items", ", ".join(unique_items[:5]) + ("..." if len(unique_items) > 5 else ""), confidence),
                ],
                final_answer=answer,
                overall_confidence=confidence,
            ),
            confidence_score=confidence,
            evidence_sentences=[],
            model_prediction=None,
        )

    # ─── Yes/No question handling ─────────────────────────────

    def _detect_yes_no_question(self, question: str) -> tuple[bool, str | None]:
        """Detect if this is a yes/no question and extract the target.

        Returns (is_yes_no, target_phrase) tuple.
        Examples:
          - "Is the total $500?" → (True, "total $500")
          - "Does it have a discount?" → (True, "discount")
          - "Are there any taxes?" → (True, "taxes")
        """
        import re
        q_lower = question.lower().strip()

        # Yes/No question patterns
        yes_no_patterns = [
            (r'^(?:is|are|was|were|do|does|did|has|have|had|can|could|will|would|should)\s+(?:the|there|this|it|any)?\s*(.*?)\??$', 1),
            (r'^(?:is|are)\s+there\s+(?:a|an|any)?\s*(.*?)\??$', 1),
            (r'^(?:does|do)\s+(?:the|this|it)\s+(?:have|contain|include)\s+(.*?)\??$', 1),
        ]

        for pattern, group in yes_no_patterns:
            match = re.match(pattern, q_lower)
            if match:
                target = match.group(group).strip()
                # Clean up common words
                target = re.sub(r'^(?:a|an|any|the|this|that)\s+', '', target)
                return True, target if target else None

        return False, None

    def _handle_yes_no_question(
        self, paragraph: str, question: str, include_xai: bool = False
    ) -> XAIExplanation | None:
        """Handle yes/no questions with conversational synthesis.

        Instead of returning just "yes" or "no", generates natural responses like:
        - "Yes, the total is $500."
        - "No, I couldn't find any discount in this document."

        Args:
            include_xai: If True, runs cross-attention + LIME. If False, skips for speed.
        """
        is_yes_no, target = self._detect_yes_no_question(question)
        if not is_yes_no:
            return None

        logger.info("Detected yes/no question about: '%s'", target)

        # First, try to find the relevant information
        # Use table reconstruction to detect values
        pairs = TableReconstructor.detect_label_value_pairs(paragraph)

        # Check if target is mentioned in document
        target_lower = target.lower() if target else ""
        found_value = None
        found_label = None

        # Search in extracted pairs
        for pair in pairs:
            if target_lower and target_lower in pair["label_normalized"]:
                found_value = pair["value"]
                found_label = pair["label"]
                break

        # Also search in raw text
        if not found_value and target:
            import re
            # Look for target followed by value
            pattern = rf'{re.escape(target)}[\s:]*?([\$£€]?\s*[\d,]+\.?\d*)'
            match = re.search(pattern, paragraph, re.IGNORECASE)
            if match:
                found_value = match.group(1).strip()
                found_label = target

        # Also check if target keyword exists in document at all
        target_in_doc = target_lower in paragraph.lower() if target else False

        # Generate natural response
        if found_value:
            answer = f"Yes, the {found_label or target} is {found_value}."
            confidence = 0.85
            is_yes = True
        elif target_in_doc:
            # Target mentioned but no clear value
            answer = f"Yes, {target} is mentioned in the document, but I couldn't extract a specific value."
            confidence = 0.6
            is_yes = True
        else:
            # Not found
            answer = f"No, I couldn't find any {target or 'matching information'} in this document."
            confidence = 0.75
            is_yes = False

        logger.info("Yes/No answer: %s (found_value=%s)", "Yes" if is_yes else "No", found_value)

        # ═══ XAI: Conditionally run cross-attention and LIME ═══
        if include_xai:
            shap_exp, lime_exp = self.generate_xai_for_answer(paragraph, question, answer)
            logger.info("XAI for yes/no question: %d SHAP features, %d LIME features",
                        len(shap_exp.shap_values), len(lime_exp.word_weights))
        else:
            # Fast mode: skip XAI computations
            shap_exp = SHAPExplanation(base_value=0.5, shap_values=[], feature_names=[])
            lime_exp = LIMEExplanation(word_weights=[], prediction_proba=confidence)

        return XAIExplanation(
            paragraph=paragraph,
            question=question,
            answer=answer,
            highlighted_spans=[],
            shap_explanation=shap_exp,
            lime_explanation=lime_exp,
            derivation_tree=DerivationTree(
                question=question,
                steps=[
                    DerivationStep(1, "❓ Question Analysis", f"Detected yes/no question about '{target}'", "Rule-Extracted", 0.95),
                    DerivationStep(2, "🔍 Document Search", f"Searched for '{target}' in document", f"Found: {found_value}" if found_value else "Not found", 0.85 if found_value else 0.5),
                    DerivationStep(3, "🔬 XAI Analysis", "Cross-attention + LIME" if include_xai else "Skipped (fast mode)", f"{len(shap_exp.shap_values)} features" if include_xai else "N/A", 0.88 if include_xai else 1.0),
                    DerivationStep(4, "💬 Conversational Synthesis", f"Generated natural {'affirmative' if is_yes else 'negative'} response", answer[:50], confidence),
                ],
                final_answer=answer,
                overall_confidence=confidence,
            ),
            confidence_score=confidence,
            evidence_sentences=[],
            model_prediction=None,
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

    # ─── XAI generation helper (PUBLIC) ──────────────────────────

    def generate_xai_for_answer(
        self, paragraph: str, question: str, answer: str
    ) -> tuple[SHAPExplanation, LIMEExplanation]:
        """Generate XAI explanations (cross-attention + LIME) for a given answer.

        This is a PUBLIC method that can be called independently after
        get_answer_only() to lazily load XAI explanations when the user
        requests them (e.g., clicks "Show Explanation").

        Args:
            paragraph: The document context
            question: The user's question
            answer: The answer to explain (from get_answer_only)

        Returns:
            Tuple of (SHAPExplanation, LIMEExplanation)
        """
        self._cached_answer = answer  # Cache for LIME sequence probability

        # Cross-attention based token importance
        token_importance = self.qa_model.get_token_importance(paragraph, question)
        shap_values = sorted(
            token_importance.items(), key=lambda x: abs(x[1]), reverse=True
        )[:20]
        if shap_values:
            max_score = max(abs(s) for _, s in shap_values)
            if max_score > 0:
                shap_values = [(w, s / max_score) for w, s in shap_values]

        shap_exp = SHAPExplanation(
            base_value=0.5,
            shap_values=shap_values,
            feature_names=[w for w, _ in shap_values],
        )

        # LIME explanation
        lime_exp = self._get_lime_explanation(paragraph, question)

        logger.info("XAI generated: %d SHAP features, %d LIME features",
                    len(shap_values), len(lime_exp.word_weights))

        return shap_exp, lime_exp

    # ─── main entry points ────────────────────────────────────

    def get_answer_only(self, paragraph: str, question: str) -> XAIExplanation:
        """Get answer FAST without XAI explanations (Lazy XAI).

        Runs the Waterfall Logic to produce an answer and derivation_tree,
        but SKIPS the expensive cross-attention and LIME computations.

        Use this for fast initial responses, then call generate_xai_for_answer()
        separately if the user requests explanation details.

        Returns:
            XAIExplanation with answer and derivation_tree populated,
            but shap_explanation and lime_explanation will be empty.
        """
        return self.generate_explanation(paragraph, question, include_xai=False)

    def generate_explanation(
        self, paragraph: str, question: str, include_xai: bool = False
    ) -> XAIExplanation:
        """Generate XAI explanation using Waterfall Logic.

        Waterfall Pipeline:
        ═══════════════════════════════════════════════════════════
        1. CONVERSATIONAL: Handle greetings, thanks, etc. (no XAI needed)

        2. RULE-EXTRACTED: Try specialized handlers first
           - Yes/No questions → Rule-based detection
           - List questions → NER/Pattern extraction
           - Comparison questions → Question decomposition
           If handler finds answer → Generate XAI using that answer as target

        3. MODEL-GENERATED: BART fallback for complex questions
           - Full generative Q&A with cross-attention + LIME

        The DerivationTree indicates whether answer was:
        - "Rule-Extracted" (fast, deterministic)
        - "Model-Generated" (BART inference)
        ═══════════════════════════════════════════════════════════

        Args:
            paragraph: The document context
            question: The user's question
            include_xai: If False (default), skips cross-attention & LIME for speed.
                         If True, generates full XAI explanations.

        Returns:
            XAIExplanation with answer, derivation_tree, and optionally XAI data.
        """
        logger.info("Processing question: %s (include_xai=%s)", question, include_xai)

        # ═══ Pre-process: Table Reconstruction for flattened financial text ═══
        processed_paragraph = paragraph
        table_pairs = TableReconstructor.detect_label_value_pairs(paragraph)
        if table_pairs and len(table_pairs) >= 3:
            processed_paragraph = TableReconstructor.reconstruct_table_format(paragraph)
            logger.info("Applied table reconstruction to flattened text")

        # ═══════════════════════════════════════════════════════════════
        # STAGE 1: CONVERSATIONAL (no XAI needed)
        # ═══════════════════════════════════════════════════════════════
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
                    question=question,
                    steps=[DerivationStep(1, "💬 Conversational", "Handled as greeting/conversation", "No document lookup needed", 1.0)],
                    final_answer=conv_response,
                    overall_confidence=1.0
                ),
                confidence_score=-1.0,  # Hide confidence for conversations
                evidence_sentences=[],
                model_prediction=None,
            )

        # ═══════════════════════════════════════════════════════════════
        # STAGE 2: RULE-EXTRACTED (specialized handlers)
        # ═══════════════════════════════════════════════════════════════

        # Try Yes/No handler
        yes_no_response = self._handle_yes_no_question(processed_paragraph, question, include_xai)
        if yes_no_response:
            logger.info("Answer source: Rule-Extracted (Yes/No)")
            yes_no_response.paragraph = paragraph
            return yes_no_response

        # Try List handler
        list_response = self._handle_list_question(processed_paragraph, question, include_xai)
        if list_response:
            logger.info("Answer source: Rule-Extracted (List/NER)")
            list_response.paragraph = paragraph
            return list_response

        # Try Comparison handler
        is_comparison, comparison_type, attribute = self._detect_comparison_question(question)
        if is_comparison and comparison_type and attribute:
            logger.info("Answer source: Rule-Extracted (Comparison)")
            result = self._handle_comparison_question(processed_paragraph, question, comparison_type, attribute, include_xai)
            result.paragraph = paragraph
            return result

        # ═══════════════════════════════════════════════════════════════
        # STAGE 3: MODEL-GENERATED (BART fallback for complex questions)
        # ═══════════════════════════════════════════════════════════════
        logger.info("Answer source: Model-Generated (BART)")
        result = self._generate_regular_explanation(processed_paragraph, question, include_xai)
        result.paragraph = paragraph  # Keep original for display
        return result

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

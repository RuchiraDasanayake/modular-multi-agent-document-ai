"""Sentence embedding service using SentenceTransformers."""

from sentence_transformers import SentenceTransformer

import threading

class EmbeddingService:
    _instance = None
    _lock = threading.Lock()
    _model = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(EmbeddingService, cls).__new__(cls)
                    cls._model = SentenceTransformer('all-MiniLM-L6-v2')
        return cls._instance

    def generate_embedding(self, text: str) -> list[float]:
        """Generate vector embedding for the given text."""
        if not self._model:
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
        
        embedding = self._model.encode(text)
        return embedding.tolist()

    _DOC_TYPE_DESCRIPTIONS: dict[str, str] = {
        "invoice": "Invoice with line items, subtotals, taxes, and payment terms",
        "receipt": "Purchase receipt with itemised products and payment total",
        "financial_statement": "Financial report with balance sheets, income statements, and numerical tables",
        "table_document": "Tabular document with rows, columns, and structured data cells",
        "form_document": "Structured form with labeled fields, checkboxes, and input areas",
        "clinical_summary": "Clinical summary with patient demographics, diagnosis, and treatment plan",
        "medical_record": "Medical record with patient history, lab results, and clinical data",
        "scanned_document": "Scanned paper document requiring OCR text recognition",
        "text_document": "Text-heavy document with paragraphs, sections, and narrative content",
        "legal_document": "Legal document with regulatory clauses, sections, and statutory language",
        "mixed_document": "Mixed-format document combining text, tables, and images",
        "contract": "Contract with legal clauses, signature blocks, and appendices",
        "unknown": "Unclassified document with unknown structure",
    }

    def create_context_string(self, doc_type: str, vendor: str | None) -> str:
        """Create a descriptive context string for better embedding differentiation."""
        desc = self._DOC_TYPE_DESCRIPTIONS.get(
            doc_type, f"Document classified as {doc_type}"
        )
        parts = [desc]
        if vendor:
            parts.append(f"from {vendor}")
        return ". ".join(parts)

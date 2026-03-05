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

    def create_context_string(self, doc_type: str, vendor: str | None) -> str:
        """Create a descriptive context string for better embedding differentiation."""
        # More descriptive context for better semantic separation
        context_parts = [
            f"Document type: {doc_type}",
            f"Processing {doc_type} documents",
        ]
        if vendor:
            context_parts.append(f"Vendor: {vendor}")
            context_parts.append(f"Source organization: {vendor}")
            context_parts.append(f"Documents from {vendor} company")
        
        return ". ".join(context_parts)

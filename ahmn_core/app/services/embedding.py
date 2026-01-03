from sentence_transformers import SentenceTransformer
from typing import List
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

    def generate_embedding(self, text: str) -> List[float]:
        """Generate vector embedding for the given text."""
        if not self._model:
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
        
        embedding = self._model.encode(text)
        return embedding.tolist()

    def create_context_string(self, doc_type: str, vendor: str | None) -> str:
        """Create a context string from document type and vendor."""
        parts = [f"type:{doc_type}"]
        if vendor:
            parts.append(f"vendor:{vendor}")
        return " ".join(parts)

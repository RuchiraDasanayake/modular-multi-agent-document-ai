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
                    # Load model only once
                    cls._model = SentenceTransformer('all-MiniLM-L6-v2')
        return cls._instance

    def generate_embedding(self, text: str) -> List[float]:
        if not self._model:
             # Fallback if something went wrong with init, though __new__ handles it
             self._model = SentenceTransformer('all-MiniLM-L6-v2')
        
        embedding = self._model.encode(text)
        return embedding.tolist()

    def create_context_string(self, doc_type: str, vendor: str | None) -> str:
        parts = [f"type:{doc_type}"]
        if vendor:
            parts.append(f"vendor:{vendor}")
        return " ".join(parts)

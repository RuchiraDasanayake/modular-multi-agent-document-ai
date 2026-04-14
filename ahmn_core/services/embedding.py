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

    def create_context_string(
        self,
        doc_type: str,
        vendor: str | None,
        content_profile: str | None = None,
        extra_context: dict | None = None,
    ) -> str:
        """Create a descriptive context string for better embedding differentiation."""
        # More descriptive context for better semantic separation
        context_parts = [
            f"Document type: {doc_type}",
            f"Processing {doc_type} documents",
        ]
        if content_profile:
            context_parts.append(f"Content profile: {content_profile}")
        if vendor:
            context_parts.append(f"Vendor: {vendor}")
            context_parts.append(f"Source organization: {vendor}")
            context_parts.append(f"Documents from {vendor} company")
        extra = extra_context or {}
        for key, label in (
            ("layout_cluster_id", "Layout cluster"),
            ("route_bin", "Route bin"),
            ("quality_bin", "Quality bin"),
            ("complexity_bin", "Complexity bin"),
        ):
            value = extra.get(key)
            if value:
                context_parts.append(f"{label}: {value}")

        analysis_confidence = extra.get("analysis_confidence")
        if analysis_confidence is not None:
            context_parts.append(f"Analysis confidence: {analysis_confidence}")

        quality_features = extra.get("quality_features") if isinstance(extra.get("quality_features"), dict) else {}
        structural_features = extra.get("structural_features") if isinstance(extra.get("structural_features"), dict) else {}
        for key in ("ocr_noise_ratio", "image_ratio", "line_length_cv"):
            value = quality_features.get(key)
            if value is not None:
                context_parts.append(f"{key}: {value}")
        for key in ("table_ratio", "form_ratio", "kv_density", "numeric_density"):
            value = structural_features.get(key)
            if value is not None:
                context_parts.append(f"{key}: {value}")

        return ". ".join(context_parts)

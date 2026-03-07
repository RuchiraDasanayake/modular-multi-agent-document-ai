"""Vector store for dense retrieval with hashing-based embeddings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import hashlib
import numpy as np

from idpo.core.types import Chunk

class HashingEmbedder:
    def __init__(self, dim: int = 256, seed: int = 13) -> None:
        self.dim = dim
        self.seed = seed

    def embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for token in text.split():
            token_hash = self._hash(token)
            idx = token_hash % self.dim
            sign = 1 if token_hash % 2 == 0 else -1
            vec[idx] += sign
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec

    def _hash(self, token: str) -> int:
        payload = f"{self.seed}:{token}".encode("utf-8")
        digest = hashlib.md5(payload).digest()
        return int.from_bytes(digest[:4], "little")

@dataclass
class VectorRecord:
    chunk_id: str
    vector: np.ndarray
    metadata: dict[str, str]

class VectorStore:
    def __init__(self, embedder: HashingEmbedder) -> None:
        self.embedder = embedder
        self.records: list[VectorRecord] = []

    def add(self, chunks: Iterable[Chunk]) -> None:
        for chunk in chunks:
            vector = self.embedder.embed(chunk.text)
            self.records.append(
                VectorRecord(
                    chunk_id=chunk.chunk_id,
                    vector=vector,
                    metadata={
                        "doc_id": chunk.doc_id,
                        "section": chunk.section or "",
                        "page_start": str(chunk.page_range[0]),
                        "page_end": str(chunk.page_range[1]),
                    },
                )
            )

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        if not self.records:
            return []
        qvec = self.embedder.embed(query)
        scores = []
        for record in self.records:
            score = float(np.dot(qvec, record.vector))
            scores.append((record.chunk_id, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def dump(self, path: str) -> None:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "dim": self.embedder.dim,
            "records": [
                {"chunk_id": record.chunk_id, "metadata": record.metadata}
                for record in self.records
            ],
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        vectors = np.stack([record.vector for record in self.records]) if self.records else np.zeros((0, self.embedder.dim))
        np.save(out_path.with_suffix(".npy"), vectors)

    @classmethod
    def load(cls, path: str, embedder: HashingEmbedder) -> "VectorStore":
        meta_path = Path(path)
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        vectors = np.load(meta_path.with_suffix(".npy"))
        store = cls(embedder)
        for idx, record in enumerate(payload.get("records", [])):
            vector = vectors[idx] if idx < len(vectors) else np.zeros(embedder.dim)
            store.records.append(
                VectorRecord(
                    chunk_id=record["chunk_id"],
                    vector=vector,
                    metadata=record.get("metadata", {}),
                )
            )
        return store

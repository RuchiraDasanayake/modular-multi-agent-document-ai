"""Index bundle for persisting and loading retrieval indices."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from idpo.core.types import Chunk
from idpo.retrieval.bm25 import BM25Index
from idpo.retrieval.vector_store import HashingEmbedder, VectorStore

@dataclass
class IndexBundle:
    vector_store: VectorStore
    bm25: BM25Index
    chunks: dict[str, Chunk]

    def save(self, directory: str) -> None:
        out_dir = Path(directory)
        out_dir.mkdir(parents=True, exist_ok=True)
        self.vector_store.dump(str(out_dir / "vectors.json"))
        chunk_payload = {"chunks": [chunk.__dict__ for chunk in self.chunks.values()]}
        (out_dir / "chunks.json").write_text(json.dumps(chunk_payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, directory: str, embed_dim: int = 256, seed: int = 13) -> "IndexBundle":
        out_dir = Path(directory)
        chunk_payload = json.loads((out_dir / "chunks.json").read_text(encoding="utf-8"))
        chunks = {}
        for item in chunk_payload.get("chunks", []):
            item["page_range"] = tuple(item.get("page_range", (1, 1)))
            chunks[item["chunk_id"]] = Chunk(**item)
        embedder = HashingEmbedder(dim=embed_dim, seed=seed)
        vector_store = VectorStore.load(str(out_dir / "vectors.json"), embedder)
        bm25 = BM25Index()
        bm25.add(chunks.values())
        return cls(vector_store=vector_store, bm25=bm25, chunks=chunks)

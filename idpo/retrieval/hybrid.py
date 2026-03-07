"""Hybrid retriever combining dense vector and sparse BM25 search."""

from __future__ import annotations

import numpy as np

from idpo.core.types import Chunk, RetrievalResult
from idpo.retrieval.bm25 import BM25Index
from idpo.retrieval.vector_store import VectorStore

class HybridRetriever:
    def __init__(self, vector_store: VectorStore, bm25: BM25Index) -> None:
        self.vector_store = vector_store
        self.bm25 = bm25

    def retrieve(
        self,
        query: str,
        chunks: dict[str, Chunk],
        dense_k: int,
        sparse_k: int,
        final_k: int,
        metadata_boost: float,
        mmr_lambda: float,
    ) -> list[RetrievalResult]:
        dense = self.vector_store.search(query, top_k=dense_k)
        sparse = self.bm25.search(query, top_k=sparse_k)

        score_map: dict[str, dict[str, float]] = {}
        for chunk_id, score in dense:
            score_map.setdefault(chunk_id, {})["dense"] = score
        for chunk_id, score in sparse:
            score_map.setdefault(chunk_id, {})["sparse"] = score

        results: list[RetrievalResult] = []
        for idx, (chunk_id, scores) in enumerate(score_map.items()):
            chunk = chunks.get(chunk_id)
            if not chunk:
                continue
            dense_score = scores.get("dense", 0.0)
            sparse_score = scores.get("sparse", 0.0)
            metadata_score = metadata_boost if chunk.section else 0.0
            total = dense_score + sparse_score + metadata_score
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    score=total,
                    dense_score=dense_score,
                    sparse_score=sparse_score,
                    metadata_score=metadata_score,
                    rank=idx,
                )
            )

        results.sort(key=lambda r: (-r.score, r.chunk.chunk_id))
        reranked = self._mmr_rerank(results, final_k, mmr_lambda)
        return reranked

    def _mmr_rerank(
        self, results: list[RetrievalResult], k: int, mmr_lambda: float
    ) -> list[RetrievalResult]:
        if not results:
            return []
        selected: list[RetrievalResult] = []
        candidates = results.copy()
        while candidates and len(selected) < k:
            if not selected:
                selected.append(candidates.pop(0))
                continue
            best_idx = 0
            best_score = float("-inf")
            for idx, candidate in enumerate(candidates):
                diversity_penalty = max(
                    self._similarity(candidate.chunk.text, chosen.chunk.text) for chosen in selected
                )
                mmr_score = mmr_lambda * candidate.score - (1 - mmr_lambda) * diversity_penalty
                if mmr_score > best_score or (mmr_score == best_score and candidate.chunk.chunk_id < candidates[best_idx].chunk.chunk_id):
                    best_score = mmr_score
                    best_idx = idx
            selected.append(candidates.pop(best_idx))
        for rank, item in enumerate(selected, 1):
            item.rank = rank
        return selected

    def _similarity(self, text_a: str, text_b: str) -> float:
        vec_a = self.vector_store.embedder.embed(text_a)
        vec_b = self.vector_store.embedder.embed(text_b)
        return float(np.dot(vec_a, vec_b))

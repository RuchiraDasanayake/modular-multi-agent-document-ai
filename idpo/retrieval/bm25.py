from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple

from idpo.core.types import Chunk


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_freq: Dict[str, int] = defaultdict(int)
        self.term_freqs: Dict[str, Counter] = {}
        self.doc_lens: Dict[str, int] = {}
        self.avg_len: float = 0.0
        self.doc_ids: List[str] = []

    def add(self, chunks: Iterable[Chunk]) -> None:
        for chunk in chunks:
            tokens = self._tokenize(chunk.text)
            freq = Counter(tokens)
            self.term_freqs[chunk.chunk_id] = freq
            self.doc_lens[chunk.chunk_id] = len(tokens)
            self.doc_ids.append(chunk.chunk_id)
            for term in freq:
                self.doc_freq[term] += 1
        total_len = sum(self.doc_lens.values())
        self.avg_len = total_len / len(self.doc_lens) if self.doc_lens else 0.0

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        tokens = self._tokenize(query)
        scores: Dict[str, float] = defaultdict(float)
        num_docs = max(len(self.doc_ids), 1)
        for term in tokens:
            df = self.doc_freq.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1 + (num_docs - df + 0.5) / (df + 0.5))
            for doc_id, freq in self.term_freqs.items():
                tf = freq.get(term, 0)
                if tf == 0:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * self.doc_lens[doc_id] / (self.avg_len or 1))
                scores[doc_id] += idf * (tf * (self.k1 + 1) / denom)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    def _tokenize(self, text: str) -> List[str]:
        return [token.lower().strip(".,:;()[]{}") for token in text.split() if token]

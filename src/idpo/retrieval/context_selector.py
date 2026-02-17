from __future__ import annotations

from typing import List, Tuple

from idpo.core.metrics import token_count, term_overlap_score
from idpo.core.types import Chunk, RetrievalResult, TokenBudget


def select_context(
    results: List[RetrievalResult],
    budget: TokenBudget,
    diversity_penalty: float,
) -> Tuple[List[Chunk], int, List[dict]]:
    selected: List[Chunk] = []
    used_tokens = 0
    selected_terms = None
    decisions: List[dict] = []
    for item in results:
        chunk = item.chunk
        chunk_tokens = chunk.tokens or token_count(chunk.text)
        if used_tokens + chunk_tokens > budget.available:
            decisions.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "selected": False,
                    "reason": "token_budget_exceeded",
                    "tokens": chunk_tokens,
                    "score": item.score,
                }
            )
            continue
        if selected_terms:
            overlap = _overlap_ratio(selected_terms, term_overlap_score(chunk.text))
            if overlap > diversity_penalty:
                decisions.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "selected": False,
                        "reason": "diversity_penalty",
                        "tokens": chunk_tokens,
                        "score": item.score,
                    }
                )
                continue
        selected.append(chunk)
        used_tokens += chunk_tokens
        selected_terms = term_overlap_score(chunk.text) if selected_terms is None else selected_terms + term_overlap_score(chunk.text)
        decisions.append(
            {
                "chunk_id": chunk.chunk_id,
                "selected": True,
                "reason": "selected",
                "tokens": chunk_tokens,
                "score": item.score,
            }
        )
        if used_tokens >= budget.available:
            break
    return selected, used_tokens, decisions


def _overlap_ratio(base, new) -> float:
    if not base or not new:
        return 0.0
    common = sum((base & new).values())
    total = sum(new.values()) or 1
    return common / total

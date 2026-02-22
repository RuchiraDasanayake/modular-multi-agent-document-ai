from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, List, Sequence, Tuple


def token_count(text: str) -> int:
    return len(text.split())


def _edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    rows = len(a) + 1
    cols = len(b) + 1
    dp = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        dp[i][0] = i
    for j in range(cols):
        dp[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    return dp[-1][-1]


def cer(reference: str, hypothesis: str) -> float:
    ref = list(reference)
    hyp = list(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def wer(reference: str, hypothesis: str) -> float:
    ref = reference.split()
    hyp = hypothesis.split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def precision_recall_f1(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def f1_for_sets(reference: Iterable[str], predicted: Iterable[str]) -> Tuple[float, float, float]:
    ref_set = set(reference)
    pred_set = set(predicted)
    tp = len(ref_set & pred_set)
    fp = len(pred_set - ref_set)
    fn = len(ref_set - pred_set)
    return precision_recall_f1(tp, fp, fn)


def mrr(ranks: Iterable[int]) -> float:
    reciprocal = [1.0 / rank for rank in ranks if rank > 0]
    return sum(reciprocal) / len(reciprocal) if reciprocal else 0.0


def ndcg(relevances: List[float]) -> float:
    if not relevances:
        return 0.0
    dcg = sum(rel / math.log2(idx + 2) for idx, rel in enumerate(relevances))
    ideal = sorted(relevances, reverse=True)
    idcg = sum(rel / math.log2(idx + 2) for idx, rel in enumerate(ideal)) or 1.0
    return dcg / idcg


def recall_at_k(relevant: List[str], retrieved: List[str], k: int) -> float:
    if not relevant:
        return 0.0
    retrieved_k = set(retrieved[:k])
    return len(set(relevant) & retrieved_k) / len(set(relevant))


def term_overlap_score(text: str) -> Counter:
    tokens = [token.lower().strip(".,:;()[]{}") for token in text.split()]
    return Counter(token for token in tokens if token)

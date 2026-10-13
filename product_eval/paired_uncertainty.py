"""Source-paired, family-stratified uncertainty for frozen recall counts.

Research evidence only. This module does not read documents, labels or model
outputs and does not change the scorer that produces the supplied counts.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class PairedCount:
    doc_id: str
    reference: int
    text_matched: int
    candidate_matched: int


def _ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    return np.divide(numerator, denominator, out=np.full(numerator.shape, np.nan), where=denominator != 0)


def _estimate(point: float, draws: np.ndarray) -> dict:
    finite = draws[np.isfinite(draws)]
    interval = np.quantile(finite, [0.025, 0.975], method="linear").tolist() if finite.size else None
    return {"estimate": float(point) if np.isfinite(point) else None,
            "percentile_95_interval": interval, "estimable_replicates": int(finite.size)}


def _report(counts: np.ndarray, sums: np.ndarray) -> dict:
    # Columns are shared reference targets, text matches and candidate matches.
    totals = counts.sum(axis=0)
    point = _ratio(totals[1:], np.repeat(totals[0], 2))
    text = _ratio(sums[:, 1], sums[:, 0])
    candidate = _ratio(sums[:, 2], sums[:, 0])
    return {"documents": len(counts), "reference": int(totals[0]),
            "text_matched": int(totals[1]), "candidate_matched": int(totals[2]),
            "text": _estimate(point[0], text), "candidate": _estimate(point[1], candidate),
            "candidate_minus_text": _estimate(point[1] - point[0], candidate - text)}


def stratified_paired_recall(records: Sequence[PairedCount], source_families: Mapping[str, str], *,
                            macro_families: Sequence[str], replicates: int = 10_000,
                            seed: int = 20261013) -> dict:
    """Keep every source, resampling originals rather than their fields or rows.

    Failed/unattempted documents must have zero matches with their full reference
    counts. The frozen source map is required to detect dropped or duplicate rows.
    A zero denominator is undefined, including within a bootstrap replicate.
    """
    if type(replicates) is not int or not 1 <= replicates <= 100_000 or type(seed) is not int or seed < 0:
        raise ValueError("Positive bounded replicate count and nonnegative integer seed required")
    if not source_families or any(not isinstance(key, str) or not key or not isinstance(value, str) or not value
                                  for key, value in source_families.items()):
        raise ValueError("A nonempty frozen source-to-family map is required")
    by_id = {}
    for row in records:
        if not isinstance(row, PairedCount) or row.doc_id not in source_families or row.doc_id in by_id:
            raise ValueError("Counts must identify each frozen original exactly once")
        values = (row.reference, row.text_matched, row.candidate_matched)
        if (any(type(value) is not int or not 0 <= value <= 1_000_000 for value in values)
                or row.text_matched > row.reference or row.candidate_matched > row.reference):
            raise ValueError("Matches must be nonnegative integer counts within the shared reference")
        by_id[row.doc_id] = row
    if set(by_id) != set(source_families):
        raise ValueError("Counts must include failed and unattempted originals")
    family_names = sorted(set(source_families.values()))
    if (not macro_families or len(set(macro_families)) != len(macro_families)
            or set(macro_families) - set(family_names)):
        raise ValueError("Macro families must be explicit, unique and present in the frozen cohort")
    rng = np.random.default_rng(seed)
    family_reports, family_draws, family_points = {}, {}, {}
    all_counts, all_sums = [], []
    for family in family_names:
        rows = [by_id[key] for key in sorted(by_id) if source_families[key] == family]
        counts = np.array([(row.reference, row.text_matched, row.candidate_matched) for row in rows], dtype=np.int64)
        # The same document multiplicities are applied to both arms and their
        # common denominator. Chunking bounds memory on large source cohorts.
        sums = np.empty((replicates, 3), dtype=np.int64)
        for start in range(0, replicates, 256):
            end = min(start + 256, replicates)
            indices = rng.integers(0, len(rows), size=(end - start, len(rows)))
            sums[start:end] = counts[indices].sum(axis=1)
        family_reports[family] = _report(counts, sums)
        family_draws[family] = np.column_stack((_ratio(sums[:, 1], sums[:, 0]), _ratio(sums[:, 2], sums[:, 0])))
        totals = counts.sum(axis=0)
        family_points[family] = _ratio(totals[1:], np.repeat(totals[0], 2))
        all_counts.append(counts)
        all_sums.append(sums)
    # Undefined family estimates propagate: excluding such a family would
    # silently change the preregistered equal-weight estimand.
    macro_point = np.stack([family_points[family] for family in macro_families]).mean(axis=0)
    macro_draws = np.stack([family_draws[family] for family in macro_families]).mean(axis=0)
    return {
        "method": "paired source-level family-stratified percentile bootstrap",
        "replicates": replicates, "seed": seed, "confidence_level": 0.95,
        "numpy_version": np.__version__, "python_version": platform.python_version(),
        "family_order": family_names, "source_order": "doc_id ascending within family",
        "families": family_reports,
        "micro": _report(np.concatenate(all_counts), np.stack(all_sums).sum(axis=0)),
        "macro": {"families": list(macro_families), "weight_per_family": 1 / len(macro_families),
                  "text": _estimate(macro_point[0], macro_draws[:, 0]),
                  "candidate": _estimate(macro_point[1], macro_draws[:, 1]),
                  "candidate_minus_text": _estimate(macro_point[1] - macro_point[0], macro_draws[:, 1] - macro_draws[:, 0])},
    }

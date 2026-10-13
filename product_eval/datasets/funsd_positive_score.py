"""Score only annotated positive FUNSD answers; unlinked fields are unknown."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from product_eval.contracts import load_jsonl
from product_eval.datasets.funsd_remainder import FunsdSliceError, _doc_id, _sha256


def _cohort(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            item = json.loads(line)
        except ValueError as exc:
            raise FunsdSliceError(f"Invalid cohort JSON at line {number}") from exc
        if not isinstance(item, dict) or not isinstance(item.get("doc_id"), str):
            raise FunsdSliceError(f"Invalid cohort receipt at line {number}")
        doc_id = item["doc_id"]
        if doc_id in records:
            raise FunsdSliceError(f"Duplicate cohort document ID: {doc_id}")
        source_path = item.get("source_path")
        expected_hash = item.get("source_sha256")
        if not isinstance(source_path, str) or not isinstance(expected_hash, str):
            raise FunsdSliceError(f"Incomplete cohort source receipt: {doc_id}")
        source = Path(source_path)
        if not source.is_file() or _sha256(source) != expected_hash:
            raise FunsdSliceError(f"Source bytes differ from cohort receipt: {doc_id}")
        if _doc_id(source.name, expected_hash) != doc_id:
            raise FunsdSliceError(f"Runtime document ID differs from cohort receipt: {doc_id}")
        records[doc_id] = item
    if not records:
        raise FunsdSliceError("Cohort has no documents")
    return records


def score_positive_only(cohort_path: Path, gold_path: Path, candidate_path: Path) -> dict[str, Any]:
    """Report exact accepted/proposed recall on linked positive labels only.

    Precision, schema F1 and field absence are undefined for this sparse gold.
    Every source stays in the execution denominator, including unscored images.
    """
    cohort = _cohort(cohort_path)
    gold = load_jsonl(gold_path, kind="gold")
    candidates = load_jsonl(candidate_path, kind="candidate")
    if not set(gold) <= set(cohort):
        raise FunsdSliceError("Gold contains a document outside the cohort")
    if not set(candidates) <= set(cohort):
        raise FunsdSliceError("Candidate contains a document outside the cohort")
    counts: Counter[str] = Counter()
    per_field: dict[str, Counter[str]] = {}
    for doc_id, record in gold.items():
        candidate = candidates.get(doc_id)
        extracted = {
            item["field_id"]: item for item in candidate["extracted_values"]
        } if candidate else {}
        for item in record["gold_values"]:
            expected = item["value"]
            if not isinstance(expected, str) or not expected:
                raise FunsdSliceError("Positive-only gold contains an absent or non-string value")
            field = item["field_id"]
            field_counts = per_field.setdefault(field, Counter())
            counts["annotated_values"] += 1
            field_counts["annotated_values"] += 1
            proposed = extracted.get(field)
            if proposed is None:
                outcome = "not_proposed"
            elif proposed["value"] != expected:
                outcome = "wrong_or_unvalued"
            elif proposed["status"] == "accepted" and proposed["review_state"] == "none":
                outcome = "exact_accepted"
            elif proposed["review_state"] == "completed":
                outcome = "exact_post_review"
            elif proposed["status"] == "needs_review":
                outcome = "exact_pending_review"
            else:
                outcome = "exact_unaccepted_other"
            counts[outcome] += 1
            field_counts[outcome] += 1
    denominator = counts["annotated_values"]
    if not denominator:
        raise FunsdSliceError("No annotated positive values to score")
    return {
        "dataset_id": "funsd_test_remainder",
        "metric_scope": "Exact raw-string recall on positive published DATE/TO/FROM links only; no precision, schema F1, absence, or evidence metric.",
        "source_count": len(cohort),
        "source_hash_verified_count": len(cohort),
        "candidate_count": len(candidates),
        "missing_candidate_count": len(set(cohort) - set(candidates)),
        "scored_document_count": len(gold),
        "unscored_document_count": len(cohort) - len(gold),
        "annotated_positive_values": denominator,
        "exact_accepted_values": counts["exact_accepted"],
        "exact_accepted_recall": counts["exact_accepted"] / denominator,
        "exact_pending_review_values": counts["exact_pending_review"],
        "exact_pending_review_rate": counts["exact_pending_review"] / denominator,
        "exact_post_review_values": counts["exact_post_review"],
        "not_proposed_values": counts["not_proposed"],
        "wrong_or_unvalued_values": counts["wrong_or_unvalued"],
        "exact_unaccepted_other_values": counts["exact_unaccepted_other"],
        "per_field": {
            field: dict(sorted(field_counts.items()))
            for field, field_counts in sorted(per_field.items())
        },
        "input_sha256": {
            "cohort.jsonl": _sha256(cohort_path),
            "gold.jsonl": _sha256(gold_path),
            "candidates.jsonl": _sha256(candidate_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = score_positive_only(args.cohort, args.gold, args.candidate)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "source_count": report["source_count"],
        "scored_document_count": report["scored_document_count"],
        "annotated_positive_values": report["annotated_positive_values"],
        "exact_accepted_recall": report["exact_accepted_recall"],
    }, indent=2))


if __name__ == "__main__":
    main()

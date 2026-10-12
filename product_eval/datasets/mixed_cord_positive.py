"""Score CORD positives only after a complete mixed product gate receipt."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from product_eval.contracts import load_jsonl
from product_eval.datasets.cord_positive_score import score_cord_positive
from product_eval.datasets.cord_test import _sha256_file, _write_jsonl
from product_eval.datasets.mixed_vrdu_cord_train import MixedGateError, _read_metadata


def _verify_hash(path: Path, expected: Any) -> None:
    if not isinstance(expected, str) or not path.is_file() or _sha256_file(path) != expected:
        raise MixedGateError(f"Missing or changed completed-gate receipt: {path}")


def score_mixed_cord_positive(bundle_dir: Path, gate_report_dir: Path, output_path: Path,
                              *, min_unique: int = 2000) -> dict[str, Any]:
    """Require a sealed full-gate receipt before computing CORD positive recall."""
    bundle_dir, gate_report_dir, output_path = (
        path.resolve() for path in (bundle_dir, gate_report_dir, output_path)
    )
    subset_path = output_path.with_name(output_path.stem + ".candidates.jsonl")
    if output_path.exists() or subset_path.exists():
        raise MixedGateError("CORD score output files must be new")
    metadata = _read_metadata(bundle_dir / "metadata.json")
    file_hashes = metadata.get("files_sha256")
    if not isinstance(file_hashes, dict):
        raise MixedGateError("Mixed bundle lacks output file hashes")
    for name in ("cohort.jsonl", "gold.jsonl", "cohort_cord_train.jsonl", "gold_cord_train.jsonl"):
        _verify_hash(bundle_dir / name, file_hashes.get(name))
    provenance = _read_metadata(gate_report_dir / "provenance.json")
    if (provenance.get("cohort_sha256") != file_hashes["cohort.jsonl"] or
            provenance.get("gold_sha256") != file_hashes["gold.jsonl"] or
            provenance.get("model_configured") is not False or
            provenance.get("working_tree_dirty") is not False):
        raise MixedGateError("Gate provenance does not match this no-model mixed bundle")
    candidate_path = gate_report_dir / "candidates.jsonl"
    execution_path = gate_report_dir / "execution-report.json"
    quality_path = gate_report_dir / "quality-report.json"
    _verify_hash(candidate_path, provenance.get("candidate_sha256"))
    _verify_hash(execution_path, provenance.get("execution_report_sha256"))
    _verify_hash(quality_path, provenance.get("quality_report_sha256"))
    execution = _read_metadata(execution_path)
    if (type(min_unique) is not int or min_unique < 1 or
            execution.get("documents") != metadata.get("cohort_count") or
            execution.get("distinct_sources") != metadata.get("cohort_count") or
            type(execution.get("distinct_sources")) is not int or
            execution["distinct_sources"] < min_unique or
            execution.get("repeated_source_outputs") != 0 or
            execution.get("source_hashes_verified") is not True):
        raise MixedGateError("Completed mixed gate lacks a distinct, source-verified execution receipt")
    cohort = [json.loads(line) for line in (bundle_dir / "cohort.jsonl").read_text(encoding="utf-8").splitlines()]
    cord = [json.loads(line) for line in (bundle_dir / "cohort_cord_train.jsonl").read_text(encoding="utf-8").splitlines()]
    all_ids = {row["doc_id"] for row in cohort}
    cord_ids = {row["doc_id"] for row in cord}
    full_by_id = {row["doc_id"]: row for row in cohort}
    if (len(all_ids) != len(cohort) or len(cord_ids) != len(cord) or not cord_ids or
            not cord_ids <= all_ids or
            any(row.get("dataset_id") != "cord_v2_train" or full_by_id[row["doc_id"]] != row for row in cord) or
            {row["doc_id"] for row in cohort if row.get("dataset_id") == "cord_v2_train"} != cord_ids):
        raise MixedGateError("Mixed/CORD source subsets are inconsistent")
    candidates = load_jsonl(candidate_path, kind="candidate")
    if set(candidates) != all_ids:
        raise MixedGateError("Completed-gate candidates do not cover exactly the mixed cohort")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cord-positive.", dir=output_path.parent) as temporary:
        staged_subset = Path(temporary) / "candidates.jsonl"
        _write_jsonl(staged_subset, [candidates[doc_id] for doc_id in sorted(cord_ids)])
        result = score_cord_positive(bundle_dir / "cohort_cord_train.jsonl",
                                     bundle_dir / "gold_cord_train.jsonl", staged_subset)
        result["mixed_gate_provenance_sha256"] = _sha256_file(gate_report_dir / "provenance.json")
        result["mixed_gate_execution_sha256"] = _sha256_file(execution_path)
        result["mixed_gate_candidate_sha256"] = _sha256_file(candidate_path)
        staged_report = Path(temporary) / "report.json"
        staged_report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if output_path.exists() or subset_path.exists():
            raise MixedGateError("CORD score output files appeared during scoring")
        staged_subset.rename(subset_path)
        staged_report.rename(output_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--gate-report-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = score_mixed_cord_positive(args.bundle_dir, args.gate_report_dir, args.output)
    except (MixedGateError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({key: result[key] for key in (
        "source_count", "exact_proposed_scalar_recall", "exact_proposed_cell_recall",
        "exact_proposed_complete_row_recall",
    )}, indent=2))


if __name__ == "__main__":
    main()

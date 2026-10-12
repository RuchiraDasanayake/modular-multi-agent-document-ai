"""Score CORD positives only after a complete mixed product gate receipt."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from product_eval.contracts import load_jsonl
from product_eval.datasets.cord_positive_score import score_cord_positive
from product_eval.datasets.cord_test import _sha256_file, _write_jsonl
from product_eval.datasets.mixed_vrdu_cord_train import MixedGateError, _read_metadata
from product_eval.execution import verify_result_receipts, verify_runs
from product_eval.scorer import score_records

_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _verify_hash(path: Path, expected: Any) -> None:
    if not isinstance(expected, str) or not path.is_file() or _sha256_file(path) != expected:
        raise MixedGateError(f"Missing or changed completed-gate receipt: {path}")


def _run_dirs(bundle_dir: Path, provenance: dict[str, Any], metadata: dict[str, Any],
              min_unique: int) -> list[Path]:
    gate_id, data_dir = provenance.get("gate_id"), provenance.get("data_dir")
    shards, run_ids = provenance.get("shard_dirs"), provenance.get("run_ids")
    if (not isinstance(gate_id, str) or not _SAFE_ID.fullmatch(gate_id) or
            not isinstance(data_dir, str) or not Path(data_dir).is_absolute() or
            not isinstance(shards, list) or not shards or shards != metadata.get("shard_dirs") or
            not isinstance(run_ids, list) or len(run_ids) != len(shards) or
            type(provenance.get("min_unique")) is not int or
            provenance["min_unique"] < min_unique or
            provenance.get("cohort_path") != str(bundle_dir / "cohort.jsonl") or
            provenance.get("gold_path") != str(bundle_dir / "gold.jsonl")):
        raise MixedGateError("Mixed gate lacks matching run IDs, shards, source paths, or data directory")
    expected_runs: list[str] = []
    for shard in shards:
        if not isinstance(shard, str) or not Path(shard).is_absolute():
            raise MixedGateError("Mixed gate shard path is invalid")
        shard_path = Path(shard).resolve(strict=True)
        if not shard_path.is_dir() or not shard_path.is_relative_to(bundle_dir / "shards"):
            raise MixedGateError("Mixed gate shard does not belong to the frozen bundle")
        run_id = f"{gate_id}_{shard_path.name}"
        if not _SAFE_ID.fullmatch(run_id):
            raise MixedGateError("Mixed gate run ID is invalid")
        expected_runs.append(run_id)
    if run_ids != expected_runs or len(set(run_ids)) != len(run_ids):
        raise MixedGateError("Mixed gate run IDs do not match its frozen shards")
    runs_root = Path(data_dir).resolve(strict=True) / "product_runs"
    run_dirs = [runs_root / run_id for run_id in run_ids]
    if any(not run_dir.resolve(strict=True).is_relative_to(runs_root) for run_dir in run_dirs):
        raise MixedGateError("Mixed gate run directory escapes the declared data directory")
    return run_dirs


def _verify_completed_runs(bundle_dir: Path, gate_report_dir: Path,
                           provenance: dict[str, Any], metadata: dict[str, Any],
                           cohort: list[dict[str, Any]], candidate_path: Path,
                           execution: dict[str, Any], quality_path: Path,
                           min_unique: int) -> dict[str, dict[str, Any]]:
    run_dirs = _run_dirs(bundle_dir, provenance, metadata, min_unique)
    _verify_hash(gate_report_dir / "exit-codes.json", provenance.get("exit_codes_sha256"))
    exit_codes = _read_metadata(gate_report_dir / "exit-codes.json")
    if exit_codes != {run_id: 0 for run_id in provenance["run_ids"]}:
        raise MixedGateError("Mixed gate has no successful subprocess exit receipt for every run")
    recomputed_execution = verify_runs(run_dirs, min_unique=min_unique)
    if (_canonical_json(execution) != _canonical_json({
            **recomputed_execution, "result_hashes_and_candidates_verified": True}) or
            verify_result_receipts(run_dirs) != recomputed_execution["documents"]):
        raise MixedGateError("Mixed gate execution or sealed product results differ from the runs")

    cohort_by_id = {row["doc_id"]: row for row in cohort}
    observed_ids: set[str] = set()
    run_candidates: dict[str, dict[str, Any]] = {}
    for run_dir, run_id in zip(run_dirs, provenance["run_ids"]):
        shard_name = run_id[len(provenance["gate_id"]) + 1:]
        for line in (run_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            receipt = json.loads(line)
            doc_id = receipt["doc_id"]
            row = cohort_by_id.get(doc_id)
            source_path = Path(row["source_path"]) if row is not None else None
            if (row is None or doc_id in observed_ids or row.get("gate_shard") != shard_name or
                    not source_path.is_absolute() or
                    not source_path.resolve(strict=True).is_relative_to(bundle_dir / "shards" / shard_name) or
                    receipt.get("run_id") != run_id or
                    receipt.get("source_hash_kind") != "raw_file" or
                    receipt.get("source_index") != 0 or
                    receipt.get("source_sha256") != row.get("source_sha256") or
                    receipt.get("source_size_bytes") != row.get("source_size_bytes") or
                    receipt.get("source_path") != row.get("source_path") or
                    receipt.get("source_file") != Path(row["source_path"]).name or
                    receipt.get("model_call_count") != 0):
                raise MixedGateError(f"Mixed gate run/source receipt differs from cohort: {doc_id}")
            observed_ids.add(doc_id)
        for doc_id, candidate in load_jsonl(run_dir / "candidates.jsonl", kind="candidate").items():
            if doc_id in run_candidates:
                raise MixedGateError(f"Mixed gate duplicates scored candidate: {doc_id}")
            run_candidates[doc_id] = candidate
    if observed_ids != set(cohort_by_id):
        raise MixedGateError("Mixed gate runs do not cover exactly the frozen source cohort")
    candidates = load_jsonl(candidate_path, kind="candidate")
    if _canonical_json(candidates) != _canonical_json(run_candidates):
        raise MixedGateError("Mixed gate aggregate candidates differ from sealed product runs")
    gold = load_jsonl(bundle_dir / "gold.jsonl", kind="gold")
    if set(gold) != set(cohort_by_id):
        raise MixedGateError("Mixed gate gold does not cover exactly the frozen source cohort")
    if _canonical_json(_read_metadata(quality_path)) != _canonical_json(score_records(gold, candidates)):
        raise MixedGateError("Mixed gate quality differs from recomputed full-cohort quality")
    return candidates


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
    candidates = _verify_completed_runs(bundle_dir, gate_report_dir, provenance, metadata, cohort,
                                        candidate_path, execution, quality_path, min_unique)
    if set(candidates) != all_ids:
        raise MixedGateError("Completed-gate candidates do not cover exactly the mixed cohort")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cord-positive.", dir=output_path.parent) as temporary:
        staged_subset = Path(temporary) / "candidates.jsonl"
        _write_jsonl(staged_subset, [candidates[doc_id] for doc_id in sorted(cord_ids)])
        result = score_cord_positive(bundle_dir / "cohort_cord_train.jsonl",
                                     bundle_dir / "gold_cord_train.jsonl", staged_subset)
        result["dataset_id"] = "cord_v2_train"
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

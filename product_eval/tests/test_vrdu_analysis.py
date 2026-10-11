from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from product_eval.contracts import load_jsonl
from product_eval.datasets.vrdu_analysis import (
    AnalysisError,
    analyze_vrdu,
    analyze_vrdu_runs,
)
from product_eval.scorer import score_records

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _cohort(tmp_path: Path, hashes: tuple[str, str] = ("a" * 64, "b" * 64)) -> Path:
    path = tmp_path / "cohort.jsonl"
    rows = [
        {"doc_id": "synthetic-invoice-1", "family": "registration-form", "source_sha256": hashes[0]},
        {"doc_id": "synthetic-request-1", "family": "ad-buy-form", "source_sha256": hashes[1]},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _candidate_shards(tmp_path: Path) -> tuple[Path, Path]:
    rows = (FIXTURES / "candidate.jsonl").read_text(encoding="utf-8").splitlines()
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text(rows[0] + "\n", encoding="utf-8")
    second.write_text(rows[1] + "\n", encoding="utf-8")
    return first, second


def test_family_report_uses_unchanged_scorer_and_counts_abstentions(tmp_path: Path) -> None:
    cohort = _cohort(tmp_path)
    first, second = _candidate_shards(tmp_path)
    gold_path = FIXTURES / "gold.jsonl"
    gold = load_jsonl(gold_path, kind="gold")
    candidate = load_jsonl(FIXTURES / "candidate.jsonl", kind="candidate")
    official_report = tmp_path / "report.json"
    official_report.write_text(json.dumps(score_records(gold, candidate)), encoding="utf-8")

    result = analyze_vrdu(cohort, gold_path, [first, second], full_report_path=official_report)
    assert result["cohort_documents"] == result["candidate_documents"] == 2
    assert result["overall"]["score"]["schema"] == score_records(gold, candidate)["schema"]
    assert result["by_family"]["registration-form"]["score"]["values"]["tp"] == 2
    assert result["by_family"]["ad-buy-form"]["score"]["values"]["false_accepted"] == 2
    assert result["by_family"]["ad-buy-form"]["outcomes"]["missing_present_gold_fields"] == 1
    assert result["by_family"]["registration-form"]["outcomes"]["present_gold_fields"] == 2


def test_family_report_keeps_missing_candidate_document_in_denominator(tmp_path: Path) -> None:
    first, _ = _candidate_shards(tmp_path)
    result = analyze_vrdu(_cohort(tmp_path), FIXTURES / "gold.jsonl", [first])
    ad_buy = result["by_family"]["ad-buy-form"]
    assert ad_buy["score"]["documents"]["gold"] == 1
    assert ad_buy["score"]["documents"]["candidate"] == 0
    assert ad_buy["score"]["documents"]["missing_candidate"] == 1
    assert ad_buy["outcomes"]["document_status"] == {"no_output": 1}
    assert ad_buy["outcomes"]["missing_present_gold_fields"] == 2


def test_family_report_rejects_duplicate_shards_and_mismatched_report(tmp_path: Path) -> None:
    first, second = _candidate_shards(tmp_path)
    cohort = _cohort(tmp_path)
    with pytest.raises(AnalysisError, match="Duplicate candidate doc_id"):
        analyze_vrdu(cohort, FIXTURES / "gold.jsonl", [first, first])
    mismatch = tmp_path / "wrong-report.json"
    mismatch.write_text("{}", encoding="utf-8")
    with pytest.raises(AnalysisError, match="does not match"):
        analyze_vrdu(cohort, FIXTURES / "gold.jsonl", [first, second], full_report_path=mismatch)


def _completed_run(tmp_path: Path, run_id: str, candidate: dict[str, object], source: Path) -> Path:
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    source_bytes = source.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    receipt = {
        "contract_version": 1,
        "run_id": run_id,
        "doc_id": candidate["doc_id"],
        "source_path": str(source),
        "source_sha256": source_hash,
        "source_hash_kind": "raw_file",
        "source_index": 0,
        "source_size_bytes": len(source_bytes),
        "document_status": candidate["document_status"],
        "duration_ms": 1.0,
        "page_count": 1,
        "model_call_count": 0,
    }
    counts = {status: int(candidate["document_status"] == status) for status in ("processed", "needs_review", "unsupported", "failed")}
    run = {"contract_version": 1, "run_id": run_id, "mode": "product_auto", "doc_count": 1, "status_counts": counts}
    (run_dir / "manifest.jsonl").write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    (run_dir / "candidates.jsonl").write_text(json.dumps(candidate) + "\n", encoding="utf-8")
    (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
    return run_dir


def test_run_directory_mode_verifies_real_source_hashes_and_cohort_join(tmp_path: Path) -> None:
    source_a = tmp_path / "a.pdf"
    source_b = tmp_path / "b.pdf"
    source_a.write_bytes(b"%PDF-1.4\na")
    source_b.write_bytes(b"%PDF-1.4\nb")
    hashes = tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in (source_a, source_b))
    cohort = _cohort(tmp_path, hashes)
    candidates = list(load_jsonl(FIXTURES / "candidate.jsonl", kind="candidate").values())
    run_a = _completed_run(tmp_path, "run-a", candidates[0], source_a)
    run_b = _completed_run(tmp_path, "run-b", candidates[1], source_b)
    report = analyze_vrdu_runs(cohort, FIXTURES / "gold.jsonl", [run_a, run_b])
    assert report["run_verification"]["documents"] == 2
    assert report["run_verification"]["distinct_sources"] == 2
    assert report["by_family"]["ad-buy-form"]["diagnostics"]["top_spurious_candidate_field_ids"] == {"claim_number": 1}
    cohort.write_text(cohort.read_text(encoding="utf-8").replace(hashes[0], "c" * 64), encoding="utf-8")
    with pytest.raises(AnalysisError, match="does not match frozen VRDU cohort"):
        analyze_vrdu_runs(cohort, FIXTURES / "gold.jsonl", [run_a, run_b])

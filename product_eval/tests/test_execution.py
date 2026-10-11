from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from product_eval.contracts import ContractError
from product_eval.execution import verify_run, verify_runs


def _write_run(tmp_path: Path, source: Path, *, source_hash_kind: str = "raw_file") -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    payload = source.read_bytes()
    if source_hash_kind == "canonical_json_entry":
        item = json.loads(payload)[0]
        payload = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    receipt = {
        "contract_version": 1,
        "run_id": "test-run",
        "doc_id": "doc-1",
        "source_path": str(source),
        "source_file": source.name,
        "source_index": 0,
        "source_hash_kind": source_hash_kind,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "source_container_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_size_bytes": len(payload),
        "document_status": "needs_review",
        "duration_ms": 2.0,
        "page_count": 1,
        "model_call_count": 0,
    }
    candidate = {
        "contract_version": 1,
        "doc_id": "doc-1",
        "document_status": "needs_review",
        "proposed_schema": [],
        "extracted_values": [],
    }
    run = {
        "contract_version": 1,
        "run_id": "test-run",
        "mode": "product_auto",
        "doc_count": 1,
        "status_counts": {"processed": 0, "needs_review": 1, "unsupported": 0, "failed": 0},
    }
    (run_dir / "manifest.jsonl").write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    (run_dir / "candidates.jsonl").write_text(json.dumps(candidate) + "\n", encoding="utf-8")
    (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
    return run_dir


def test_verify_run_checks_bytes_and_release_floor(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("Invoice number: I-1\n", encoding="utf-8")
    run_dir = _write_run(tmp_path, source)

    report = verify_run(run_dir, min_unique=1)
    assert report["documents"] == report["distinct_sources"] == 1
    assert report["source_hashes_verified"] is True
    with pytest.raises(ContractError, match="requires 2"):
        verify_run(run_dir, min_unique=2)
    source.write_text("tampered", encoding="utf-8")
    with pytest.raises(ContractError, match="size changed|does not match"):
        verify_run(run_dir, min_unique=1)


def test_verify_run_hashes_individual_json_array_entries(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text('[{"name":"A"},{"name":"B"}]', encoding="utf-8")
    run_dir = _write_run(tmp_path, source, source_hash_kind="canonical_json_entry")
    assert verify_run(run_dir, min_unique=1)["distinct_sources"] == 1
    manifest_path = run_dir / "manifest.jsonl"
    receipt = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt["source_index"] = 1
    manifest_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    with pytest.raises(ContractError, match="does not match source content"):
        verify_run(run_dir)


def test_verify_run_requires_one_receipt_per_candidate_and_completion(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("x", encoding="utf-8")
    run_dir = _write_run(tmp_path, source)
    (run_dir / "candidates.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ContractError, match="doc_id mismatch"):
        verify_run(run_dir)
    (run_dir / "run.json").unlink()
    with pytest.raises(ContractError, match="cannot read JSON"):
        verify_run(run_dir)


def test_verify_runs_counts_distinct_sources_across_shards(tmp_path: Path) -> None:
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    first = one / "first.txt"
    second = two / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    run_one = _write_run(one, first)
    run_two = _write_run(two, second)
    second_receipt_path = run_two / "manifest.jsonl"
    second_receipt = json.loads(second_receipt_path.read_text(encoding="utf-8"))
    second_receipt["run_id"] = "test-run-2"
    second_receipt["doc_id"] = "doc-2"
    second_receipt_path.write_text(json.dumps(second_receipt) + "\n", encoding="utf-8")
    second_candidate_path = run_two / "candidates.jsonl"
    second_candidate = json.loads(second_candidate_path.read_text(encoding="utf-8"))
    second_candidate["doc_id"] = "doc-2"
    second_candidate_path.write_text(json.dumps(second_candidate) + "\n", encoding="utf-8")
    second_run_path = run_two / "run.json"
    second_run = json.loads(second_run_path.read_text(encoding="utf-8"))
    second_run["run_id"] = "test-run-2"
    second_run_path.write_text(json.dumps(second_run), encoding="utf-8")

    assert verify_runs([run_one, run_two], min_unique=2)["documents"] == 2
    second.write_text("first", encoding="utf-8")
    second_receipt["source_sha256"] = hashlib.sha256(second.read_bytes()).hexdigest()
    second_receipt["source_size_bytes"] = second.stat().st_size
    second_receipt_path.write_text(json.dumps(second_receipt) + "\n", encoding="utf-8")
    with pytest.raises(ContractError, match="requires 2"):
        verify_runs([run_one, run_two], min_unique=2)

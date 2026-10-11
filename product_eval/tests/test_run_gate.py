from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from product_eval.run_gate import run_gate


def _gold_record(path: Path, value: str) -> dict[str, object]:
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    doc_id = hashlib.sha256(f"{path.name}\0{source_hash}\0{0}".encode()).hexdigest()[:32]
    return {
        "contract_version": 1,
        "doc_id": doc_id,
        "pages": [{"page": 1, "text": path.read_text(encoding="utf-8").strip()}],
        "gold_schema": [{"field_id": "invoice", "type": "string", "critical": False}],
        "gold_values": [{"field_id": "invoice", "value": value}],
    }


def test_gate_runs_distinct_shards_and_scores_only_after_source_verification(tmp_path: Path) -> None:
    shards = [tmp_path / "shard_a", tmp_path / "shard_b"]
    records = []
    for shard, value in zip(shards, ("A-1", "B-2")):
        shard.mkdir()
        source = shard / "invoice.txt"
        source.write_text(f"Invoice: {value}\n", encoding="utf-8")
        records.append(_gold_record(source, value))
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    data_dir = tmp_path / "data"
    report_dir = tmp_path / "report"
    result = run_gate(
        shards, gold_path=gold_path, data_dir=data_dir, report_dir=report_dir,
        gate_id="small_gate", min_unique=2, max_workers=2,
    )

    assert result["execution"]["documents"] == 2
    assert result["execution"]["distinct_sources"] == 2
    assert result["execution"]["source_hashes_verified"] is True
    assert result["quality"]["schema"]["tp"] == 2
    assert result["provenance"]["model_configured"] is False
    assert len((report_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    assert len(list(report_dir.glob("small_gate_*.log"))) == 2

    with pytest.raises(ValueError, match="must be new"):
        run_gate(
            shards, gold_path=gold_path, data_dir=data_dir, report_dir=report_dir,
            gate_id="small_gate", min_unique=2,
        )


def test_gate_rejects_repeated_or_unsafe_shards_before_start(tmp_path: Path) -> None:
    shard = tmp_path / "shard"
    shard.mkdir()
    (shard / "source.txt").write_text("x", encoding="utf-8")
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text("{}\n", encoding="utf-8")
    kwargs = {"gold_path": gold_path, "data_dir": tmp_path / "data", "report_dir": tmp_path / "report"}

    with pytest.raises(ValueError, match="distinct"):
        run_gate([shard, shard], gate_id="repeat", **kwargs)
    with pytest.raises(ValueError, match="gate_id must be safe"):
        run_gate([shard], gate_id="bad id", **kwargs)
    assert not (tmp_path / "report").exists()

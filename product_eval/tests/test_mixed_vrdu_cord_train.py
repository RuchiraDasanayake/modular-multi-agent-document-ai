from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from product_eval.contracts import load_jsonl
from product_eval.datasets import mixed_vrdu_cord_train as mixed
from product_eval.datasets.cord_test import _doc_id
from product_eval.datasets.mixed_cord_positive import score_mixed_cord_positive
from product_eval.datasets.vrdu_analysis import analyze_vrdu


def test_pinned_train_manifest_has_four_full_sha256_hashes() -> None:
    assert len(mixed.TRAIN_FILES) == 4
    assert all(len(pin.sha256) == 64 and set(pin.sha256) <= set("0123456789abcdef")
               and pin.size > 0 and pin.name.startswith("train-") for pin in mixed.TRAIN_FILES)


def _png(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> str:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt(path: Path, *, dataset_id: str, family: str, split: str | None = None) -> dict[str, object]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    row: dict[str, object] = {
        "dataset_id": dataset_id, "source_id": f"fixture/{path.name}", "family": family,
        "source_path": str(path), "source_sha256": digest,
        "source_size_bytes": path.stat().st_size, "doc_id": _doc_id(path.name, digest),
    }
    if split:
        row["evaluation_split"] = split
    return row


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, bad_split: bool = False
             ) -> tuple[Path, Path, Path]:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    train_root = tmp_path / "train"
    data_dir = train_root / "data"
    data_dir.mkdir(parents=True)
    (train_root / "README.md").write_text("---\nlicense: cc-by-4.0\n---\n", encoding="utf-8")
    annotations = [
        {"gt_parse": {"total": {"total_price": "5.00"}, "menu": [
            {"nm": "Tea", "cnt": "2", "price": "5.00"}]},
         "meta": {"split": "train", "version": "2.0.0"}},
        {"gt_parse": {"sub_total": {"tax_price": "1.00"}, "menu": [
            {"nm": "Bread", "price": "4.00"}]},
         "meta": {"split": "test" if bad_split else "train", "version": "2.0.0"}},
    ]
    table = pa.Table.from_pylist([
        {"image": {"bytes": _png(color), "path": None}, "ground_truth": json.dumps(annotation)}
        for color, annotation in zip(("red", "blue"), annotations)
    ])
    shard = data_dir / "train-00000-of-00001-fixture.parquet"
    pq.write_table(table, shard)
    monkeypatch.setattr(mixed, "TRAIN_FILES", (mixed.ParquetPin(
        shard.name, shard.stat().st_size, hashlib.sha256(shard.read_bytes()).hexdigest()),))
    monkeypatch.setattr(mixed, "EXPECTED_TRAIN_ROWS", 2)

    vrdu_dir = tmp_path / "vrdu"
    vrdu_dir.mkdir()
    vrdu_rows = []
    vrdu_gold = []
    for index in range(3):
        source = vrdu_dir / f"form_{index}.pdf"
        source.write_bytes(f"%PDF-1.4 fixture {index}".encode())
        receipt = _receipt(source, dataset_id="vrdu", family="registration-form")
        vrdu_rows.append(receipt)
        vrdu_gold.append({"contract_version": 1, "doc_id": receipt["doc_id"],
                          "pages": [{"page": 1, "text": ""}], "gold_schema": [], "gold_values": []})
    cohort_hash = _write_jsonl(vrdu_dir / "cohort.jsonl", vrdu_rows)
    gold_hash = _write_jsonl(vrdu_dir / "gold.jsonl", vrdu_gold)
    (vrdu_dir / "metadata.json").write_text(json.dumps({
        "dataset_commit": mixed.VRDU_COMMIT,
        "files_sha256": {"cohort.jsonl": cohort_hash, "gold.jsonl": gold_hash},
    }), encoding="utf-8")
    monkeypatch.setattr(mixed, "VRDU_COHORT_SHA256", cohort_hash)
    monkeypatch.setattr(mixed, "VRDU_GOLD_SHA256", gold_hash)
    monkeypatch.setattr(mixed, "EXPECTED_VRDU_COUNT", 3)

    test_dir = tmp_path / "cord-test"
    test_dir.mkdir()
    held_out = test_dir / "cord_test_0000.png"
    held_out.write_bytes(_png("green"))
    test_hash = _write_jsonl(test_dir / "cohort.jsonl", [
        _receipt(held_out, dataset_id="cord_v2_test", family="receipt", split="reserved")])
    (test_dir / "metadata.json").write_text(json.dumps({
        "creator_dataset_revision": mixed.DATASET_REVISION,
        "creator_file_sha256": mixed.CORD_TEST_PARQUET_SHA256,
        "files_sha256": {"cohort.jsonl": test_hash},
    }), encoding="utf-8")
    monkeypatch.setattr(mixed, "CORD_TEST_COHORT_SHA256", test_hash)
    monkeypatch.setattr(mixed, "EXPECTED_CORD_TEST_COUNT", 1)
    monkeypatch.setattr(mixed, "EXPECTED_CORD_RESERVED_COUNT", 1)
    return train_root, vrdu_dir, test_dir


def test_mixed_builder_stages_distinct_sources_and_positive_linked_gold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_root, vrdu, test = _fixture(tmp_path, monkeypatch)
    output = tmp_path / "bundle"
    metadata = mixed.build_mixed_gate(train_root, vrdu, test, output, target=4, shard_count=2)
    assert metadata["cohort_count"] == metadata["distinct_source_sha256_count"] == 4
    assert metadata["dataset_counts"] == {"cord_v2_train": 2, "vrdu": 2}
    cohort = [json.loads(line) for line in (output / "cohort.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len({row["source_sha256"] for row in cohort}) == 4
    assert all(Path(row["source_path"]).is_file() for row in cohort)
    assert all(hashlib.sha256(Path(row["source_path"]).read_bytes()).hexdigest() == row["source_sha256"]
               for row in cohort)
    assert len(list((output / "shards").glob("shard_*"))) == 2
    cord_gold = load_jsonl(output / "gold_cord_train.jsonl", kind="gold")
    assert len(cord_gold) == 2
    assert any({"field_id": "item_name", "value": [{"row": 0, "value": "Tea"}]}
               in gold["gold_values"] for gold in cord_gold.values())
    assert any({"field_id": "total_amount", "value": "5.00"}
               in gold["gold_values"] for gold in cord_gold.values())
    assert set(load_jsonl(output / "gold.jsonl", kind="gold")) == {row["doc_id"] for row in cohort}
    assert all(row["source_sha256"] != hashlib.sha256((test / "cord_test_0000.png").read_bytes()).hexdigest()
               for row in cohort)


def test_mixed_builder_fails_closed_on_insufficient_sources_or_changed_parquet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_root, vrdu, test = _fixture(tmp_path, monkeypatch)
    with pytest.raises(mixed.MixedGateError, match="distinct train/VRDU sources"):
        mixed.build_mixed_gate(train_root, vrdu, test, tmp_path / "too-large", target=6, shard_count=2)
    assert not (tmp_path / "too-large").exists()

    shard = next((train_root / "data").iterdir())
    shard.write_bytes(shard.read_bytes() + b"changed")
    with pytest.raises(mixed.MixedGateError, match="size changed"):
        mixed.build_mixed_gate(train_root, vrdu, test, tmp_path / "tampered", target=4, shard_count=2)
    assert not (tmp_path / "tampered").exists()


def test_mixed_builder_rejects_nontrain_annotations_and_extra_split_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_root, vrdu, test = _fixture(tmp_path, monkeypatch, bad_split=True)
    with pytest.raises(ValueError, match="unexpected split/version"):
        mixed.build_mixed_gate(train_root, vrdu, test, tmp_path / "bad-split", target=4, shard_count=2)
    assert not (tmp_path / "bad-split").exists()
    (train_root / "data" / "validation-00000.parquet").write_bytes(b"not allowed")
    with pytest.raises(mixed.MixedGateError, match="exactly the four pinned train shards"):
        mixed.build_mixed_gate(train_root, vrdu, test, tmp_path / "mixed-splits", target=4, shard_count=2)


def test_source_only_selection_excludes_holdout_overlap_and_deduplicates() -> None:
    train = [
        {"source_sha256": digest, "source_id": f"train/{index}", "doc_id": f"cord_{index}"}
        for index, digest in enumerate(("a" * 64, "b" * 64, "c" * 64, "c" * 64))
    ]
    vrdu = [
        {"source_sha256": digest, "doc_id": f"vrdu_{index}"}
        for index, digest in enumerate(("b" * 64, "d" * 64, "e" * 64))
    ]
    cord, pdfs, counts = mixed._select_sources(train, vrdu, {"a" * 64}, target=3)
    assert [row["source_sha256"] for row in cord] == ["c" * 64]
    assert len(pdfs) == 2
    assert {row["source_sha256"] for row in pdfs} <= {"b" * 64, "d" * 64, "e" * 64}
    assert len({row["source_sha256"] for row in cord + pdfs}) == 3
    assert counts == {"overlap_cord_test": 1, "overlap_vrdu": 1, "duplicate_train_bytes": 1}


def test_cord_positive_score_requires_completed_hash_bound_mixed_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_root, vrdu, test = _fixture(tmp_path, monkeypatch)
    bundle = tmp_path / "bundle"
    mixed.build_mixed_gate(train_root, vrdu, test, bundle, target=4, shard_count=2)
    gate = tmp_path / "gate"
    gate.mkdir()
    cohort = [json.loads(line) for line in (bundle / "cohort.jsonl").read_text(encoding="utf-8").splitlines()]
    candidate_hash = _write_jsonl(gate / "candidates.jsonl", [
        {"contract_version": 1, "doc_id": row["doc_id"], "document_status": "needs_review",
         "proposed_schema": [], "extracted_values": []} for row in cohort
    ])
    family_report = analyze_vrdu(bundle / "cohort.jsonl", bundle / "gold.jsonl", [gate / "candidates.jsonl"])
    assert set(family_report["by_family"]) == {"receipt", "registration-form"}
    execution = {"documents": 4, "distinct_sources": 4, "repeated_source_outputs": 0,
                 "source_hashes_verified": True}
    (gate / "execution-report.json").write_text(json.dumps(execution), encoding="utf-8")
    (gate / "quality-report.json").write_text("{}\n", encoding="utf-8")
    metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    provenance = {
        "cohort_sha256": metadata["files_sha256"]["cohort.jsonl"],
        "gold_sha256": metadata["files_sha256"]["gold.jsonl"],
        "candidate_sha256": candidate_hash,
        "execution_report_sha256": hashlib.sha256((gate / "execution-report.json").read_bytes()).hexdigest(),
        "quality_report_sha256": hashlib.sha256((gate / "quality-report.json").read_bytes()).hexdigest(),
        "model_configured": False, "working_tree_dirty": False,
    }
    (gate / "provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    report_path = gate / "cord-positive.json"
    report = score_mixed_cord_positive(bundle, gate, report_path, min_unique=4)
    assert report["source_count"] == 2
    assert report["exact_proposed_scalar_recall"] == 0
    assert report["exact_proposed_complete_row_recall"] == 0
    assert len(load_jsonl(gate / "cord-positive.candidates.jsonl", kind="candidate")) == 2

    provenance["candidate_sha256"] = "0" * 64
    (gate / "provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    with pytest.raises(mixed.MixedGateError, match="changed completed-gate receipt"):
        score_mixed_cord_positive(bundle, gate, gate / "tampered.json", min_unique=4)
    assert not (gate / "tampered.json").exists()

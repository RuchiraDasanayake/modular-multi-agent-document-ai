from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from idpo.product_auto.workflow import _doc_id as runtime_doc_id
from product_eval.contracts import load_jsonl
from product_eval.datasets.funsd_positive_score import score_positive_only
from product_eval.datasets.funsd_remainder import (
    FunsdSliceError,
    _linked_answers,
    build_funsd_remainder,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _annotation(*, with_link: bool) -> dict[str, object]:
    answer_link = [[1, 2]] if with_link else []
    return {
        "form": [
            {"id": 1, "label": "question", "text": "TO:", "linking": answer_link},
            {"id": 2, "label": "answer", "text": "Ada Lovelace", "linking": answer_link},
        ]
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    images = tmp_path / "images"
    annotations = tmp_path / "annotations"
    images.mkdir()
    annotations.mkdir()
    for stem in ("a", "b", "c"):
        (images / f"{stem}.png").write_bytes(f"image-{stem}".encode())
        (annotations / f"{stem}.json").write_text(
            json.dumps(_annotation(with_link=stem == "b")), encoding="utf-8"
        )
    pack = tmp_path / "historic.json"
    pack.write_text(json.dumps({"cases": [{"case_id": "funsd_a"}]}), encoding="utf-8")
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({
        "adapter_version": 1,
        "source_test_count": 3,
        "historical_count": 1,
        "historical_pack_sha256": _sha256(pack),
        "entries": [
            {
                "stem": stem,
                "image_sha256": _sha256(images / f"{stem}.png"),
                "annotation_sha256": _sha256(annotations / f"{stem}.json"),
            }
            for stem in ("b", "c")
        ],
    }), encoding="utf-8")
    return images, annotations, pack, lock, tmp_path / "output"


def test_funsd_remainder_keeps_unscored_documents_in_execution_cohort(tmp_path: Path) -> None:
    images, annotations, pack, lock, output = _fixture(tmp_path)
    metadata = build_funsd_remainder(images, annotations, pack, lock, output)
    cohort = [json.loads(line) for line in (output / "cohort.jsonl").read_text().splitlines()]
    gold = load_jsonl(output / "gold.jsonl", kind="gold")
    exclusions = [json.loads(line) for line in (output / "exclusions.jsonl").read_text().splitlines()]

    assert (metadata["cohort_count"], metadata["gold_count"], metadata["gold_exclusion_count"]) == (2, 1, 1)
    assert metadata["gold_positive_field_coverage"] == {"recipient": 1}
    assert {item["source_id"] for item in cohort} == {
        "FUNSD/testing_data/b.png", "FUNSD/testing_data/c.png"
    }
    for item in cohort:
        source = Path(item["source_path"])
        assert source.parent == output / "input"
        assert _sha256(source) == item["source_sha256"]
        assert item["doc_id"] == runtime_doc_id(source.name, item["source_sha256"], 0)
    assert len(gold) == 1
    record = next(iter(gold.values()))
    assert record["gold_schema"] == [{"field_id": "recipient", "type": "string", "critical": False}]
    assert record["gold_values"] == [{"field_id": "recipient", "value": "Ada Lovelace"}]
    assert len(exclusions) == 1 and exclusions[0]["reason"] == "no_linked_DATE_TO_FROM_answer"


def test_funsd_remainder_rejects_changed_source_before_creating_output(tmp_path: Path) -> None:
    images, annotations, pack, lock, output = _fixture(tmp_path)
    (images / "b.png").write_bytes(b"changed")
    with pytest.raises(FunsdSliceError, match="Pinned FUNSD source bytes differ"):
        build_funsd_remainder(images, annotations, pack, lock, output)
    assert not output.exists()


def test_funsd_remainder_rejects_changed_historical_selection(tmp_path: Path) -> None:
    images, annotations, pack, lock, output = _fixture(tmp_path)
    pack.write_text(json.dumps({"cases": [{"case_id": "funsd_b"}]}), encoding="utf-8")
    with pytest.raises(FunsdSliceError, match="Historical FUNSD-20 pack differs"):
        build_funsd_remainder(images, annotations, pack, lock, output)
    assert not output.exists()


def test_funsd_mapping_reproduces_existing_historical_pack() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    pack = json.loads((repository_root / "datasets" / "funsd_pack_20.json").read_text(encoding="utf-8"))
    annotation_root = repository_root / "datasets" / "FUNSD" / "testing_data" / "annotations"
    assert len(pack["cases"]) == 20
    for case in pack["cases"]:
        stem = case["case_id"].removeprefix("funsd_")
        annotation = json.loads((annotation_root / f"{stem}.json").read_text(encoding="utf-8", errors="replace"))
        assert _linked_answers(annotation) == case["expected"]


def test_sparse_positive_scorer_keeps_unlabeled_source_in_denominator(tmp_path: Path) -> None:
    images, annotations, pack, lock, output = _fixture(tmp_path)
    build_funsd_remainder(images, annotations, pack, lock, output)
    cohort = [json.loads(line) for line in (output / "cohort.jsonl").read_text().splitlines()]
    b = next(item for item in cohort if item["source_id"].endswith("b.png"))
    c = next(item for item in cohort if item["source_id"].endswith("c.png"))
    candidate_path = tmp_path / "candidates.jsonl"
    candidate_path.write_text("\n".join(json.dumps(item) for item in (
        {
            "contract_version": 1,
            "doc_id": b["doc_id"],
            "document_status": "processed",
            "proposed_schema": [{"field_id": "recipient", "type": "string"}],
            "extracted_values": [{
                "field_id": "recipient", "value": "Ada Lovelace", "status": "accepted", "review_state": "none"
            }],
        },
        {
            "contract_version": 1,
            "doc_id": c["doc_id"],
            "document_status": "needs_review",
            "proposed_schema": [{"field_id": "another_field", "type": "string"}],
            "extracted_values": [{
                "field_id": "another_field", "value": "unscored", "status": "needs_review", "review_state": "pending"
            }],
        },
    )) + "\n", encoding="utf-8")
    report = score_positive_only(output / "cohort.jsonl", output / "gold.jsonl", candidate_path)
    assert report["source_count"] == report["source_hash_verified_count"] == 2
    assert report["scored_document_count"] == report["unscored_document_count"] == 1
    assert report["exact_accepted_values"] == report["annotated_positive_values"] == 1
    assert report["exact_accepted_recall"] == 1.0
    (output / "input" / "b.png").write_bytes(b"tampered after staging")
    with pytest.raises(FunsdSliceError, match="Source bytes differ"):
        score_positive_only(output / "cohort.jsonl", output / "gold.jsonl", candidate_path)

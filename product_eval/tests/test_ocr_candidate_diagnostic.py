"""Selection and scoring invariants for the read-only OCR diagnostic."""

import json
from pathlib import Path

import pytest

from product_eval.ocr_candidate_diagnostic import (
    scalar_targets,
    select_pages,
    target_coverage,
)


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_coverage_is_case_and_whitespace_insensitive_but_not_semantic() -> None:
    targets = [{"field_id": "name", "value": "Acme, Inc."}, {"field_id": "date", "value": "2026-10-12"}]
    result = target_coverage(targets, "ACME Inc\nDate: 12 Oct 2026")
    assert result == [
        {"field_id": "name", "matched": True},
        {"field_id": "date", "matched": False},
    ]


def test_scalar_targets_require_page_evidence_and_exclude_repeated_values() -> None:
    gold = {
        "gold_schema": [
            {"field_id": "name", "type": "string"},
            {"field_id": "rows", "type": "array[object]"},
        ],
        "gold_values": [
            {"field_id": "name", "value": "Acme", "evidence": {"page": 2}},
            {"field_id": "rows", "value": [{"row": 0, "value": "Acme"}], "evidence": {"page": 2}},
            {"field_id": "missing", "value": "Other", "evidence": {"page": 2}},
        ],
    }
    assert scalar_targets(gold, 1) == []
    assert scalar_targets(gold, 2) == [{"field_id": "name", "value": "Acme"}]


def test_selection_is_source_hash_ordered_and_rejects_hash_drift(tmp_path: Path) -> None:
    cohort = tmp_path / "cohort.jsonl"
    gold = tmp_path / "gold.jsonl"
    runs = tmp_path / "runs"
    _jsonl(cohort, [
        {"doc_id": "doc-a", "family": "f", "source_sha256": "b"},
        {"doc_id": "doc-b", "family": "f", "source_sha256": "a"},
    ])
    _jsonl(gold, [
        {"doc_id": doc_id,
         "gold_schema": [{"field_id": "name", "type": "string"}],
         "gold_values": [{"field_id": "name", "value": doc_id, "evidence": {"page": 1}}]}
        for doc_id in ("doc-a", "doc-b")
    ])
    for doc_id, source_hash in (("doc-a", "b"), ("doc-b", "a")):
        root = runs / "vrdu_v5_x"
        sidecar = root / "docs" / doc_id / "result.json"
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps({
            "source_sha256": source_hash,
            "pages": [{"page": 1, "text": doc_id}],
            "ocr_pages": [{"page": 1, "engine": "tesseract", "confidence": 75}],
        }), encoding="utf-8")
        image = root / "artifacts" / "derived_images" / f"{doc_id}_p1_pdf_render_1234.png"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"sample")
    selected = select_pages(cohort, gold, runs, per_family=1)
    assert [row["doc_id"] for row in selected] == ["doc-b"]
    bad = runs / "vrdu_v5_x" / "docs" / "doc-b" / "result.json"
    payload = json.loads(bad.read_text(encoding="utf-8"))
    payload["source_sha256"] = "wrong"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Source hash mismatch"):
        select_pages(cohort, gold, runs, per_family=1)

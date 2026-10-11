from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from idpo.product_auto.workflow import _doc_id as runtime_doc_id
from product_eval.datasets.cord_positive_score import score_cord_positive
from product_eval.datasets.cord_test import (
    CordSliceError,
    _annotation,
    _assign_splits,
    _doc_id,
    _gold_record,
)


def _source(tmp_path: Path, filename: str, content: bytes) -> dict[str, str]:
    path = tmp_path / filename
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    doc_id = _doc_id(filename, digest)
    assert doc_id == runtime_doc_id(filename, digest, 0)
    return {"source_path": str(path), "source_sha256": digest, "doc_id": doc_id}


def _gold(doc_id: str, total: str, name: str, price: str) -> dict[str, object]:
    return {
        "contract_version": 1,
        "doc_id": doc_id,
        "pages": [{"page": 1, "text": ""}],
        "gold_schema": [
            {"field_id": "total_amount", "type": "string", "critical": False},
            {"field_id": "item_name", "type": "array[object]", "critical": False},
            {"field_id": "item_price", "type": "array[object]", "critical": False},
        ],
        "gold_values": [
            {"field_id": "total_amount", "value": total},
            {"field_id": "item_name", "value": [{"row": 0, "value": name}]},
            {"field_id": "item_price", "value": [{"row": 0, "value": price}]},
        ],
    }


def test_cord_gold_maps_only_positive_scalar_and_ordered_menu_cells() -> None:
    annotation = {
        "gt_parse": {
            "total": {"total_price": "0", "cashprice": ["10", "20"]},
            "sub_total": {"tax_price": " 1.00 "},
            "menu": [
                {"nm": " Tea ", "cnt": "2", "price": "5.00", "sub": {"nm": "hot"}},
                {"nm": "Bread", "price": "3.00"},
            ],
        }
    }
    gold, stats = _gold_record("cord-doc", annotation)
    values = {item["field_id"]: item["value"] for item in gold["gold_values"]}
    assert values["total_amount"] == "0"
    assert values["tax_amount"] == "1.00"
    assert "cash_amount" not in values
    assert values["item_name"] == [{"row": 0, "value": "Tea"}, {"row": 1, "value": "Bread"}]
    assert values["item_quantity"] == [{"row": 0, "value": "2"}]
    assert values["item_price"] == [{"row": 0, "value": "5.00"}, {"row": 1, "value": "3.00"}]
    assert stats["non_scalar_summary_labels_excluded"] == 1
    assert stats["linked_positive_cells"] == 5
    assert stats["published_menu_rows"] == 2


def test_cord_source_only_split_keeps_visual_component_together() -> None:
    sources = [
        {"sha256": f"{number:064x}", "dhash": dhash, "aspect": aspect}
        for number, dhash, aspect in (
            (1, 0, 0.66),
            (2, 1, 0.66),
            (3, (1 << 64) - 1, 0.75),
        )
    ]
    splits, stats = _assign_splits(sources)
    assert splits[0] == splits[1]
    assert stats["component_count"] == 2
    assert stats["largest_component_size"] == 2
    assert _assign_splits(sources) == (splits, stats)


def test_cord_positive_scorer_counts_linked_rows_without_inventing_precision(tmp_path: Path) -> None:
    first = _source(tmp_path, "cord_test_0000.png", b"source-a")
    second = _source(tmp_path, "cord_test_0001.png", b"source-b")
    cohort = tmp_path / "cohort.jsonl"
    gold = tmp_path / "gold.jsonl"
    candidates = tmp_path / "candidates.jsonl"
    cohort.write_text("\n".join(json.dumps(item) for item in (first, second)) + "\n", encoding="utf-8")
    gold.write_text("\n".join(json.dumps(item) for item in (
        _gold(first["doc_id"], "5", "Tea", "5"),
        _gold(second["doc_id"], "2", "Bread", "2"),
    )) + "\n", encoding="utf-8")
    candidate = {
        "contract_version": 1,
        "doc_id": first["doc_id"],
        "document_status": "needs_review",
        "proposed_schema": [
            {"field_id": "total_amount", "type": "string"},
            {"field_id": "item_name", "type": "array[object]"},
            {"field_id": "item_price", "type": "array[object]"},
        ],
        "extracted_values": [
            {"field_id": "total_amount", "value": "5", "status": "accepted", "review_state": "none"},
            {"field_id": "item_name", "value": [{"row": 0, "value": "Tea"}], "status": "needs_review", "review_state": "pending"},
            {"field_id": "item_price", "value": [{"row": 0, "value": "5"}], "status": "needs_review", "review_state": "pending"},
        ],
    }
    candidates.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
    report = score_cord_positive(cohort, gold, candidates)
    assert report["source_count"] == 2 and report["missing_candidate_count"] == 1
    assert report["positive_scalars"]["annotated"] == 2
    assert report["exact_proposed_scalar_recall"] == 0.5
    assert report["exact_accepted_scalar_recall"] == 0.5
    assert report["positive_linked_cells"]["annotated"] == 4
    assert report["exact_proposed_cell_recall"] == 0.5
    assert report["positive_complete_rows"]["annotated"] == 2
    assert report["exact_proposed_complete_row_recall"] == 0.5
    assert report["exact_accepted_complete_row_recall"] == 0.0
    assert "precision" not in report

    candidate["extracted_values"][2]["value"][0]["row"] = 1
    candidates.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
    shifted = score_cord_positive(cohort, gold, candidates)
    assert shifted["exact_proposed_cell_recall"] == 0.25
    assert shifted["exact_proposed_complete_row_recall"] == 0.0

    Path(first["source_path"]).write_bytes(b"changed")
    with pytest.raises(CordSliceError, match="source image changed"):
        score_cord_positive(cohort, gold, candidates)


def test_cord_rejects_unexpected_creator_split() -> None:
    with pytest.raises(CordSliceError, match="unexpected split/version"):
        _annotation(json.dumps({"gt_parse": {}, "meta": {"split": "train", "version": "2.0.0"}}), 0)

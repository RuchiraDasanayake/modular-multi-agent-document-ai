from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_eval import docling_table_diagnostic as tables
from product_eval.contracts import ContractError


def test_source_path_rejects_traversal_and_other_families(tmp_path: Path) -> None:
    assert tables.source_path(tmp_path, "ad-buy-form/public.pdf") == (
        tmp_path / "ad-buy-form" / "main" / "pdfs" / "public.pdf"
    )
    for source_id in ("registration-form/public.pdf", "ad-buy-form/../secret.pdf",
                      "ad-buy-form/..\\secret.pdf", "ad-buy-form/a/b.pdf"):
        with pytest.raises(ContractError, match="source_id"):
            tables.source_path(tmp_path, source_id)


def test_frozen_selection_checks_rank_and_source_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = []
    for index in range(3):
        source_id = f"ad-buy-form/{index}.pdf"
        path = tables.source_path(tmp_path, source_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes([65 + index]))
        rows.append({
            "family": "ad-buy-form", "doc_id": f"doc-{index}", "source_id": source_id,
            "source_sha256": tables.sha256_file(path), "source_size_bytes": path.stat().st_size,
        })
    cohort = tmp_path / "cohort.jsonl"
    cohort.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    selected = sorted(rows, key=lambda row: row["source_sha256"])[:2]
    selection = tmp_path / "selected.jsonl"
    selection.write_text("".join(json.dumps({key: row[key] for key in
                         ("doc_id", "source_id", "source_sha256", "source_size_bytes")}) + "\n"
                         for row in selected), encoding="utf-8")
    monkeypatch.setattr(tables, "MAX_DOCUMENTS", 2)
    monkeypatch.setattr(tables, "COHORT_SHA256", tables.sha256_file(cohort))
    monkeypatch.setattr(tables, "SELECTION_SHA256", tables.sha256_file(selection))
    assert [row["doc_id"] for row in tables.verify_selection(selection, cohort, tmp_path)] == [
        row["doc_id"] for row in selected
    ]
    tables.source_path(tmp_path, selected[0]["source_id"]).write_bytes(b"changed")
    with pytest.raises(ContractError, match="source bytes"):
        tables.verify_selection(selection, cohort, tmp_path)


def test_docling_table_cells_keep_same_page_and_start_row_without_span_duplication() -> None:
    document = {
        "pages": {"1": {}, "2": {}},
        "tables": [{
            "prov": [{"page_no": 2}],
            "data": {"num_rows": 2, "num_cols": 3, "table_cells": [
                {"start_row_offset_idx": 0, "end_row_offset_idx": 1,
                 "start_col_offset_idx": 0, "end_col_offset_idx": 1, "text": "  Item  "},
                {"start_row_offset_idx": 1, "end_row_offset_idx": 2,
                 "start_col_offset_idx": 0, "end_col_offset_idx": 2, "text": "A\n  B"},
                {"start_row_offset_idx": 2, "end_row_offset_idx": 3,
                 "start_col_offset_idx": 0, "end_col_offset_idx": 1, "text": "invalid"},
            ]},
        }],
    }
    cells, rows, counts = tables.parsed_tables(document)
    assert cells == ["item", "a b"]
    assert rows == [["item"], ["a b"]]
    assert counts == {"tables": 1, "rows": 2, "nonempty_cells": 2,
                      "spanning_cells": 1, "invalid_cells": 1}
    document["tables"][0]["prov"] = [{"page_no": 3}]
    with pytest.raises(ContractError, match="provenance"):
        tables.parsed_tables(document)


def test_surface_presence_does_not_count_as_an_exact_cell_or_complete_row() -> None:
    gold_rows = {0: ["alpha", "10"], 1: ["beta", "20"]}
    parser_rows = [["alpha", "10", "extra"], ["beta 20"]]
    parser_cells = [cell for row in parser_rows for cell in row]
    score = tables.score_tables(gold_rows, parser_cells, parser_rows)
    assert score["gold_cells"] == 4
    assert score["gold_cell_surface_present_in_any_table_cell"] == 4
    assert score["gold_cell_exact_text_one_to_one"] == 2
    assert score["gold_within_row_cell_pairs"] == 2
    assert score["within_row_pairs_surface_colocated_unbounded"] == 1
    assert score["within_row_pairs_exact_cells_colocated_unbounded"] == 1
    assert score["complete_rows_exact_cells_one_to_one"] == 1
    assert score["complete_rows_exact_multiset_one_to_one"] == 0
    assert score["gold_cells_in_exact_linked_rows"] == 2


def test_repeated_gold_rows_cannot_reuse_one_parser_row_or_cells() -> None:
    score = tables.score_tables({0: ["A", "1"], 1: ["A", "1"]}, ["a", "1"], [["a", "1"]])
    assert score["gold_cell_surface_present_in_any_table_cell"] == 4
    assert score["gold_cell_exact_text_one_to_one"] == 2
    assert score["gold_within_row_cell_pairs"] == 2
    assert score["within_row_pairs_exact_cells_colocated_unbounded"] == 2
    assert score["complete_rows_surface_colocated_one_to_one"] == 1
    assert score["complete_rows_exact_cells_one_to_one"] == 1
    assert score["complete_rows_exact_multiset_one_to_one"] == 1


def test_gold_linked_rows_excludes_scalar_and_array_string_fields() -> None:
    gold = {
        "gold_schema": [
            {"field_id": "scalar", "type": "string"},
            {"field_id": "property", "type": "array[string]"},
            {"field_id": "channel", "type": "array[object]"},
            {"field_id": "amount", "type": "array[object]"},
        ],
        "gold_values": [
            {"field_id": "scalar", "value": "ignore"},
            {"field_id": "property", "value": ["ignore"]},
            {"field_id": "channel", "value": [{"row": 5, "value": " CNN "}]},
            {"field_id": "amount", "value": [{"row": 5, "value": "$10"}]},
        ],
    }
    assert tables.gold_linked_rows(gold) == {5: ["cnn", "$10"]}


def test_saved_scoring_keeps_failed_conversion_in_gold_denominator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = [{"doc_id": "one", "source_sha256": "a" * 64},
                {"doc_id": "two", "source_sha256": "b" * 64}]
    gold = tmp_path / "gold.jsonl"
    gold.write_text("synthetic\n", encoding="utf-8")
    monkeypatch.setattr(tables, "GOLD_SHA256", tables.sha256_file(gold))
    gold_record = lambda value: {
        "gold_schema": [{"field_id": "channel", "type": "array[object]"}],
        "gold_values": [{"field_id": "channel", "value": [{"row": 0, "value": value}]}],
    }
    monkeypatch.setattr(tables, "load_jsonl", lambda _path, kind: {
        "one": gold_record("ABC"), "two": gold_record("XYZ"),
    })
    for row, status in zip(selected, ("success", "exception"), strict=True):
        folder = tmp_path / "docs" / row["doc_id"]
        folder.mkdir(parents=True)
        (folder / "conversion.json").write_text(json.dumps({
            "source_sha256": row["source_sha256"], "status": status, "duration_ms": 25,
        }), encoding="utf-8")
    (tmp_path / "docs" / "one" / "document.json").write_text(json.dumps({
        "pages": {"1": {}},
        "tables": [{"prov": [{"page_no": 1}], "data": {"num_rows": 1, "num_cols": 1,
                    "table_cells": [{"start_row_offset_idx": 0, "end_row_offset_idx": 1,
                                     "start_col_offset_idx": 0, "end_col_offset_idx": 1,
                                     "text": "ABC"}]}}],
    }), encoding="utf-8")
    score = tables.score_saved(tmp_path, gold, selected)
    assert score["selected_documents"] == 2
    assert score["conversion_successes"] == 1
    assert score["conversion_failures_or_partial"] == 1
    assert score["missing_or_invalid_parser_outputs"] == 1
    assert score["metrics"]["gold_rows"] == 2
    assert score["metrics"]["complete_rows_exact_cells_one_to_one"] == 1
    assert score["duration_ms_sum"] == 50


def test_malformed_saved_parser_output_stays_in_denominator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = [{"doc_id": "bad", "source_sha256": "a" * 64}]
    gold = tmp_path / "gold.jsonl"
    gold.write_text("synthetic\n", encoding="utf-8")
    monkeypatch.setattr(tables, "GOLD_SHA256", tables.sha256_file(gold))
    monkeypatch.setattr(tables, "load_jsonl", lambda _path, kind: {
        "bad": {
            "gold_schema": [{"field_id": "channel", "type": "array[object]"}],
            "gold_values": [{"field_id": "channel", "value": [{"row": 0, "value": "ABC"}]}],
        },
    })
    folder = tmp_path / "docs" / "bad"
    folder.mkdir(parents=True)
    (folder / "conversion.json").write_text(json.dumps({
        "source_sha256": "a" * 64, "status": "success", "duration_ms": 1,
    }), encoding="utf-8")
    (folder / "document.json").write_text("{broken", encoding="utf-8")
    score = tables.score_saved(tmp_path, gold, selected)
    assert score["selected_documents"] == 1
    assert score["conversion_successes"] == 1
    assert score["missing_or_invalid_parser_outputs"] == 1
    assert score["metrics"]["gold_rows"] == 1
    assert score["metrics"]["complete_rows_exact_cells_one_to_one"] == 0


def test_saved_scoring_rejects_changed_raw_docling_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = [{"doc_id": "one", "source_sha256": "a" * 64}]
    gold = tmp_path / "gold.jsonl"
    gold.write_text("synthetic\n", encoding="utf-8")
    monkeypatch.setattr(tables, "GOLD_SHA256", tables.sha256_file(gold))
    monkeypatch.setattr(tables, "load_jsonl", lambda _path, kind: {"one": {}})
    folder = tmp_path / "docs" / "one"
    folder.mkdir(parents=True)
    document = folder / "document.json"
    document.write_text('{"tables": []}', encoding="utf-8")
    original_hash = tables.sha256_file(document)
    (folder / "conversion.json").write_text(json.dumps({
        "source_sha256": "a" * 64, "status": "success", "duration_ms": 1,
        "document_sha256": original_hash,
    }), encoding="utf-8")
    document.write_text('{"tables": [{"data": {}}]}', encoding="utf-8")

    with pytest.raises(tables.ContractError, match="differs from conversion receipt"):
        tables.score_saved(tmp_path, gold, selected)

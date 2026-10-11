"""The native-table comparator must preserve source and failure denominators."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_eval import pdfplumber_table_diagnostic as tables


def test_profiles_are_predeclared_independently() -> None:
    assert tables.PROFILES == {
        "lines": {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        "text": {"vertical_strategy": "text", "horizontal_strategy": "text"},
    }


def test_table_strings_keep_rows_and_skip_empty_cells() -> None:
    cells, rows, stats = tables.table_strings({"tables": [{
        "page": 2, "rows": [["  CNN ", None, "$10"], [" ", "Radio"]],
    }]})
    assert cells == ["cnn", "$10", "radio"]
    assert rows == [["cnn", "$10"], ["radio"]]
    assert stats == {"tables": 1, "rows": 2, "nonempty_cells": 3}


def test_scoring_keeps_no_table_scan_in_both_denominators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = [{"doc_id": "one", "source_sha256": "a" * 64},
                {"doc_id": "scan", "source_sha256": "b" * 64}]
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text("synthetic\n", encoding="utf-8")
    monkeypatch.setattr(tables, "GOLD_SHA256", tables.sha256_file(gold_path))

    def gold_record(value: str) -> dict:
        return {
            "gold_schema": [{"field_id": "channel", "type": "array[object]"}],
            "gold_values": [{"field_id": "channel", "value": [{"row": 0, "value": value}]}],
        }

    monkeypatch.setattr(tables, "load_jsonl", lambda _path, kind: {
        "one": gold_record("CNN"), "scan": gold_record("Radio"),
    })
    for profile in tables.PROFILES:
        for row in selected:
            folder = tmp_path / "docs" / row["doc_id"] / profile
            raw = {"page_count": 1, "native_chars": 0 if row["doc_id"] == "scan" else 50,
                   "tables": [] if row["doc_id"] == "scan" else [
                       {"page": 1, "rows": [["CNN"]]},
                   ]}
            raw_path = folder / "tables.json"
            tables.write_json(raw_path, raw)
            tables.write_json(folder / "conversion.json", {
                "doc_id": row["doc_id"], "source_sha256": row["source_sha256"],
                "profile": profile,
                "status": "no_native_text_no_tables" if row["doc_id"] == "scan" else "success",
                "duration_ms": 10, "tables_sha256": tables.sha256_file(raw_path),
            })
    score = tables.score_saved(tmp_path, gold_path, selected)
    for profile in tables.PROFILES:
        scored = score["profiles"][profile]
        assert scored["selected_documents"] == 2
        assert scored["documents_with_tables"] == 1
        assert scored["no_table_or_failed_documents"] == 1
        assert scored["metrics"]["gold_rows"] == 2
        assert scored["metrics"]["complete_rows_exact_cells_one_to_one"] == 1
        assert scored["duration_ms_sum"] == 20


def test_saved_scoring_rejects_mutated_raw_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = [{"doc_id": "one", "source_sha256": "a" * 64}]
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text("synthetic\n", encoding="utf-8")
    monkeypatch.setattr(tables, "GOLD_SHA256", tables.sha256_file(gold_path))
    monkeypatch.setattr(tables, "load_jsonl", lambda _path, kind: {"one": {}})
    for profile in tables.PROFILES:
        folder = tmp_path / "docs" / "one" / profile
        raw_path = folder / "tables.json"
        tables.write_json(raw_path, {"page_count": 1, "native_chars": 0, "tables": []})
        tables.write_json(folder / "conversion.json", {
            "doc_id": "one", "source_sha256": "a" * 64, "profile": profile,
            "status": "no_tables", "duration_ms": 1,
            "tables_sha256": tables.sha256_file(raw_path),
        })
    (tmp_path / "docs" / "one" / "lines" / "tables.json").write_text(
        json.dumps({"page_count": 1, "native_chars": 1, "tables": []}), encoding="utf-8",
    )
    with pytest.raises(tables.ContractError, match="differ from conversion receipt"):
        tables.score_saved(tmp_path, gold_path, selected)

from __future__ import annotations

from product_eval.mineru_table_diagnostic import _child_environment, table_strings


def test_mineru_html_table_rows_are_scored_once() -> None:
    middle = {
        "schema": "docvortex.middle",
        "pages": [{"page_idx": 0, "blocks": [{"type": "table", "content": "<table><tr><td>duplicate</td></tr></table>",
                                                "blocks": [{"type": "table_body", "content":
                                                            "<table><tr><th>Qty</th><th>Price</th></tr>"
                                                            "<tr><td> 2 </td><td> $5 </td></tr></table>"}]}]}],
    }
    cells, rows, stats = table_strings(middle)
    assert rows == [["qty", "price"], ["2", "$5"]]
    assert cells == ["qty", "price", "2", "$5"]
    assert stats == {"tables": 1, "invalid_tables": 0, "rows": 2, "nonempty_cells": 4}


def test_mineru_direct_table_body_and_repeated_tables_remain_distinct() -> None:
    table = {"type": "table_body", "content": "<table><tr><td>A</td></tr></table>"}
    middle = {"schema": "docvortex.middle", "pages": [{"blocks": [table, table]}]}
    cells, rows, stats = table_strings(middle)
    assert cells == ["a", "a"]
    assert rows == [["a"], ["a"]]
    assert stats["tables"] == 2


def test_child_environment_forces_local_cpu_models(tmp_path) -> None:
    env = _child_environment(tmp_path / "config.yaml", tmp_path / "home", tmp_path / "tmp")
    assert env["MINERU_MODEL_SOURCE"] == "local"
    assert env["MINERU_MODEL_SMALL_BACKEND"] == "onnx"
    assert env["MINERU_TABLE_DEVICE"] == "cpu"
    assert env["HF_HUB_OFFLINE"] == "1"

"""S1 native graph tests use source files only; no label or model input is read."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from idpo.product_auto.native_formats import parse_native_document
from product_eval import native_source_graph as graph

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "mixed_format_docling_v1"


@pytest.mark.parametrize("name", graph.FIXTURE_NAMES)
def test_locked_native_fixtures_have_stable_source_only_candidates(name: str) -> None:
    path = FIXTURES / name
    first = graph.parse_source_graph(path)
    second = graph.parse_source_graph(path)
    assert first == second
    assert len(first.nodes) == 9
    assert len(first.tables) == 1
    assert first.abstentions == ()
    table = first.tables[0]
    assert len(table.columns) == 3
    assert len(table.rows) == 2
    assert [row.source_row for row in table.rows] == [1, 2]
    nodes = {node.node_id: node for node in first.nodes}
    assert len(nodes) == 9
    for row in table.rows:
        assert [nodes[node_id].row for node_id in row.cell_node_ids] == [row.source_row] * 3
        assert [nodes[node_id].column for node_id in row.cell_node_ids] == [0, 1, 2]
    assert first.model_input() == second.model_input()
    assert len(first.model_input()) <= graph.MAX_MODEL_INPUT_BYTES


def test_rows_use_source_grid_even_when_values_repeat(tmp_path: Path) -> None:
    path = tmp_path / "repeat.html"
    path.write_text("<table><thead><tr><th>Item</th><th>Amount</th></tr></thead>"
                    "<tbody><tr><td>same</td><td>1</td></tr>"
                    "<tr><td>same</td><td>1</td></tr></tbody></table>", encoding="utf-8")
    result = graph.parse_source_graph(path)
    assert len(result.tables) == 1
    table = result.tables[0]
    nodes = {node.node_id: node for node in result.nodes}
    assert len(table.rows) == 2
    assert table.rows[0].cell_node_ids != table.rows[1].cell_node_ids
    assert [[nodes[node_id].text for node_id in row.cell_node_ids] for row in table.rows] == [
        ["same", "1"], ["same", "1"]]
    assert table.header_basis == "html_thead"


@pytest.mark.parametrize("labels", [("Amount", "Amount"), ("Net total", "Net-total")])
def test_duplicate_or_normalized_ambiguous_headers_abstain(tmp_path: Path,
                                                           labels: tuple[str, str]) -> None:
    path = tmp_path / "ambiguous.html"
    path.write_text(f"<table><tr><th>{labels[0]}</th><th>{labels[1]}</th></tr>"
                    "<tr><td>2</td><td>3</td></tr></table>", encoding="utf-8")
    result = graph.parse_source_graph(path)
    assert not result.tables
    assert not result.nodes
    assert result.abstentions == (graph.TableAbstention("table-1", "duplicate_header"),)


def test_unmeasured_header_script_and_format_abstain(tmp_path: Path) -> None:
    path = tmp_path / "script.html"
    path.write_text("<table><tr><th>नाम</th><th>Amount</th></tr>"
                    "<tr><td>A</td><td>1</td></tr></table>", encoding="utf-8")
    result = graph.parse_source_graph(path)
    assert not result.tables
    assert result.abstentions == (graph.TableAbstention("table-1", "unsupported_header_script"),)
    with pytest.raises(graph.SourceGraphError, match="^unsupported_format$"):
        graph.parse_source_graph(tmp_path / "unsupported.txt")


def test_parser_failure_exposes_only_a_fixed_reason(monkeypatch: pytest.MonkeyPatch,
                                                    tmp_path: Path) -> None:
    path = tmp_path / "source.html"
    path.write_text("private source text", encoding="utf-8")

    def fail(*_args):
        raise RuntimeError("private source text")

    monkeypatch.setattr(graph, "parse_native_document", fail)
    with pytest.raises(graph.SourceGraphError, match="^parser_failed$") as error:
        graph.parse_source_graph(path)
    assert "private source text" not in str(error.value)


def test_wrong_native_cell_pointer_abstains_even_if_value_is_identical(tmp_path: Path) -> None:
    path = tmp_path / "same.html"
    path.write_text("<table><tr><th>Item</th><th>Amount</th></tr>"
                    "<tr><td>same</td><td>same</td></tr></table>", encoding="utf-8")
    source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    _, parsed = parse_native_document(path, source_sha256)
    table = parsed.tables[0]
    first_data_cell, second_data_cell = table.cells[2:4]
    forged_anchor = replace(first_data_cell.anchors[0],
                            native_locator=second_data_cell.anchors[0].native_locator)
    forged_cell = replace(first_data_cell, anchors=(forged_anchor,))
    forged_table = replace(table, cells=(*table.cells[:2], forged_cell, *table.cells[3:]))
    forged = replace(parsed, tables=(forged_table,))
    result = graph.build_source_graph(forged, path)
    assert not result.tables
    assert not result.nodes
    assert result.abstentions == (graph.TableAbstention("table-1", "native_locator_mismatch"),)


def test_serialization_rejects_invented_candidate_pointer_and_oversize(tmp_path: Path) -> None:
    path = tmp_path / "source.html"
    path.write_text("<table><tr><th>Item</th><th>Amount</th></tr>"
                    "<tr><td>A</td><td>1</td></tr></table>", encoding="utf-8")
    original = graph.parse_source_graph(path)
    table = original.tables[0]
    forged_row = replace(table.rows[0], cell_node_ids=("n_invented", *table.rows[0].cell_node_ids[1:]))
    forged = replace(original, tables=(replace(table, rows=(forged_row,)),))
    with pytest.raises(graph.SourceGraphError, match="^invalid_candidate_pointer$"):
        forged.model_input()
    too_long = replace(original.nodes[0], text="x" * graph.MAX_MODEL_INPUT_BYTES)
    with pytest.raises(graph.SourceGraphError, match="^model_input_limit$"):
        replace(original, nodes=(too_long, *original.nodes[1:])).model_input()


def test_receipt_contains_hashes_and_counts_without_source_text() -> None:
    receipt = graph.locked_fixture_receipt(FIXTURES)
    serialized = json.dumps(receipt, sort_keys=True)
    assert receipt["model_calls"] == 0
    assert receipt["gold_access"] is False
    assert receipt["product_extraction_calls"] == 0
    assert len(receipt["records"]) == 5
    assert all(record["status"] == "candidate" for record in receipt["records"])
    assert "Widget" not in serialized
    assert "SYN-1001" not in serialized

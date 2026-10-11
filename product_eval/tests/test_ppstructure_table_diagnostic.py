"""Contract checks for the isolated PP-StructureV3 table comparison."""

from __future__ import annotations

from pathlib import Path

import pytest

from product_eval import ppstructure_table_diagnostic as tables
from product_eval.contracts import ContractError


def _config(model_dir: Path) -> dict:
    def module(name: str) -> dict:
        return {"module_name": name, "model_name": name, "model_dir": str(model_dir)}
    return {
        "pipeline_name": "PP-StructureV3", **tables.ROOT_FLAGS,
        "SubModules": {"LayoutDetection": module("layout"), "RegionDetection": module("region"),
                       "ChartRecognition": {"module_name": "chart", "model_dir": None}},
        "SubPipelines": {
            "GeneralOCR": {"use_doc_preprocessor": False,
                           "SubModules": {"TextDetection": module("text_det")}},
            "TableRecognition": {"use_doc_preprocessor": False, "use_layout_detection": False,
                                 "SubModules": {"TableClassification": module("table_cls")}},
            "FormulaRecognition": {"SubModules": {"Formula": {"module_name": "formula", "model_dir": None}}},
        },
    }


def test_model_lock_rejects_implicit_download_and_mutated_weight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yaml

    monkeypatch.setattr(tables, "package_versions", lambda: {"paddleocr": "synthetic"})
    model = tmp_path / "model"
    model.mkdir()
    weight = model / "inference.pdiparams"
    weight.write_bytes(b"synthetic weight")
    config = tmp_path / "pipeline.yaml"
    config.write_text(yaml.safe_dump(_config(model)), encoding="utf-8")
    lock = tmp_path / "lock.json"
    assert tables.make_model_lock(config, lock)["model_files"] == 1
    with pytest.raises(ContractError, match="already exists"):
        tables.make_model_lock(config, lock)
    monkeypatch.setattr(tables, "package_versions", lambda: {"paddleocr": "changed"})
    with pytest.raises(ContractError, match="parser packages"):
        tables.verify_model_lock(config, lock)
    monkeypatch.setattr(tables, "package_versions", lambda: {"paddleocr": "synthetic"})
    weight.write_bytes(b"changed")
    with pytest.raises(ContractError, match="differs from lock"):
        tables.verify_model_lock(config, lock)
    config.write_text(yaml.safe_dump(_config(model) | {"use_table_recognition": False}), encoding="utf-8")
    with pytest.raises(ContractError, match="fixed table-only profile"):
        tables.verify_model_lock(config, lock)


def test_model_lock_requires_every_active_model_dir(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config["SubPipelines"]["TableRecognition"]["SubModules"]["TableClassification"]["model_dir"] = None
    with pytest.raises(ContractError, match="no local model_dir"):
        tables.active_model_dirs(config)


def test_table_html_counts_real_cells_and_keeps_spans_at_start_row() -> None:
    page = {"table_res_list": [{"pred_html": "<table><tbody><tr><th colspan='2'>Channel</th><th>Cost</th></tr>"
            "<tr><td><b>CNN</b></td><td>National</td><td>$10</td></tr></tbody></table>",
            "cell_box_list": [[0, 0, 10, 10], [10, 0, 20, 10]]}]}
    cells, rows, stats = tables.table_strings([{"res": page}])
    assert rows == [["channel", "cost"], ["cnn", "national", "$10"]]
    assert cells == ["channel", "cost", "cnn", "national", "$10"]
    assert stats == {"tables": 1, "rows": 2, "nonempty_cells": 5,
                     "cell_boxes": 2, "invalid_cell_boxes": 0}


@pytest.mark.parametrize("page", [
    {},
    {"table_res_list": [{"pred_html": "CNN", "cell_box_list": []}]},
    {"table_res_list": [{"pred_html": "<table><tr><td>A</td></tr></table>"}]},
])
def test_malformed_parser_output_is_explicit(page: dict) -> None:
    with pytest.raises(ContractError):
        tables.table_strings([page])


def test_failed_document_keeps_gold_row_in_denominator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    selected = [{"doc_id": "ok", "source_sha256": "a" * 64},
                {"doc_id": "timeout", "source_sha256": "b" * 64}]
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text("synthetic\n", encoding="utf-8")
    monkeypatch.setattr(tables, "GOLD_SHA256", tables.sha256_file(gold_path))

    def record(value: str) -> dict:
        return {"gold_schema": [{"field_id": "item", "type": "array[object]"}],
                "gold_values": [{"field_id": "item", "value": [{"row": 0, "value": value}]}]}

    monkeypatch.setattr(tables, "load_jsonl", lambda _path, kind: {
        "ok": record("CNN"), "timeout": record("Radio"),
    })
    for row in selected:
        folder = tmp_path / "docs" / row["doc_id"]
        folder.mkdir(parents=True)
        pages = []
        if row["doc_id"] == "ok":
            raw = folder / "page-000.json"
            image = folder / "page-000.png"
            image.write_bytes(b"synthetic image")
            tables.write_json(raw, {"table_res_list": [{"pred_html": "<table><tr><td>CNN</td></tr></table>",
                                                        "cell_box_list": [[0, 0, 10, 10]]}]})
            pages = [{"page_index": 0, "file": raw.name, "sha256": tables.sha256_file(raw),
                      "image_file": image.name, "image_sha256": tables.sha256_file(image)}]
        tables.write_json(folder / "conversion.json", {
            "doc_id": row["doc_id"], "source_sha256": row["source_sha256"],
            "status": "success" if pages else "timeout", "duration_ms": 50,
            "page_count": 1 if pages else None, "pages": pages,
        })
    score = tables.score_saved(tmp_path, gold_path, selected)
    assert score["selected_documents"] == 2
    assert score["conversion_successes"] == 1
    assert score["conversion_failures_or_partial"] == 1
    assert score["metrics"]["gold_rows"] == 2
    assert score["metrics"]["complete_rows_exact_cells_one_to_one"] == 1
    (tmp_path / "docs" / "ok" / "page-000.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ContractError, match="differs from conversion receipt"):
        tables.score_saved(tmp_path, gold_path, selected)

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from product_eval.contracts import ContractError
from product_eval.tablemagic_v2_pilot import (
    _git_blob_sha1,
    _resource_error,
    verify_models,
)
from product_eval.tablemagic_v2_table_diagnostic import (
    _manual_audit_candidates,
    table_strings,
)
from product_eval.tablemagic_v2_worker import _model


def _page(markup: str = "<table><tr><td>Alpha</td><td>10</td></tr></table>") -> dict:
    return {"res": {
        "page_index": 0,
        "model_settings": {"use_layout_detection": True, "use_ocr_model": True,
                           "use_doc_preprocessor": False},
        "layout_det_res": {"boxes": [
            {"label": "table", "coordinate": [0, 0, 100, 30]}]},
        "overall_ocr_res": {"rec_texts": ["UNRELATED"],
                            "rec_boxes": [[0, 50, 50, 60]]},
        "table_res_list": [{
            "pred_html": markup,
            "cell_box_list": [[0, 0, 50, 30], [50, 0, 100, 30]],
            "table_ocr_pred": {"rec_texts": ["Alpha", "10"],
                               "rec_boxes": [[2, 2, 48, 20], [52, 2, 98, 20]]},
        }],
    }}


GEOMETRY = {"page_index": 0, "image_width": 100, "image_height": 80,
            "table_region_ids": [1]}


def test_scores_only_html_and_separately_counts_real_box_text_matches():
    cells, rows, stats = table_strings([_page()], [GEOMETRY])
    assert cells == ["alpha", "10"]
    assert rows == [["alpha", "10"]]
    assert stats["valid_html_tables"] == 1
    assert stats["valid_cell_boxes"] == 2
    assert stats["valid_table_regions"] == 1
    assert stats["html_cells_with_unique_exact_ocr_box"] == 2


def test_ocr_text_cannot_become_a_table_row():
    page = _page("OCR text with no table tag")
    cells, rows, stats = table_strings([page], [GEOMETRY])
    assert cells == rows == []
    assert stats["invalid_html_tables"] == 1


def test_full_profile_and_geometry_are_required():
    page = _page()
    page["res"]["model_settings"]["use_layout_detection"] = False
    with pytest.raises(ContractError, match="frozen full table profile"):
        table_strings([page], [GEOMETRY])
    with pytest.raises(ContractError, match="source geometry"):
        table_strings([_page()], [{**GEOMETRY, "table_region_ids": []}])


def test_bad_cell_box_is_counted_without_invented_replacement():
    page = _page()
    page["res"]["table_res_list"][0]["cell_box_list"][1] = [90, 0, 102, 30]
    _, _, stats = table_strings([page], [GEOMETRY])
    assert stats["valid_cell_boxes"] == 1
    assert stats["invalid_cell_boxes"] == 1
    assert stats["tables_with_equal_cell_counts"] == 0
    assert stats["html_cells_with_unique_exact_ocr_box"] == 1


def test_manual_overlay_sample_uses_primary_exact_match_and_gold_row_order():
    markup = ("<table><tr><td>Alpha</td><td>10</td></tr>"
              "<tr><td>Beta</td><td>20</td></tr></table>")
    page = _page(markup)
    _, rows, _ = table_strings([page], [GEOMETRY])
    matched = _manual_audit_candidates("doc-a", {9: ["beta", "20"],
                                                  3: ["alpha", "10"]}, [page], rows)
    assert [item["gold_row_id"] for item in matched] == [3, 9]
    assert [item["html_nonempty_row_index"] for item in matched] == [0, 1]
    assert all(item["page_index"] == item["table_index"] == 0 for item in matched)


def test_all_active_model_bytes_must_match_manifest(tmp_path, monkeypatch):
    from product_eval import tablemagic_v2_pilot as pilot

    manifest = copy.deepcopy(json.loads(pilot.MODEL_MANIFEST.read_text(encoding="utf-8")))
    for model in manifest["models"]:
        if model["name"] == "UVDoc":
            continue
        folder = tmp_path / model["name"]
        folder.mkdir()
        content = model["name"].encode("ascii")
        path = folder / "inference.pdiparams"
        path.write_bytes(content)
        model["files"] = [{"path": path.name, "size_bytes": len(content),
                           "sha256": hashlib.sha256(content).hexdigest()}]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(pilot, "MODEL_MANIFEST_SHA256", pilot._manifest_digest(manifest))
    assert verify_models(tmp_path, manifest_path)["verified_model_files"] == 9
    (tmp_path / "SLANeXt_wired" / "inference.pdiparams").write_bytes(b"same-size-wrong!")
    with pytest.raises(ContractError, match="model size differs|model digest differs"):
        verify_models(tmp_path, manifest_path)


def test_git_blob_digest_and_resource_guards(tmp_path):
    path = tmp_path / "small.txt"
    path.write_bytes(b"abc")
    assert _git_blob_sha1(path) == hashlib.sha1(b"blob 3\0abc").hexdigest()
    sample = {"process_tree_rss_bytes": 1, "host_available_bytes": 4 * 1024**3,
              "c_free_bytes": 5 * 1024**3, "e_free_bytes": 3 * 1024**3}
    assert _resource_error(sample) is None
    assert _resource_error({**sample, "host_available_bytes": 2 * 1024**3}) == "host_ram_floor"


def test_worker_only_accepts_expected_model_node(tmp_path):
    config = {"SubModules": {"LayoutDetection": {"model_name": "PP-DocLayout-L",
                                                  "model_dir": None}}}
    _model(config, ("SubModules", "LayoutDetection"), tmp_path, "PP-DocLayout-L")
    assert config["SubModules"]["LayoutDetection"]["model_dir"] == str(tmp_path / "PP-DocLayout-L")
    with pytest.raises(RuntimeError, match="default changed"):
        _model(config, ("SubModules", "LayoutDetection"), tmp_path, "wrong")

from __future__ import annotations

import pytest

from product_eval.contracts import ContractError
from product_eval.paddleocr_vl_table_diagnostic import table_regions, table_strings


def test_table_region_html_only_preserves_rows_and_region_count() -> None:
    page = {"res": {"page_index": 0, "model_settings": {"use_layout_detection": True},
                    "parsing_res_list": [
                        {"block_label": "text", "block_content": "<table><tr><td>ignored</td></tr></table>"},
                        {"block_label": "table", "block_bbox": [1, 2, 20, 30],
                         "block_content": "<table><tr><th>Item</th><th>Cost</th></tr>"
                                          "<tr><td rowspan='2'>Tea</td><td>5.00</td></tr>"
                                          "<tr><td>4.00</td></tr></table>"},
                    ]}}
    cells, rows, stats = table_strings([page])
    assert rows == [["item", "cost"], ["tea", "5.00"], ["4.00"]]
    assert cells == ["item", "cost", "tea", "5.00", "4.00"]
    assert stats == {"table_blocks": 1, "valid_tables": 1, "invalid_tables": 0,
                     "valid_region_boxes": 1, "invalid_region_boxes": 0,
                     "merged_continuations": 0, "rows": 3, "nonempty_cells": 5}


def test_markdown_table_and_bad_box_are_not_promoted_to_cells() -> None:
    page = {"page_index": 0, "model_settings": {"use_layout_detection": True},
            "parsing_res_list": [{"block_label": "table", "block_bbox": [5, 2, 3, 9],
                                  "block_content": "| Item | Price |\n| Tea | 5.00 |"}]}
    cells, rows, stats = table_strings([page])
    assert cells == [] and rows == []
    assert stats["invalid_tables"] == 1
    assert stats["invalid_region_boxes"] == 1


def test_layout_disabled_or_page_missing_is_invalid() -> None:
    page = {"page_index": 0, "model_settings": {"use_layout_detection": False},
            "parsing_res_list": []}
    with pytest.raises(ContractError, match="full layout"):
        table_strings([page])
    page["model_settings"]["use_layout_detection"] = True
    with pytest.raises(ContractError, match="page order"):
        table_strings([page, page])


def test_empty_linked_continuation_is_recorded_without_double_counting() -> None:
    common = {"model_settings": {"use_layout_detection": True}}
    first = {**common, "page_index": 0, "parsing_res_list": [
        {"block_label": "table", "block_bbox": [1, 2, 20, 30],
         "global_block_id": 5, "global_group_id": 5,
         "block_content": "<table><tr><td>merged</td></tr></table>"}]}
    second = {**common, "page_index": 1, "parsing_res_list": [
        {"block_label": "table", "block_bbox": [1, 2, 20, 30],
         "global_block_id": 8, "global_group_id": 5, "block_content": ""}]}
    cells, rows, stats = table_strings([first, second])
    assert cells == ["merged"] and rows == [["merged"]]
    assert stats["table_blocks"] == 2
    assert stats["valid_tables"] == 1
    assert stats["merged_continuations"] == 1
    assert stats["invalid_tables"] == 0
    regions = table_regions([first, second])
    assert len(regions) == 2
    assert regions[1]["block_bbox"] == [1.0, 2.0, 20.0, 30.0]
    assert regions[1]["global_group_id"] == 5

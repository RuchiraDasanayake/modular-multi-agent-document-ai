"""Synthetic DETR class and coordinate contract tests."""

from __future__ import annotations

import math

import pytest

from product_eval.tatr_output_adapter import adapt_detr_outputs


def test_detection_queries_preserve_no_object_and_source_image_scale() -> None:
    adapted = adapt_detr_outputs(
        [[5.0, 0.0, -5.0], [-5.0, -5.0, 5.0]],
        [[0.5, 0.5, 0.4, 0.2], [0.1, 0.1, 0.1, 0.1]],
        (1000, 500), model_kind="detection",
    )
    assert len(adapted) == 2
    assert adapted[0]["label"] == "table"
    assert adapted[0]["bbox"] == pytest.approx((300, 200, 700, 300))
    assert adapted[0]["above_frozen_threshold"] is True
    assert adapted[1]["label"] == "no object"
    assert adapted[1]["query_index"] == 1
    assert adapted[1]["above_frozen_threshold"] is False
    assert adapted[1]["score"] > 0.5


def test_structure_map_and_outside_box_are_retained() -> None:
    adapted = adapt_detr_outputs(
        [[0, 0, 0, 0, 0, 10, -10]],
        [[0.95, 0.5, 0.2, 0.4]],
        (400, 200), model_kind="structure",
    )
    assert adapted[0]["label"] == "table spanning cell"
    assert adapted[0]["inside_image"] is False
    assert adapted[0]["bbox"] == pytest.approx((340, 60, 420, 140))


@pytest.mark.parametrize("logits,boxes,size", [
    ([[1, 2]], [[0.5, 0.5, 0.2, 0.2]], (100, 100)),
    ([[1, 2, 3]], [[0.5, 0.5, 0, 0.2]], (100, 100)),
    ([[1, 2, 3]], [[math.nan, 0.5, 0.2, 0.2]], (100, 100)),
    ([[1, 2, 3]], [], (100, 100)),
    ([[1, 2, 3]], [[0.5, 0.5, 0.2, 0.2]], (0, 100)),
])
def test_invalid_raw_outputs_fail_closed(
    logits: list[list[float]], boxes: list[list[float]], size: tuple[int, int],
) -> None:
    with pytest.raises(ValueError):
        adapt_detr_outputs(logits, boxes, size, model_kind="detection")

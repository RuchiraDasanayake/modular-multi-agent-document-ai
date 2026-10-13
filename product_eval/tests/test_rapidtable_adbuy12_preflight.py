"""Source-free checks for the pinned RapidTable contract."""

from types import SimpleNamespace
from unittest import TestCase

import numpy as np

from product_eval.rapidtable_adbuy12_preflight import (
    validate_ocr_tuple,
    validate_result,
)


class RapidTablePreflightTests(TestCase):
    def test_ocr_tuple_requires_three_aligned_arrays(self) -> None:
        box = np.array([[[1, 1], [9, 1], [9, 9], [1, 9]]], dtype=np.float32)
        validate_ocr_tuple((box, ("A",), (0.99,)))
        with self.assertRaisesRegex(ValueError, "3-tuple"):
            validate_ocr_tuple((box, ("A",)))
        with self.assertRaisesRegex(ValueError, "mismatched"):
            validate_ocr_tuple((box, ("A", "B"), (0.99,)))

    def test_ocr_tuple_rejects_nonfinite_geometry(self) -> None:
        box = np.array([[[1, 1], [9, 1], [float("nan"), 9], [1, 9]]], dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            validate_ocr_tuple((box, ("A",), (0.99,)))

    def test_table_contract_matches_physical_cells_and_logic(self) -> None:
        result = SimpleNamespace(
            imgs=[np.zeros((20, 20, 3), dtype=np.uint8)],
            pred_htmls=["<table><tr><td>A</td><td>B</td></tr></table>"],
            cell_bboxes=[
                np.array(
                    [[1, 1, 9, 1, 9, 9, 1, 9], [10, 1, 19, 1, 19, 9, 10, 9]],
                    dtype=np.float32,
                )
            ],
            logic_points=[np.array([[0, 0, 0, 0], [0, 0, 1, 1]], dtype=np.int64)],
            elapse=0.01,
        )
        stats = validate_result(result, 20, 20, ("A", "B"))
        self.assertEqual(stats["physical_html_cells"], 2)
        self.assertEqual(stats["logic_points"], 2)

    def test_source_geometry_overrun_fails_closed(self) -> None:
        result = SimpleNamespace(
            imgs=[np.zeros((20, 20, 3), dtype=np.uint8)],
            pred_htmls=["<table><tr><td>A</td></tr></table>"],
            cell_bboxes=[np.array([[1, 1, 9, 1, 9, 24, 1, 24]], dtype=np.float32)],
            logic_points=[np.array([[0, 0, 0, 0]], dtype=np.int64)],
            elapse=0.01,
        )
        with self.assertRaisesRegex(ValueError, "outside input raster"):
            validate_result(result, 20, 20, ("A",))

    def test_mismatch_between_html_and_box_count_fails_closed(self) -> None:
        result = SimpleNamespace(
            imgs=[np.zeros((20, 20, 3), dtype=np.uint8)],
            pred_htmls=["<table><tr><td>A</td><td>B</td></tr></table>"],
            cell_bboxes=[np.array([[1, 1, 9, 1, 9, 9, 1, 9]], dtype=np.float32)],
            logic_points=[np.array([[0, 0, 0, 0]], dtype=np.int64)],
            elapse=0.01,
        )
        with self.assertRaisesRegex(ValueError, "physical HTML cell count"):
            validate_result(result, 20, 20, ("A", "B"))

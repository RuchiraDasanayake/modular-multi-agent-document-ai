"""No selected PDFs or model calls: pinned TATR cell compatibility fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from product_eval.tatr_cell_compat import (
    STRUCTURE_THRESHOLDS,
    cells_from_synthetic_objects,
    load_official_cell_functions,
    prepare_word_tokens,
)
from product_eval.tatr_native_geometry import WordToken
from product_eval.tatr_rect import Rect


def _object(label: str, bbox: tuple[int, int, int, int], score: float = 0.9) -> dict:
    return {"label": label, "bbox": bbox, "score": score}


def _native(text: str, bbox: tuple[int, int, int, int], index: int) -> WordToken:
    return WordToken(text, bbox, bbox, index * 10, index * 10 + len(text))


def _grid_objects(*, span: bool = False) -> list[dict]:
    objects = [
        _object("table", (0, 0, 100, 40)),
        _object("table row", (0, 0, 100, 20)),
        _object("table row", (0, 20, 100, 40)),
        _object("table column", (0, 0, 50, 40)),
        _object("table column", (50, 0, 100, 40)),
        _object("table column header", (0, 0, 100, 20)),
    ]
    if span:
        objects.append(_object("table spanning cell", (0, 0, 100, 20)))
    return objects


@pytest.fixture(scope="module")
def official():
    root = Path(os.environ.get("TATR_ASSET_STAGE", r"I:\DocAI-Benchmarks\tatr-adbuy12-runtime-v1-stage"))
    if not root.exists():
        pytest.skip("pinned TATR asset stage absent; no substitute source is accepted")
    return load_official_cell_functions(root)


def test_rect_intersection_and_empty_union_semantics() -> None:
    assert list(Rect().include_rect((1, 2, 5, 6))) == [1, 2, 5, 6]
    assert Rect((1, 2, 5, 6)).intersect((3, 4, 7, 8)).get_area() == 4
    assert Rect((1, 2, 5, 6)).intersect((5, 2, 7, 8)).get_area() == 0
    assert list(Rect((1, 2, 5, 6)).include_rect((3, 4, 7, 8))) == [1, 2, 7, 8]


def test_native_and_scan_tokens_obey_one_word_order_and_provenance() -> None:
    native = _native("North", (1, 2, 21, 12), 0)
    scan = {
        "text": "South", "bbox": (52, 2, 80, 12), "reading_order": 0,
        "source": "ocr_word", "ocr_engine": "synthetic-fixture",
        "ocr_revision": "v1", "ocr_confidence": 0.92,
    }
    native_words = prepare_word_tokens([native], (100, 40))
    scan_words = prepare_word_tokens([scan], (100, 40))
    assert native_words[0]["pdf_bbox"] == native.pdf_bbox
    assert scan_words[0]["source"] == "ocr_word"
    assert native_words[0]["span_num"] == scan_words[0]["span_num"] == 0
    with pytest.raises(ValueError, match="mixed native and OCR"):
        prepare_word_tokens([native, {**scan, "reading_order": 1}], (100, 40))


@pytest.mark.parametrize("mutant", [
    {"text": "two words", "bbox": (1, 1, 20, 10), "reading_order": 0, "source": "ocr_word",
     "ocr_engine": "fixture", "ocr_revision": "v1", "ocr_confidence": 0.9},
    {"text": "One", "bbox": (1, 1, 20, 10), "reading_order": 1, "source": "ocr_word",
     "ocr_engine": "fixture", "ocr_revision": "v1", "ocr_confidence": 0.9},
    {"text": "One", "bbox": (1, 1, 20, 10), "reading_order": 0, "source": "ocr_word",
     "ocr_engine": "fixture", "ocr_revision": "v1"},
    {"text": "One", "bbox": (1, 1, 200, 10), "reading_order": 0, "source": "ocr_word",
     "ocr_engine": "fixture", "ocr_revision": "v1", "ocr_confidence": 0.9},
])
def test_bad_scan_word_fails_closed(mutant: dict) -> None:
    with pytest.raises(ValueError):
        prepare_word_tokens([mutant], (100, 40))


def test_duplicate_native_word_is_not_silently_deduplicated() -> None:
    token = _native("A", (1, 2, 10, 12), 0)
    with pytest.raises(ValueError, match="duplicate"):
        prepare_word_tokens([token, token], (100, 40))


def test_official_simple_grid_preserves_empty_cell_and_unique_word_assignment(official) -> None:
    tokens = [
        _native("Name", (5, 4, 30, 14), 0),
        _native("Value", (55, 4, 85, 14), 1),
        _native("Acme", (5, 24, 28, 34), 2),
    ]
    result = cells_from_synthetic_objects(official, _grid_objects(), tokens, (100, 40))
    cells = {(cell["row_nums"][0], cell["column_nums"][0]): cell for cell in result.cells}
    assert len(cells) == 4
    assert cells[(0, 0)]["cell text"] == "Name"
    assert cells[(0, 1)]["cell text"] == "Value"
    assert cells[(1, 0)]["cell text"] == "Acme"
    assert cells[(1, 1)]["cell text"] == ""
    assert cells[(1, 1)]["spans"] == []
    assert cells[(0, 0)]["column header"] is True
    assert cells[(1, 0)]["column header"] is False
    assert result.unassigned_token_ids == ()


def test_official_spanning_header_occupies_two_columns_and_starts_at_row_zero(official) -> None:
    tokens = [
        _native("Total", (38, 4, 62, 14), 0),
        _native("A", (5, 24, 15, 34), 1),
        _native("B", (55, 24, 65, 34), 2),
    ]
    result = cells_from_synthetic_objects(official, _grid_objects(span=True), tokens, (100, 40))
    assert len(result.cells) == 3
    header = next(cell for cell in result.cells if cell["row_nums"] == [0])
    assert set(header["column_nums"]) == {0, 1}
    assert header["column header"] is True
    assert header["cell text"] == "Total"
    assert {cell["cell text"] for cell in result.cells} == {"Total", "A", "B"}


def test_official_scan_words_remain_distinct_in_adjacent_cells(official) -> None:
    tokens = [
        {
            "text": text, "bbox": box, "reading_order": index,
            "source": "ocr_word", "ocr_engine": "synthetic-fixture",
            "ocr_revision": "v1", "ocr_confidence": 0.8,
        }
        for index, (text, box) in enumerate([
            ("Left", (5, 4, 30, 14)), ("Right", (55, 4, 90, 14)),
            ("5", (5, 24, 15, 34)), ("6", (55, 24, 65, 34)),
        ])
    ]
    result = cells_from_synthetic_objects(official, _grid_objects(), tokens, (100, 40))
    assert [cell["cell text"] for cell in sorted(
        result.cells, key=lambda cell: (cell["row_nums"][0], cell["column_nums"][0])
    )] == ["Left", "Right", "5", "6"]
    assert result.unassigned_token_ids == ()


def test_out_of_image_active_object_rejected_before_official_code(official) -> None:
    objects = _grid_objects() + [_object("table row", (-1, 0, 100, 20))]
    with pytest.raises(ValueError, match="outside"):
        cells_from_synthetic_objects(official, objects, [], (100, 40))


def test_frozen_threshold_profile_differs_from_upstream_row_handling(official) -> None:
    objects = _grid_objects()
    objects[1]["score"] = 0.49
    tokens = [_native("Heading", (5, 4, 35, 14), 0), _native("Data", (5, 24, 30, 34), 1)]
    words = prepare_word_tokens(tokens, (100, 40))
    # Pinned upstream passes a row threshold to refine_rows but does not apply it.
    upstream = official.objects_to_structures(objects, words, STRUCTURE_THRESHOLDS)
    assert len(upstream[0]["rows"]) == 2
    # The locked 0.5 protocol profile filters that low-score row first.
    frozen = cells_from_synthetic_objects(official, _grid_objects()[:1] + [
        _object("table row", (0, 0, 100, 20), 0.49),
        *_grid_objects()[2:],
    ], tokens, (100, 40))
    assert {tuple(cell["row_nums"]) for cell in frozen.cells} == {(0,)}

"""Contract checks for source-linked parser adapters."""

import pytest

from idpo.product_auto.parsed_document import (
    Box,
    ParsedDocument,
    SourceAnchor,
    SourceUnit,
    Table,
    TableCell,
)

SOURCE_HASH = "a" * 64


def test_native_cell_location_survives_without_invented_box() -> None:
    document = ParsedDocument(
        source_sha256=SOURCE_HASH,
        source_format="xlsx",
        parser_id="docling-slim",
        parser_version="2.138.0",
        units=(SourceUnit("sheet-1", "sheet", 0, "Widget A 2 12.00", label="Order Lines"),),
        tables=(Table("table-1", (
            TableCell(0, 0, "Widget A", anchors=(SourceAnchor("sheet-1", native_locator="'Order Lines'!A1"),)),
            TableCell(0, 1, "2", anchors=(SourceAnchor("sheet-1", native_locator="'Order Lines'!B1"),)),
        )),),
    )

    payload = document.to_dict()
    assert payload["contract_version"] == 2
    assert payload["tables"][0]["cells"][0]["anchors"][0]["native_locator"] == "'Order Lines'!A1"
    assert payload["tables"][0]["cells"][0]["anchors"][0]["raw_box"] is None
    assert payload["tables"][0]["cells"][0]["anchors"][0]["display_box"] is None


def test_source_quote_is_checked_against_the_referenced_unit() -> None:
    unit = SourceUnit("page-1", "pdf_page", 0, "Total: 12.00", width=612, height=792)
    good_anchor = SourceAnchor("page-1", text_span=(7, 12), quote="12.00")
    document = ParsedDocument(SOURCE_HASH, "pdf", "native", "1", (unit,), (Table("t", (TableCell(0, 0, "12.00", anchors=(good_anchor,)),)),))
    assert document.to_dict()["tables"][0]["cells"][0]["anchors"][0]["quote"] == "12.00"

    bad_anchor = SourceAnchor("page-1", text_span=(7, 12), quote="21.00")
    with pytest.raises(ValueError, match="quote does not equal"):
        ParsedDocument(SOURCE_HASH, "pdf", "native", "1", (unit,), (Table("t", (TableCell(0, 0, "21.00", anchors=(bad_anchor,)),)),))


def test_missing_geometry_is_allowed_but_false_geometry_is_rejected() -> None:
    with pytest.raises(ValueError, match="normalized box"):
        Box(0.1, 0.1, 1.1, 0.2, "normalized_top_left")
    with pytest.raises(ValueError, match="display box"):
        SourceAnchor("page-1", raw_box=Box(1, 1, 2, 2, "pixels_top_left"), display_box=Box(1, 1, 2, 2, "pixels_top_left"))
    with pytest.raises(ValueError, match="missing source unit"):
        ParsedDocument(SOURCE_HASH, "pdf", "native", "1", (SourceUnit("page-1", "pdf_page", 0, ""),), (Table("t", (TableCell(0, 0, "x", anchors=(SourceAnchor("page-2", native_locator="word:1"),)),)),))


def test_merged_grid_cells_cannot_overlap() -> None:
    with pytest.raises(ValueError, match="overlap"):
        Table("t", (TableCell(0, 0, "merged", column_span=2), TableCell(0, 1, "duplicate")))
    with pytest.raises(ValueError, match="contract limit"):
        Table("t", (TableCell(0, 0, "oversized", row_span=1_000_001),))

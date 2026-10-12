"""Parser-neutral, source-linked document structure for product adapters.

This contract is deliberately independent of any OCR or layout package. It is
not wired into ``process_auto`` yet; adapters must preserve unavailable source
locations as unavailable rather than manufacturing page geometry.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Literal

UnitKind = Literal["pdf_page", "image", "sheet", "slide", "html", "mime_part", "text"]
BoxSpace = Literal["pdf_points_bottom_left", "points_top_left", "pixels_top_left", "normalized_top_left"]
_BOX_SPACES = {"pdf_points_bottom_left", "points_top_left", "pixels_top_left", "normalized_top_left"}
_UNIT_KINDS = {"pdf_page", "image", "sheet", "slide", "html", "mime_part", "text"}
MAX_TABLE_GRID_CELLS = 1_000_000


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    space: BoxSpace

    def __post_init__(self) -> None:
        if self.space not in _BOX_SPACES:
            raise ValueError("unknown box coordinate space")
        if not all(isfinite(value) for value in (self.x0, self.y0, self.x1, self.y1)):
            raise ValueError("box coordinates must be finite")
        if self.x0 >= self.x1 or self.y0 >= self.y1:
            raise ValueError("box must have positive width and height")
        if self.space == "normalized_top_left" and not (
            0 <= self.x0 < self.x1 <= 1 and 0 <= self.y0 < self.y1 <= 1
        ):
            raise ValueError("normalized box must fit inside the unit square")


@dataclass(frozen=True)
class SourceUnit:
    unit_id: str
    kind: UnitKind
    ordinal: int
    text: str
    label: str | None = None
    width: float | None = None
    height: float | None = None

    def __post_init__(self) -> None:
        if not self.unit_id or self.ordinal < 0:
            raise ValueError("unit ID and nonnegative ordinal are required")
        if self.kind not in _UNIT_KINDS:
            raise ValueError("unknown source unit kind")
        for dimension in (self.width, self.height):
            if dimension is not None and (not isfinite(dimension) or dimension <= 0):
                raise ValueError("unit dimensions must be finite and positive")
        if (self.width is None) != (self.height is None):
            raise ValueError("unit width and height must be supplied together")


@dataclass(frozen=True)
class SourceAnchor:
    unit_id: str
    native_locator: str | None = None
    text_span: tuple[int, int] | None = None
    quote: str | None = None
    raw_box: Box | None = None
    display_box: Box | None = None

    def __post_init__(self) -> None:
        if not self.unit_id:
            raise ValueError("anchor unit ID is required")
        if self.native_locator is not None and not self.native_locator.strip():
            raise ValueError("native locator cannot be blank")
        if not any((self.native_locator, self.text_span, self.raw_box, self.display_box)):
            raise ValueError("anchor needs a native locator, text span, or real box")
        if self.text_span is not None:
            start, end = self.text_span
            if start < 0 or end <= start:
                raise ValueError("text span must be nonempty and nonnegative")
        elif self.quote is not None:
            raise ValueError("quote requires a text span")
        if self.display_box is not None and self.display_box.space != "normalized_top_left":
            raise ValueError("display box must use normalized top-left coordinates")


@dataclass(frozen=True)
class TableCell:
    row: int
    column: int
    text: str
    row_span: int = 1
    column_span: int = 1
    anchors: tuple[SourceAnchor, ...] = ()

    def __post_init__(self) -> None:
        if self.row < 0 or self.column < 0 or self.row_span < 1 or self.column_span < 1:
            raise ValueError("table cell grid offsets and spans must be valid")


@dataclass(frozen=True)
class Table:
    table_id: str
    cells: tuple[TableCell, ...]
    anchors: tuple[SourceAnchor, ...] = ()

    def __post_init__(self) -> None:
        if not self.table_id:
            raise ValueError("table ID is required")
        occupied: set[tuple[int, int]] = set()
        covered_count = 0
        for cell in self.cells:
            covered_count += cell.row_span * cell.column_span
            if covered_count > MAX_TABLE_GRID_CELLS:
                raise ValueError("table grid exceeds the parser contract limit")
            for row in range(cell.row, cell.row + cell.row_span):
                for column in range(cell.column, cell.column + cell.column_span):
                    if (row, column) in occupied:
                        raise ValueError("table cells cannot overlap in the parser grid")
                    occupied.add((row, column))


@dataclass(frozen=True)
class ParsedDocument:
    source_sha256: str
    source_format: str
    parser_id: str
    parser_version: str
    units: tuple[SourceUnit, ...]
    tables: tuple[Table, ...] = ()
    parser_config_sha256: str | None = None
    contract_version: int = field(default=2, init=False)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
        if self.parser_config_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", self.parser_config_sha256):
            raise ValueError("parser_config_sha256 must be a lowercase SHA-256 digest")
        if not self.source_format or not self.parser_id or not self.parser_version:
            raise ValueError("source format and parser identity are required")
        if not self.units:
            raise ValueError("a parsed document needs at least one source unit")
        units = {unit.unit_id: unit for unit in self.units}
        if len(units) != len(self.units):
            raise ValueError("source unit IDs must be unique")
        if len({table.table_id for table in self.tables}) != len(self.tables):
            raise ValueError("table IDs must be unique")
        for table in self.tables:
            for anchor in (*table.anchors, *(anchor for cell in table.cells for anchor in cell.anchors)):
                unit = units.get(anchor.unit_id)
                if unit is None:
                    raise ValueError("anchor refers to a missing source unit")
                if anchor.text_span is not None:
                    start, end = anchor.text_span
                    if end > len(unit.text):
                        raise ValueError("anchor text span exceeds source unit text")
                    if anchor.quote is not None and unit.text[start:end] != anchor.quote:
                        raise ValueError("anchor quote does not equal source unit text")

    def to_dict(self) -> dict[str, object]:
        """Return JSON-serializable parser data without adding inferred evidence."""
        return asdict(self)

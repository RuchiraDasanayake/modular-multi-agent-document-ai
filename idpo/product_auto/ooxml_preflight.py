"""Streaming XML checks before Office readers allocate objects from package parts."""

from __future__ import annotations

import posixpath
import re
import zipfile
from xml.parsers import expat

MAX_XML_ELEMENTS = 100_000
MAX_XML_DEPTH = 128
_CELL = re.compile(r"\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})", re.IGNORECASE)


def _coordinate(value: str) -> tuple[int, int]:
    match = _CELL.fullmatch(value)
    if not match:
        raise ValueError("invalid_sheet_coordinate")
    column = 0
    for character in match[1].upper():
        column = column * 26 + ord(character) - ord("A") + 1
    row = int(match[2])
    if row > 1_048_576 or column > 16_384:
        raise ValueError("invalid_sheet_coordinate")
    return row, column


class _Budget:
    def __init__(self, cell_limit: int, grid_limit: int, limit_error: type[ValueError],
                 spreadsheet: bool, word_processing: bool) -> None:
        self.cell_limit = cell_limit
        self.grid_limit = grid_limit
        self.limit_error = limit_error
        self.spreadsheet = spreadsheet
        self.word_processing = word_processing
        self.cells = 0
        self.expansion_cells = 0
        self.sheets = 0
        self.sheet_references = 0
        self.sheet_ids: set[tuple[str, str]] = set()
        self.relationships: dict[tuple[str, str], str] = {}


def preflight_xml_parts(archive: zipfile.ZipFile, *, max_xml_bytes: int,
                        cell_limit: int, grid_limit: int,
                        limit_error: type[ValueError], spreadsheet: bool = False,
                        word_processing: bool = False) -> None:
    """Check XML, including worksheet targets whose filename does not end in XML."""
    budget = _Budget(cell_limit, grid_limit, limit_error, spreadsheet, word_processing)
    pending = {entry.filename for entry in archive.infolist()
               if entry.filename.lower().endswith((".xml", ".rels"))}
    seen: set[str] = set()
    while pending:
        name = min(pending)
        pending.remove(name)
        if name in seen:
            continue
        seen.add(name)
        if name not in archive.namelist():
            raise ValueError("missing_ooxml_xml_part")
        if archive.getinfo(name).file_size > max_xml_bytes:
            raise limit_error("archive_member_limit")
        _scan_part(archive, name, budget, pending)
        targets = [budget.relationships[key] for key in budget.sheet_ids if key in budget.relationships]
        if len(targets) != len(set(targets)):
            raise ValueError("duplicate_worksheet_target")
        pending.update(budget.relationships[key] for key in budget.sheet_ids
                       if key in budget.relationships and budget.relationships[key] not in seen)


def _scan_part(archive: zipfile.ZipFile, name: str, budget: _Budget, pending: set[str]) -> None:
    parser = expat.ParserCreate(namespace_separator="}")
    depth = elements = 0
    parents: list[str] = []
    row = column = max_row = max_column = 0

    def forbid_dtd(*_args: object) -> None:
        raise ValueError("ooxml_dtd_forbidden")

    def check_grid(last_row: int, last_column: int) -> None:
        nonlocal max_row, max_column
        max_row = max(max_row, last_row)
        max_column = max(max_column, last_column)
        if max_row * max_column > budget.grid_limit:
            raise budget.limit_error("sheet_grid_limit")

    def start(tag: str, attributes: dict[str, str]) -> None:
        nonlocal depth, elements, row, column
        depth += 1
        elements += 1
        if depth > MAX_XML_DEPTH or elements > MAX_XML_ELEMENTS:
            raise budget.limit_error("archive_xml_structure_limit")
        local = tag.rsplit("}", 1)[-1]
        parent = parents[-1] if parents else ""
        parents.append(local)
        if depth == 1 and local == "worksheet":
            budget.sheets += 1
            if budget.sheets > 50:
                raise budget.limit_error("native_unit_limit")
        if (name == "[Content_Types].xml" and local == "Override"
                and attributes.get("ContentType", "").lower().endswith(("+xml", "/xml"))):
            pending.add(attributes.get("PartName", "").lstrip("/"))
        if name.lower().endswith(".rels") and local == "Relationship":
            target = attributes.get("Target", "")
            base = posixpath.dirname(posixpath.dirname(name))
            resolved = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                                         else posixpath.join(base, target))
            if attributes.get("TargetMode") == "External":
                resolved = target
            owner = posixpath.join(base, posixpath.basename(name)[:-5])
            key = (owner, attributes.get("Id", ""))
            if not key[1] or key in budget.relationships:
                raise ValueError("ambiguous_ooxml_relationship")
            budget.relationships[key] = resolved
            if attributes.get("Type", "").rsplit("/", 1)[-1] in {"worksheet", "comments"}:
                pending.add(resolved)
        if local == "sheet":
            budget.sheet_references += 1
            if budget.sheet_references > 50:
                raise budget.limit_error("native_unit_limit")
            for attribute, value in attributes.items():
                if attribute.rsplit("}", 1)[-1] == "id":
                    if (name, value) in budget.sheet_ids:
                        raise ValueError("duplicate_worksheet_reference")
                    budget.sheet_ids.add((name, value))
        if budget.word_processing and local in {"tc", "gridSpan"}:
            if local == "tc":
                budget.cells += 1
                budget.expansion_cells += 1
                if budget.cells > budget.cell_limit:
                    raise budget.limit_error("native_cell_limit")
            else:
                value = attributes.get("http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "1")
                if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= budget.grid_limit:
                    raise budget.limit_error("word_table_expansion_limit")
                budget.expansion_cells += int(value) - 1
            if budget.expansion_cells > budget.grid_limit:
                raise budget.limit_error("word_table_expansion_limit")
        # openpyxl accepts unexpected roots/namespaces for some containers and
        # treats every direct row child as a cell. Budget these conservatively.
        if not budget.spreadsheet:
            return
        if local == "row":
            raw_row = attributes.get("r")
            if raw_row is not None and (not raw_row.isascii() or not raw_row.isdigit()
                                        or not 1 <= int(raw_row) <= 1_048_576):
                raise ValueError("invalid_sheet_coordinate")
            row = int(raw_row) if raw_row is not None else row + 1
            column = 0
        if local == "c" or parent == "row":
            budget.cells += 1
            if budget.cells > budget.cell_limit:
                raise budget.limit_error("native_cell_limit")
            if "r" in attributes:
                cell_row, column = _coordinate(attributes["r"])
            else:
                cell_row, column = row, column + 1
            check_grid(cell_row, column)
        if local in {"mergeCell", "hyperlink", "comment"}:
            endpoints = attributes.get("ref", "").split(":")
            if len(endpoints) not in {1, 2}:
                raise ValueError("invalid_sheet_coordinate")
            first_row, first_column = _coordinate(endpoints[0])
            last_row, last_column = _coordinate(endpoints[-1])
            if first_row > last_row or first_column > last_column:
                raise ValueError("invalid_sheet_coordinate")
            check_grid(last_row, last_column)
            budget.expansion_cells += (last_row - first_row + 1) * (last_column - first_column + 1)
            if budget.expansion_cells > budget.grid_limit:
                raise budget.limit_error("sheet_expansion_limit")

    def end(_tag: str) -> None:
        nonlocal depth
        depth -= 1
        parents.pop()

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = forbid_dtd
    parser.EntityDeclHandler = forbid_dtd
    parser.ExternalEntityRefHandler = forbid_dtd
    try:
        with archive.open(name) as stream:
            while chunk := stream.read(64 * 1024):
                parser.Parse(chunk, False)
        parser.Parse(b"", True)
    except expat.ExpatError as error:
        raise ValueError("invalid_ooxml_xml") from error

"""Bounded, source-native readers for the product extraction path.

The generated text is a deterministic view of the source, not a byte offset in
the OOXML/HTML/EML container. Every table cell keeps a locator into the hashed
original and an exact span into that view. No cell geometry is inferred.
"""

from __future__ import annotations

import json
import re
import stat
import sys
import zipfile
from collections import defaultdict
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from importlib import metadata
from pathlib import Path

from idpo.core.types import Document, Page
from idpo.product_auto.ooxml_preflight import preflight_xml_parts
from idpo.product_auto.parsed_document import (
    ParsedDocument,
    SourceAnchor,
    SourceUnit,
    Table,
    TableCell,
)

NATIVE_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".html", ".eml"}
MAX_ARCHIVE_ENTRIES = 1024
MAX_ARCHIVE_UNCOMPRESSED = 64 * 1024 * 1024
MAX_ARCHIVE_XML_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 32 * 1024 * 1024
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 250_000
MAX_TABLE_CELLS = 20_000
MAX_HTML_ELEMENTS = 20_000
MAX_MIME_PARTS = 64
MAX_MIME_DEPTH = 10
MAX_SHEET_GRID_CELLS = 50_000


class NativeLimitError(ValueError):
    """An otherwise supported source exceeds a declared parser resource bound."""


def _locator(**items: object) -> str:
    return json.dumps(items, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class _Text:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.length = 0

    def add(self, value: str) -> tuple[int, int] | None:
        if not value:
            return None
        start = self.length
        self.length += len(value)
        if self.length > MAX_TEXT_CHARS:
            raise NativeLimitError("native_text_limit")
        self.parts.append(value)
        return start, self.length

    def text(self) -> str:
        return "".join(self.parts)


def _emit_table(
    output: _Text, unit_id: str, table_id: str,
    rows: list[list[tuple[int, int, str, str, int, int]]],
) -> Table:
    cells: list[TableCell] = []
    for row in rows:
        if output.length:
            output.add("\n")
        for index, (row_index, column_index, value, locator, row_span, column_span) in enumerate(row):
            if index:
                output.add("\t")
            span = output.add(value)
            anchor = SourceAnchor(unit_id, native_locator=locator, text_span=span, quote=value if span else None)
            cells.append(TableCell(row_index, column_index, value, row_span, column_span, (anchor,)))
            if len(cells) > MAX_TABLE_CELLS:
                raise NativeLimitError("native_cell_limit")
    return Table(table_id, tuple(cells))


def _preflight_archive(path: Path, required_member: str) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise NativeLimitError("archive_entry_limit")
            names = {item.filename for item in entries}
            if len(names) != len(entries):
                raise ValueError("duplicate_archive_member")
            if "[Content_Types].xml" not in names or required_member not in names:
                raise ValueError("invalid_ooxml_package")
            total = 0
            for item in entries:
                parts = item.filename.replace("\\", "/").split("/")
                if item.filename.startswith(("/", "\\")) or ":" in parts[0] or any(
                    part in {"", ".", ".."} for part in parts[:-1]
                ):
                    raise ValueError("unsafe_archive_member")
                if ".." in parts or item.flag_bits & 1:
                    raise ValueError("unsafe_archive_member")
                if item.create_system == 3 and stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError("unsafe_archive_member")
                if item.is_dir():
                    continue
                member_name = item.filename.lower()
                is_xml = member_name.endswith((".xml", ".rels"))
                maximum = MAX_ARCHIVE_XML_BYTES if is_xml else MAX_ARCHIVE_MEMBER_BYTES
                if item.file_size > maximum:
                    raise NativeLimitError("archive_member_limit")
                total += item.file_size
                if total > MAX_ARCHIVE_UNCOMPRESSED:
                    raise NativeLimitError("archive_expansion_limit")
                if item.compress_size and item.file_size / item.compress_size > 200:
                    raise NativeLimitError("archive_compression_ratio_limit")
                # Reading every member verifies CRC and catches truncated compressed data.
                with archive.open(item) as member:
                    previous = b""
                    while chunk := member.read(1024 * 1024):
                        if is_xml:
                            scan = previous + chunk
                            if b"<!DOCTYPE" in scan.upper() or b"<!ENTITY" in scan.upper():
                                raise ValueError("ooxml_dtd_forbidden")
                            previous = chunk[-16:]
            preflight_xml_parts(archive, max_xml_bytes=MAX_ARCHIVE_XML_BYTES,
                                cell_limit=MAX_TABLE_CELLS, grid_limit=MAX_SHEET_GRID_CELLS,
                                limit_error=NativeLimitError, spreadsheet=required_member == "xl/workbook.xml",
                                word_processing=required_member == "word/document.xml")
    except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise ValueError("invalid_ooxml_package") from exc


def _docx(path: Path, source_hash: str) -> ParsedDocument:
    from docx import Document as WordDocument
    from docx.table import Table as WordTable

    source = WordDocument(path)
    output = _Text()
    tables: list[Table] = []
    total_cells = 0
    unit_id = "document-1"
    for block_index, block in enumerate(source.iter_inner_content()):
        if isinstance(block, WordTable):
            table_index = len(tables)
            positions: dict[int, list[tuple[int, int]]] = defaultdict(list)
            origins: dict[int, object] = {}
            for row_index, row in enumerate(block.rows):
                for column_index, cell in enumerate(row.cells):
                    if cell.tables:
                        raise NativeLimitError("nested_docx_table_unsupported")
                    identity = id(cell._tc)
                    positions[identity].append((row_index, column_index))
                    origins[identity] = cell
            row_items: dict[int, list[tuple[int, int, str, str, int, int]]] = defaultdict(list)
            for identity, points in positions.items():
                first_row = min(row for row, _ in points)
                first_col = min(column for _, column in points)
                row_span = max(row for row, _ in points) - first_row + 1
                col_span = max(column for _, column in points) - first_col + 1
                if len(points) != row_span * col_span:
                    raise ValueError("nonrectangular_docx_merge")
                cell = origins[identity]
                row_items[first_row].append((first_row, first_col, cell.text,
                    _locator(kind="docx_table_cell", block_index=block_index,
                             table_index=table_index, row=first_row, column=first_col),
                    row_span, col_span))
            rows = [sorted(row_items[index], key=lambda item: item[1]) for index in sorted(row_items)]
            total_cells += sum(len(row) for row in rows)
            if total_cells > MAX_TABLE_CELLS:
                raise NativeLimitError("native_cell_limit")
            tables.append(_emit_table(output, unit_id, f"table-{table_index + 1}", rows))
        else:
            if output.length:
                output.add("\n")
            output.add(block.text)
    return ParsedDocument(source_hash, "docx", "python-docx", metadata.version("python-docx"),
                          (SourceUnit(unit_id, "text", 0, output.text(), label="Word document"),), tuple(tables))


def _xlsx(path: Path, source_hash: str) -> ParsedDocument:
    from openpyxl import load_workbook
    from openpyxl.utils.cell import range_boundaries

    workbook = load_workbook(path, read_only=False, data_only=False, keep_links=False, keep_vba=False)
    units: list[SourceUnit] = []
    tables: list[Table] = []
    total_cells = 0
    total_text = 0
    try:
        for sheet_index, sheet in enumerate(workbook.worksheets):
            if sheet_index >= 50:
                raise NativeLimitError("native_unit_limit")
            if sheet.max_row * sheet.max_column > MAX_SHEET_GRID_CELLS:
                raise NativeLimitError("sheet_grid_limit")
            output = _Text()
            table_ranges = []
            for declared in sheet.tables.values():
                table_ranges.append((declared.name, range_boundaries(declared.ref)))
            rows = []
            for row in sheet.iter_rows():
                items = []
                for cell in row:
                    belonging = next((name for name, (c0, r0, c1, r1) in table_ranges
                                      if r0 <= cell.row <= r1 and c0 <= cell.column <= c1), None)
                    if cell.value is None and belonging is None:
                        continue
                    total_cells += 1
                    if total_cells > MAX_TABLE_CELLS:
                        raise NativeLimitError("native_cell_limit")
                    value = "" if cell.value is None else str(cell.value)
                    items.append((cell.row - 1, cell.column - 1, value,
                        _locator(kind="xlsx_cell", sheet=sheet.title, table=belonging,
                                 address=cell.coordinate, formula=cell.data_type == "f"), 1, 1))
                if items:
                    rows.append(items)
            unit_id = f"sheet-{sheet_index + 1}"
            tables.append(_emit_table(output, unit_id, f"sheet-grid-{sheet_index + 1}", rows))
            total_text += output.length
            if total_text > MAX_TEXT_CHARS:
                raise NativeLimitError("native_text_limit")
            units.append(SourceUnit(unit_id, "sheet", sheet_index, output.text(), label=sheet.title))
    finally:
        workbook.close()
    if not units:
        units.append(SourceUnit("sheet-1", "sheet", 0, "", label="Empty workbook"))
    return ParsedDocument(source_hash, "xlsx", "openpyxl", metadata.version("openpyxl"),
                          tuple(units), tuple(tables))


def _pptx(path: Path, source_hash: str) -> ParsedDocument:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    presentation = Presentation(path)
    units: list[SourceUnit] = []
    tables: list[Table] = []
    total_cells = 0
    total_text = 0
    if len(presentation.slides) > 50:
        raise NativeLimitError("native_unit_limit")
    for slide_index, slide in enumerate(presentation.slides, start=1):
        output = _Text()
        unit_id = f"slide-{slide_index}"
        for shape in slide.shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP and len(shape.shapes):
                raise NativeLimitError("grouped_pptx_shapes_unsupported")
            if shape.has_table:
                grid = shape.table
                rows = []
                for row_index in range(len(grid.rows)):
                    items = []
                    for column_index in range(len(grid.columns)):
                        cell = grid.cell(row_index, column_index)
                        if cell.is_spanned:
                            continue
                        total_cells += 1
                        if total_cells > MAX_TABLE_CELLS:
                            raise NativeLimitError("native_cell_limit")
                        items.append((row_index, column_index, cell.text,
                            _locator(kind="pptx_table_cell", slide=slide_index,
                                     shape_id=shape.shape_id, row=row_index, column=column_index),
                            cell.span_height, cell.span_width))
                    if items:
                        rows.append(items)
                tables.append(_emit_table(output, unit_id, f"slide-{slide_index}-shape-{shape.shape_id}", rows))
            elif shape.has_text_frame and shape.text:
                if output.length:
                    output.add("\n")
                output.add(shape.text)
        total_text += output.length
        if total_text > MAX_TEXT_CHARS:
            raise NativeLimitError("native_text_limit")
        units.append(SourceUnit(unit_id, "slide", slide_index - 1, output.text(), label=f"Slide {slide_index}"))
    if not units:
        units.append(SourceUnit("slide-1", "slide", 0, "", label="Empty presentation"))
    return ParsedDocument(source_hash, "pptx", "python-pptx", metadata.version("python-pptx"),
                          tuple(units), tuple(tables))


_HTML_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "dd", "div", "dl", "dt", "footer",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav",
    "ol", "p", "pre", "section", "ul",
}
_HIDDEN_STYLE = re.compile(
    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:!important)?\s*(?:;|$)",
    re.IGNORECASE,
)


def _html_hidden(element) -> bool:
    if not isinstance(element.tag, str):
        return True
    tag = str(element.tag).lower()
    return (tag in {"script", "style", "noscript", "template", "svg", "canvas"}
            or element.get("hidden") is not None
            or (element.get("aria-hidden") or "").lower() == "true"
            or (tag == "input" and (element.get("type") or "").lower() == "hidden")
            or bool(_HIDDEN_STYLE.search(element.get("style") or "")))


def _html_visible_cell_text(element) -> str:
    def fragments(node):
        if _html_hidden(node):
            return
        if node.text:
            yield node.text
        for child in node:
            yield from fragments(child)
            if child.tail:
                yield child.tail

    return "".join(fragments(element)).strip()


def _html_content(source: bytes, source_hash: str, *, mime_path: list[int] | None = None,
                  parser_encoding: str | None = None) -> ParsedDocument:
    from lxml import etree

    if len(source) > MAX_HTML_BYTES:
        raise NativeLimitError("html_size_limit")
    parser = etree.HTMLParser(encoding=parser_encoding, no_network=True, recover=True, huge_tree=False)
    root = etree.fromstring(source, parser=parser)
    if root is None:
        raise ValueError("empty_html_document")
    if sum(1 for _ in root.iter()) > MAX_HTML_ELEMENTS:
        raise NativeLimitError("html_element_limit")
    if root.xpath("//table//table"):
        raise NativeLimitError("nested_html_table_unsupported")
    body = root.find(".//body")
    if body is None:
        body = root
    output = _Text()
    tables: list[Table] = []
    total_cells = 0
    unit_id = "mime-1" if mime_path is not None else "html-1"
    tree = root.getroottree()
    pending_space = False

    def last_char() -> str:
        return output.parts[-1][-1] if output.parts else ""

    def separate() -> None:
        nonlocal pending_space
        pending_space = False
        if output.length and last_char() != "\n":
            output.add("\n")

    def add_text(value: str | None) -> None:
        nonlocal pending_space
        if not value:
            return
        normalized = re.sub(r"\s+", " ", value)
        content = normalized.strip()
        if not content:
            pending_space = pending_space or bool(output.length)
            return
        if (pending_space or normalized.startswith(" ")) and last_char() not in {"", "\n", " ", "\t"}:
            output.add(" ")
        output.add(content)
        pending_space = normalized.endswith(" ")

    def walk(element) -> None:
        nonlocal total_cells, pending_space
        tag = str(element.tag).lower()
        if _html_hidden(element):
            return
        if tag == "table":
            def hidden_under_table(node) -> bool:
                while node is not None:
                    if _html_hidden(node):
                        return True
                    if node is element:
                        return False
                    node = node.getparent()
                return True

            rows = []
            occupied: set[tuple[int, int]] = set()
            visible_rows = [row for row in element.xpath("./tr | ./thead/tr | ./tbody/tr | ./tfoot/tr")
                            if not hidden_under_table(row)]
            for row_index, row in enumerate(visible_rows):
                items = []
                column_index = 0
                for cell in row.xpath("./th | ./td"):
                    if hidden_under_table(cell):
                        continue
                    while (row_index, column_index) in occupied:
                        column_index += 1
                    try:
                        row_span = int(cell.get("rowspan", "1"))
                        column_span = int(cell.get("colspan", "1"))
                    except ValueError as exc:
                        raise ValueError("invalid_html_table_span") from exc
                    if not 1 <= row_span <= 128 or not 1 <= column_span <= 128:
                        raise NativeLimitError("html_table_span_limit")
                    if len(occupied) + row_span * column_span > MAX_TABLE_CELLS:
                        raise NativeLimitError("native_cell_limit")
                    total_cells += 1
                    if total_cells > MAX_TABLE_CELLS:
                        raise NativeLimitError("native_cell_limit")
                    for covered_row in range(row_index, row_index + row_span):
                        for covered_column in range(column_index, column_index + column_span):
                            if (covered_row, covered_column) in occupied:
                                raise ValueError("overlapping_html_table_cells")
                            occupied.add((covered_row, covered_column))
                    value = _html_visible_cell_text(cell)
                    locator = _locator(kind="eml_html_cell" if mime_path is not None else "html_dom_cell",
                                       xpath=tree.getpath(cell), **({"mime_path": mime_path} if mime_path is not None else {}))
                    items.append((row_index, column_index, value, locator, row_span, column_span))
                    column_index += column_span
                rows.append(items)
            tables.append(_emit_table(output, unit_id, f"table-{len(tables) + 1}", rows))
            separate()
            return
        if tag == "br":
            separate()
            return
        if tag in _HTML_BLOCK_TAGS:
            separate()
        add_text(element.text)
        for child in element:
            walk(child)
            add_text(child.tail)
        if tag in _HTML_BLOCK_TAGS:
            separate()

    walk(body)
    source_format = "eml" if mime_path is not None else "html"
    kind = "mime_part" if mime_path is not None else "html"
    label = f"MIME part {mime_path}" if mime_path is not None else "HTML document"
    return ParsedDocument(source_hash, source_format, "lxml-html", metadata.version("lxml"),
                          (SourceUnit(unit_id, kind, 0, output.text().rstrip("\n"), label=label),), tuple(tables))


def _eml(path: Path, source_hash: str) -> ParsedDocument:
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    parts: list[tuple[list[int], EmailMessage]] = []

    def visit(part: EmailMessage, path_to_part: list[int]) -> None:
        if len(parts) >= MAX_MIME_PARTS or len(path_to_part) > MAX_MIME_DEPTH:
            raise NativeLimitError("mime_structure_limit")
        if part.defects:
            raise ValueError("malformed_mime_message")
        parts.append((path_to_part, part))
        if part.is_multipart():
            for index, child in enumerate(part.iter_parts()):
                visit(child, [*path_to_part, index])

    visit(message, [])
    bodies = [(where, part) for where, part in parts
              if not part.is_multipart() and part.get_content_disposition() != "attachment"
              and part.get_content_type() in {"text/html", "text/plain"}]
    selected = next(((where, part) for where, part in bodies if part.get_content_type() == "text/html"), None)
    if selected is None:
        selected = next(iter(bodies), None)
    if selected is None:
        raise ValueError("no_text_mime_part")
    where, part = selected
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        raise TypeError("invalid_text_mime_part")
    mime_charset = part.get_content_charset()
    if part.get_content_type() == "text/html" and mime_charset is None:
        return _html_content(payload, source_hash, mime_path=where)
    try:
        content = payload.decode(mime_charset or "utf-8", errors="strict")
    except (LookupError, UnicodeError) as exc:
        raise ValueError("invalid_mime_charset") from exc
    if part.get_content_type() == "text/html":
        return _html_content(content.encode("utf-8"), source_hash, mime_path=where,
                             parser_encoding="utf-8")
    if len(content.encode("utf-8")) > MAX_HTML_BYTES or len(content) > MAX_TEXT_CHARS:
        raise NativeLimitError("mime_body_size_limit")
    return ParsedDocument(source_hash, "eml", "python-email", sys.version.split()[0],
                          (SourceUnit("mime-1", "mime_part", 0, content, label=f"MIME part {where}"),))


def parse_native_document(path: Path, source_hash: str) -> tuple[Document, ParsedDocument]:
    suffix = path.suffix.lower()
    if suffix not in NATIVE_EXTENSIONS:
        raise ValueError("unsupported_native_format")
    if suffix in {".docx", ".xlsx", ".pptx"}:
        _preflight_archive(path, {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml",
                                  ".pptx": "ppt/presentation.xml"}[suffix])
    if suffix == ".docx":
        parsed = _docx(path, source_hash)
    elif suffix == ".xlsx":
        parsed = _xlsx(path, source_hash)
    elif suffix == ".pptx":
        parsed = _pptx(path, source_hash)
    elif suffix == ".html":
        parsed = _html_content(path.read_bytes(), source_hash)
    else:
        parsed = _eml(path, source_hash)
    if sum(len(unit.text) for unit in parsed.units) > MAX_TEXT_CHARS:
        raise NativeLimitError("native_text_limit")
    if sum(len(table.cells) for table in parsed.tables) > MAX_TABLE_CELLS:
        raise NativeLimitError("native_cell_limit")
    pages = [Page(number=index, text=unit.text, raw_text=unit.text, metadata={"native_unit_id": unit.unit_id})
             for index, unit in enumerate(parsed.units, start=1)]
    document = Document(doc_id=path.stem, source="digital", path=str(path), pages=pages,
                        metadata={"native_format": parsed.source_format})
    return document, parsed

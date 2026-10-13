"""Reject spreadsheet allocation traps before openpyxl opens the workbook."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from idpo.product_auto.native_formats import NativeLimitError, parse_native_document

FIXTURE = Path(__file__).resolve().parents[2] / "product_eval/fixtures/mixed_format_docling_v1/order.xlsx"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _workbook(tmp_path: Path, body: str, *, encoding: str = "utf-8") -> Path:
    path = tmp_path / "bounded.xlsx"
    with zipfile.ZipFile(FIXTURE) as original, zipfile.ZipFile(path, "w") as changed:
        for entry in original.infolist():
            data = original.read(entry)
            if entry.filename == "xl/worksheets/sheet1.xml":
                data = (f'<?xml version="1.0" encoding="{encoding}"?>'
                        f'<worksheet xmlns="{NS}">{body}</worksheet>').encode(encoding)
            changed.writestr(entry, data)
    return path


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
@pytest.mark.parametrize("body,reason", [
    ('<sheetData/><mergeCells><mergeCell ref="A1:XFD1048576"/></mergeCells>', "sheet_grid_limit"),
    ('<sheetData/><hyperlinks><hyperlink ref="A1:XFD1048576" location="A1"/></hyperlinks>', "sheet_grid_limit"),
    ('<sheetData><row r="5000"><c r="Z5000"><v>1</v></c></row></sheetData>', "sheet_grid_limit"),
])
def test_rejects_expansion_before_workbook_load(tmp_path: Path, monkeypatch, encoding: str,
                                              body: str, reason: str) -> None:
    source = _workbook(tmp_path, body, encoding=encoding)

    def forbidden(*args, **kwargs):
        pytest.fail("unbounded workbook reached the allocating parser")

    monkeypatch.setattr("openpyxl.load_workbook", forbidden)
    with pytest.raises(NativeLimitError, match=reason):
        parse_native_document(source, hashlib.sha256(source.read_bytes()).hexdigest())


def test_small_merge_is_still_readable(tmp_path: Path) -> None:
    source = _workbook(tmp_path, '<sheetData><row r="1"><c r="A1" t="inlineStr">'
                       '<is><t>Visible</t></is></c></row></sheetData>'
                       '<mergeCells><mergeCell ref="A1:B2"/></mergeCells>')
    parsed = parse_native_document(source, hashlib.sha256(source.read_bytes()).hexdigest())[1]
    assert [cell.text for table in parsed.tables for cell in table.cells] == ["Visible"]


def _replace_parts(source: Path, destination: Path, replacements: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as changed:
        for entry in original.infolist():
            changed.writestr(entry, replacements.get(entry.filename, original.read(entry)))
        for name, data in replacements.items():
            if name not in original.namelist():
                changed.writestr(name, data)
    return destination


@pytest.mark.parametrize("count,same_id,reason", [
    (51, False, "native_unit_limit"), (2, True, "duplicate_worksheet_reference"),
    (2, False, "duplicate_worksheet_target"),
])
def test_workbook_references_cannot_multiply_allocations(tmp_path: Path, monkeypatch,
                                                       count: int, same_id: bool, reason: str) -> None:
    relationship_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    sheets = ''.join(f'<sheet name="Sheet{i}" sheetId="{i}" r:id="rId{1 if same_id else i}"/>'
                     for i in range(1, count + 1))
    relationships = ''.join(f'<Relationship Id="rId{i}" Type="{relationship_ns}/worksheet" '
                            'Target="/xl/worksheets/sheet1.xml"/>' for i in range(1, count + 1))
    source = _replace_parts(FIXTURE, tmp_path / "repeated.xlsx", {
        "xl/workbook.xml": f'<workbook xmlns="{NS}" xmlns:r="{relationship_ns}"><sheets>{sheets}</sheets></workbook>'.encode(),
        "xl/_rels/workbook.xml.rels": ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      + relationships + '</Relationships>').encode(),
    })
    monkeypatch.setattr("openpyxl.load_workbook", lambda *args, **kwargs: pytest.fail("unsafe parser call"))
    with pytest.raises(ValueError, match=reason):
        parse_native_document(source, hashlib.sha256(source.read_bytes()).hexdigest())


def test_comment_range_with_non_xml_filename_is_bounded(tmp_path: Path, monkeypatch) -> None:
    source = _replace_parts(FIXTURE, tmp_path / "comments.xlsx", {
        "xl/comments/comment1.bin": (f'<comments xmlns="{NS}"><authors><author>Reviewer</author></authors>'
                                      '<commentList><comment ref="A1:XFD1048576" authorId="0">'
                                      '<text><t>Comment</t></text></comment></commentList></comments>').encode(),
        "xl/worksheets/_rels/sheet1.xml.rels": (
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" '
            b'Target="../comments/comment1.bin"/></Relationships>'),
    })
    monkeypatch.setattr("openpyxl.load_workbook", lambda *args, **kwargs: pytest.fail("unsafe parser call"))
    with pytest.raises(NativeLimitError, match="sheet_grid_limit"):
        parse_native_document(source, hashlib.sha256(source.read_bytes()).hexdigest())


@pytest.mark.parametrize("span,limit", [(1_000_000_000, 50_000), (4, 10)])
@pytest.mark.parametrize("extra_attribute", ["", 'xmlns:x="urn:unexpected" x:val="1" '])
def test_word_grid_span_is_bounded_before_reader(tmp_path: Path, monkeypatch, span: int, limit: int,
                                               extra_attribute: str) -> None:
    from idpo.product_auto import native_formats

    fixture = FIXTURE.with_suffix(".docx")
    with zipfile.ZipFile(fixture) as archive:
        document = archive.read("word/document.xml").replace(
            b'</w:tcPr>', f'<w:gridSpan {extra_attribute}w:val="{span}"/></w:tcPr>'.encode())
    source = _replace_parts(fixture, tmp_path / "spanned.docx", {"word/document.xml": document})
    monkeypatch.setattr(native_formats, "MAX_SHEET_GRID_CELLS", limit)
    monkeypatch.setattr("docx.Document", lambda *args, **kwargs: pytest.fail("unsafe parser call"))
    with pytest.raises(NativeLimitError, match="word_table_expansion_limit"):
        parse_native_document(source, hashlib.sha256(source.read_bytes()).hexdigest())


@pytest.mark.parametrize("wrong_type", [False, True])
def test_relationship_target_with_non_xml_name_is_checked(tmp_path: Path, monkeypatch, wrong_type: bool) -> None:
    source = _workbook(tmp_path, '<sheetData/><mergeCells>'
                       '<mergeCell ref="A1:XFD1048576"/></mergeCells>')
    renamed = tmp_path / "renamed.xlsx"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(renamed, "w") as changed:
        for entry in original.infolist():
            data = original.read(entry)
            name = entry.filename
            if name == "xl/worksheets/sheet1.xml":
                name = "xl/worksheets/sheet1.bin"
            elif name == "xl/_rels/workbook.xml.rels":
                data = data.replace(b"sheet1.xml", b"sheet1.bin")
                if wrong_type:
                    data = data.replace(b"/relationships/worksheet", b"/relationships/unknown")
            elif name == "[Content_Types].xml":
                data = data.replace(b"/xl/worksheets/sheet1.xml", b"/xl/worksheets/sheet1.bin")
                data = data.replace(b"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
                                    b"application/octet-stream")
            changed.writestr(name, data)
    monkeypatch.setattr("openpyxl.load_workbook", lambda *args, **kwargs: pytest.fail("unsafe parser call"))
    with pytest.raises(NativeLimitError, match="sheet_grid_limit"):
        parse_native_document(renamed, hashlib.sha256(renamed.read_bytes()).hexdigest())


def test_unexpected_worksheet_root_cannot_bypass_child_allocation_bounds(tmp_path: Path, monkeypatch) -> None:
    source = _workbook(tmp_path, '<sheetData/><mergeCells>'
                       '<mergeCell ref="A1:XFD1048576"/></mergeCells>')
    changed_path = tmp_path / "wrapped.xlsx"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(changed_path, "w") as changed:
        for entry in original.infolist():
            data = original.read(entry)
            if entry.filename == "xl/worksheets/sheet1.xml":
                data = data.replace(b"worksheet", b"wrapper")
            changed.writestr(entry, data)
    monkeypatch.setattr("openpyxl.load_workbook", lambda *args, **kwargs: pytest.fail("unsafe parser call"))
    with pytest.raises(NativeLimitError, match="sheet_grid_limit"):
        parse_native_document(changed_path, hashlib.sha256(changed_path.read_bytes()).hexdigest())


@pytest.mark.parametrize("body", [
    '<sheetData/><mergeCells><mergeCell xmlns="urn:unexpected" ref="A1:XFD1048576"/></mergeCells>',
    '<sheetData/><hyperlinks><hyperlink xmlns="urn:unexpected" ref="A1:XFD1048576" location="A1"/></hyperlinks>',
    '<sheetData><row r="1"><anything xmlns="urn:unexpected" r="XFD1048576"/></row></sheetData>',
])
def test_permissive_reader_namespaces_do_not_bypass_budget(tmp_path: Path, monkeypatch, body: str) -> None:
    source = _workbook(tmp_path, body)
    monkeypatch.setattr("openpyxl.load_workbook", lambda *args, **kwargs: pytest.fail("unsafe parser call"))
    with pytest.raises(NativeLimitError, match="sheet_grid_limit"):
        parse_native_document(source, hashlib.sha256(source.read_bytes()).hexdigest())


def test_aggregate_range_work_is_bounded_before_parser(tmp_path: Path, monkeypatch) -> None:
    from idpo.product_auto import native_formats

    source = _workbook(tmp_path, '<sheetData/><mergeCells>'
                       '<mergeCell ref="A1:B2"/><mergeCell ref="A1:B2"/></mergeCells>')
    monkeypatch.setattr(native_formats, "MAX_SHEET_GRID_CELLS", 7)
    monkeypatch.setattr("openpyxl.load_workbook", lambda *args, **kwargs: pytest.fail("unsafe parser call"))
    with pytest.raises(NativeLimitError, match="sheet_expansion_limit"):
        parse_native_document(source, hashlib.sha256(source.read_bytes()).hexdigest())


def test_utf16_cells_count_toward_workbook_budget(tmp_path: Path, monkeypatch) -> None:
    from idpo.product_auto import native_formats

    source = _workbook(tmp_path, '<sheetData><row r="1"><c r="A1"/><c r="B1"/></row></sheetData>',
                       encoding="utf-16")
    monkeypatch.setattr(native_formats, "MAX_TABLE_CELLS", 1)
    monkeypatch.setattr("openpyxl.load_workbook", lambda *args, **kwargs: pytest.fail("unsafe parser call"))
    with pytest.raises(NativeLimitError, match="native_cell_limit"):
        parse_native_document(source, hashlib.sha256(source.read_bytes()).hexdigest())


def test_utf16_dtd_is_forbidden_before_office_parser(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "dtd.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", ('<?xml version="1.0" encoding="utf-16"?>'
            '<!DOCTYPE document [<!ENTITY injected "untrusted">]>'
            '<document>&injected;</document>').encode("utf-16"))
    monkeypatch.setattr("docx.Document", lambda *args, **kwargs: pytest.fail("unsafe parser call"))
    with pytest.raises(ValueError, match="ooxml_dtd_forbidden"):
        parse_native_document(source, hashlib.sha256(source.read_bytes()).hexdigest())


@pytest.mark.parametrize("depth_case", [True, False])
def test_xml_structure_is_bounded(tmp_path: Path, monkeypatch, depth_case: bool) -> None:
    from idpo.product_auto import ooxml_preflight

    body = "<sheetData>" * 129 + "</sheetData>" * 129 if depth_case else "<sheetData/>"
    source = _workbook(tmp_path, body)
    if not depth_case:
        monkeypatch.setattr(ooxml_preflight, "MAX_XML_ELEMENTS", 1)
    monkeypatch.setattr("openpyxl.load_workbook", lambda *args, **kwargs: pytest.fail("unsafe parser call"))
    with pytest.raises(NativeLimitError, match="archive_xml_structure_limit"):
        parse_native_document(source, hashlib.sha256(source.read_bytes()).hexdigest())

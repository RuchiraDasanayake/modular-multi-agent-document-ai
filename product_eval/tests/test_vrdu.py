from __future__ import annotations

import gzip
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from idpo.product_auto.workflow import _doc_id as runtime_doc_id
from product_eval.contracts import load_jsonl
from product_eval.datasets.vrdu import (
    DATASET_COMMIT,
    DatasetError,
    _gold_record,
    build_vrdu_cohort,
)


def _annotation(text: str, source: str, *, from_index: int = 0) -> list[object]:
    start = source.index(text, from_index)
    return [text, [0, 0.1, 0.1, 0.2, 0.2], [[start, start + len(text)]]]


def _row(filename: str, text: str, annotations: list[object]) -> dict[str, object]:
    return {
        "filename": filename,
        "file_path": f"./pdfs/{filename}",
        "ocr": {"text": text, "pages": [{"page_id": 0, "segment": [0, len(text)]}]},
        "annotations": annotations,
    }


def _write_family(
    root: Path,
    family: str,
    rows: list[dict[str, object]],
    matchers: dict[str, str],
    line_items: set[str] | None = None,
) -> None:
    main = root / family / "main"
    pdf_dir = main / "pdfs"
    pdf_dir.mkdir(parents=True)
    for row in rows:
        (pdf_dir / str(row["filename"])).write_bytes(b"%PDF-1.4\n" + str(row["filename"]).encode())
    meta: dict[str, object] = {"entity_name_to_match_func": matchers}
    if line_items is not None:
        meta["entity_appearance_pattern"] = {
            name: "line_item" if name in line_items else "unrepeated" for name in matchers
        }
    (main / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with gzip.open(main / "dataset.jsonl.gz", "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_vrdu_cohort_pairs_and_hashes_sources_and_preserves_linked_rows(tmp_path: Path) -> None:
    root = tmp_path / "creator"
    reg_text = "Name Ada\nID 123\n"
    ad_text = "Buyer B\nItem A 9\nItem C 3\n"
    _write_family(
        root,
        "registration-form",
        [
            _row("z.pdf", reg_text, [["registrant_name", [_annotation("Ada", reg_text)]]]),
            _row("a.pdf", reg_text, [["registration_num", [_annotation("123", reg_text)]]]),
        ],
        {"registration_num": "NumericalStringMatch", "registrant_name": "NameMatch"},
    )
    _write_family(
        root,
        "ad-buy-form",
        [
            _row(
                "b.pdf",
                ad_text,
                [
                    ["buyer", [_annotation("B", ad_text)]],
                    [["item", "price"], [[_annotation("A", ad_text), _annotation("9", ad_text)]]],
                    [["item", "price"], [[_annotation("C", ad_text), _annotation("3", ad_text)]]],
                ],
            )
        ],
        {"buyer": "GeneralStringMatch", "item": "GeneralStringMatch", "price": "PriceMatch"},
        {"item", "price"},
    )
    output = tmp_path / "output"
    report = build_vrdu_cohort(root, output, quotas={"registration-form": 1, "ad-buy-form": 1}, verify_commit=False)

    cohort = _read_jsonl(output / "cohort.jsonl")
    gold = load_jsonl(output / "gold.jsonl", kind="gold")
    assert report["cohort_count"] == report["distinct_source_sha256_count"] == report["gold_count"] == 2
    assert [item["source_id"] for item in cohort] == ["registration-form/a.pdf", "ad-buy-form/b.pdf"]
    for item in cohort:
        assert item["source_sha256"] == hashlib.sha256(Path(item["source_path"]).read_bytes()).hexdigest()
        assert item["doc_id"] == runtime_doc_id(Path(item["source_path"]).name, item["source_sha256"], 0)
        assert item["doc_id"] in gold
    reg = gold[cohort[0]["doc_id"]]
    assert reg["gold_values"][0]["value"] == "123"
    assert reg["gold_values"][0]["evidence"] == {"page": 1, "start": 12, "end": 15, "quote": "123"}
    assert reg["gold_values"][1]["value"] is None
    ad = gold[cohort[1]["doc_id"]]
    assert {entry["field_id"]: entry["value"] for entry in ad["gold_values"]} == {
        "buyer": "B",
        "item": [{"row": 0, "value": "A"}, {"row": 1, "value": "C"}],
        "price": [{"row": 0, "value": "9"}, {"row": 1, "value": "3"}],
    }
    assert {field["field_id"]: field["type"] for field in ad["gold_schema"]} == {
        "buyer": "string", "item": "array[object]", "price": "array[object]"
    }
    assert report["annotation_stats"]["linked_rows"] == 2
    assert report["files_sha256"]["gold.jsonl"] == hashlib.sha256((output / "gold.jsonl").read_bytes()).hexdigest()


def test_vrdu_repeated_different_values_remain_ordered_and_have_no_single_evidence(tmp_path: Path) -> None:
    root = tmp_path / "creator"
    text = "Code 16/9\nCode 1619\n"
    _write_family(
        root,
        "registration-form",
        [_row("a.pdf", text, [["registration_num", [_annotation("16/9", text), _annotation("1619", text)]]])],
        {"registration_num": "NumericalStringMatch"},
    )
    _write_family(root, "ad-buy-form", [_row("b.pdf", "B\n", [["buyer", [_annotation("B", "B\n")]]])], {"buyer": "GeneralStringMatch"})
    output = tmp_path / "output"
    report = build_vrdu_cohort(root, output, quotas={"registration-form": 1, "ad-buy-form": 1}, verify_commit=False)
    reg = _read_jsonl(output / "gold.jsonl")[0]
    assert reg["gold_schema"][0]["type"] == "array[string]"
    assert reg["gold_values"][0] == {"field_id": "registration_num", "value": ["16/9", "1619"]}
    assert report["annotation_stats"]["divergent_scalar_fields_as_ordered_lists"] == 1


def test_vrdu_preserves_explicit_partial_groups_and_varying_column_order() -> None:
    text = "A 11/ B C 22/ D 33/"
    source = _row("partial.pdf", text, [
        [["item", "date"], [[_annotation("A", text), _annotation("11/", text)]]],
        [["item"], [[_annotation("B", text)]]],
        [["date", "item"], [
            [_annotation("22/", text), _annotation("C", text)],
            [_annotation("33/", text), _annotation("D", text)],
        ]],
    ])
    record, stats = _gold_record(source, "synthetic", {"item": "GeneralStringMatch", "date": "DateMatch"}, {"item", "date"})
    values = {entry["field_id"]: entry["value"] for entry in record["gold_values"]}
    assert values["item"] == [
        {"row": 0, "value": "A"}, {"row": 1, "value": "B"},
        {"row": 2, "value": "C"}, {"row": 3, "value": "D"},
    ]
    # Missing dates keep their group's row ordinal; incomplete source strings
    # remain incomplete instead of being guessed or re-associated with a row.
    assert values["date"] == [
        {"row": 0, "value": "11/"}, {"row": 2, "value": "22/"}, {"row": 3, "value": "33/"},
    ]
    assert stats["linked_rows"] == 4


def test_vrdu_converts_global_ocr_offset_to_second_page_offset(tmp_path: Path) -> None:
    root = tmp_path / "creator"
    text = "P1 A\nP2 B\n"
    registration = _row("a.pdf", text, [["registrant_name", [_annotation("B", text)]]])
    registration["ocr"]["pages"] = [
        {"page_id": 0, "segment": [0, 5]},
        {"page_id": 1, "segment": [5, len(text)]},
    ]
    _write_family(root, "registration-form", [registration], {"registrant_name": "NameMatch"})
    _write_family(root, "ad-buy-form", [_row("b.pdf", "B\n", [["buyer", [_annotation("B", "B\n")]]])], {"buyer": "GeneralStringMatch"})
    output = tmp_path / "output"
    build_vrdu_cohort(root, output, quotas={"registration-form": 1, "ad-buy-form": 1}, verify_commit=False)
    reg = _read_jsonl(output / "gold.jsonl")[0]
    assert reg["pages"] == [{"page": 1, "text": "P1 A\n"}, {"page": 2, "text": "P2 B\n"}]
    assert reg["gold_values"][0]["evidence"] == {"page": 2, "start": 3, "end": 4, "quote": "B"}


def test_vrdu_keeps_unmappable_document_in_execution_cohort(tmp_path: Path) -> None:
    root = tmp_path / "creator"
    _write_family(root, "registration-form", [_row("a.pdf", "A\n", [["unknown", [_annotation("A", "A\n")]]])], {"known": "NameMatch"})
    _write_family(root, "ad-buy-form", [_row("b.pdf", "B\n", [["buyer", [_annotation("B", "B\n")]]])], {"buyer": "GeneralStringMatch"})
    output = tmp_path / "output"
    report = build_vrdu_cohort(root, output, quotas={"registration-form": 1, "ad-buy-form": 1}, verify_commit=False)
    assert report["cohort_count"] == 2
    assert report["gold_count"] == 1
    assert _read_jsonl(output / "exclusions.jsonl")[0]["reason"] == "unknown_or_nested_scalar_annotation"


def test_vrdu_rejects_row_pdf_mismatch_before_creating_output(tmp_path: Path) -> None:
    root = tmp_path / "creator"
    _write_family(root, "registration-form", [_row("a.pdf", "A\n", [])], {"known": "NameMatch"})
    _write_family(root, "ad-buy-form", [_row("b.pdf", "B\n", [])], {"buyer": "GeneralStringMatch"})
    dataset = root / "registration-form" / "main" / "dataset.jsonl.gz"
    with gzip.open(dataset, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(_row("missing.pdf", "X\n", [])) + "\n")
    output = tmp_path / "output"
    with pytest.raises(DatasetError, match="row/PDF pairing differs"):
        build_vrdu_cohort(root, output, quotas={"registration-form": 1, "ad-buy-form": 1}, verify_commit=False)
    assert not output.exists()


def test_vrdu_archive_mode_verifies_extracted_bytes(tmp_path: Path) -> None:
    root = tmp_path / "creator"
    _write_family(root, "registration-form", [_row("a.pdf", "A\n", [["name", [_annotation("A", "A\n")]]])], {"name": "NameMatch"})
    _write_family(root, "ad-buy-form", [_row("b.pdf", "B\n", [["buyer", [_annotation("B", "B\n")]]])], {"buyer": "GeneralStringMatch"})
    archive_path = tmp_path / "creator.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, f"vrdu-{DATASET_COMMIT}/{path.relative_to(root).as_posix()}")
    report = build_vrdu_cohort(
        root,
        tmp_path / "output",
        quotas={"registration-form": 1, "ad-buy-form": 1},
        source_archive=archive_path,
    )
    assert report["source_verification"]["method"] == "pinned_codeload_archive"
    assert report["source_verification"]["archive_sha256"] == hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (root / "registration-form" / "main" / "pdfs" / "a.pdf").write_bytes(b"changed")
    with pytest.raises(DatasetError, match="differs from pinned archive"):
        build_vrdu_cohort(
            root,
            tmp_path / "another-output",
            quotas={"registration-form": 1, "ad-buy-form": 1},
            source_archive=archive_path,
        )

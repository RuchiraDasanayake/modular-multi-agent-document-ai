"""Synthetic-only first-PDF worker and supervisor checks; no selected sources."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from product_eval.table_crop_geometry import table_crop_from_proposal
from product_eval.tatr_cell_compat import load_official_cell_functions
from product_eval.tatr_first_pdf_runner import (
    _frozen_volumes,
    _validate_output_path,
    _verify_trial_gate,
    _verify_worker_result,
    resource_violation,
)
from product_eval.tatr_first_pdf_worker import (
    MissingOcrRoute,
    parse_native_page,
    run_document,
)
from product_eval.tatr_native_geometry import native_word_tokens


def _synthetic_pdf(path: Path, *, with_words: bool,
                   rotation: int = 0, crop: bool = False) -> None:
    pypdf = pytest.importorskip("pypdf")
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    stream = DecodedStreamObject()
    if with_words:
        stream.set_data(
            b"BT /F1 14 Tf 40 120 Td (Left) Tj ET "
            b"BT /F1 14 Tf 160 120 Td (Right) Tj ET"
        )
    else:
        stream.set_data(b"")
    page[NameObject("/Contents")] = writer._add_object(stream)
    if crop:
        page.cropbox.lower_left = (20, 15)
        page.cropbox.upper_right = (280, 180)
    if rotation:
        page.rotate(rotation)
    with path.open("wb") as destination:
        writer.write(destination)


@pytest.fixture(scope="module")
def official():
    root = Path(os.environ.get("TATR_ASSET_STAGE", r"I:\DocAI-Benchmarks\tatr-adbuy12-runtime-v1-stage"))
    if not root.exists():
        pytest.skip("pinned TATR asset stage absent")
    return load_official_cell_functions(root)


def test_resource_boundaries_are_fail_closed() -> None:
    gib = 1024**3
    good = {"available_ram": 6 * gib, "host_disk_free": 4 * gib,
            "data_disk_free": 4 * gib, "tree_rss": 8 * gib}
    assert resource_violation(**good, before_worker=True) is None
    assert resource_violation(**good, before_worker=False) is None
    assert resource_violation(**{**good, "available_ram": 6 * gib - 1},
                              before_worker=True) == "host_ram_floor"
    assert resource_violation(**{**good, "available_ram": 3 * gib - 1},
                              before_worker=False) == "host_ram_floor"
    assert resource_violation(**{**good, "host_disk_free": 4 * gib - 1},
                              before_worker=False) == "host_disk_floor"
    assert resource_violation(**{**good, "data_disk_free": 4 * gib - 1},
                              before_worker=False) == "data_disk_floor"
    assert resource_violation(**{**good, "tree_rss": 8 * gib + 1},
                              before_worker=False) == "process_tree_rss_ceiling"


def test_trial_volume_roots_are_bound_to_actual_host_and_output_drives() -> None:
    if not Path("I:/").is_dir():
        pytest.skip("frozen I: data disk is unavailable")
    paths = (Path("C:/repo"), Path("I:/cpu/python.exe"), Path("I:/ocr/python.exe"),
             Path("I:/trial"), Path("C:/"), Path("I:/"))
    volumes = _frozen_volumes(*paths)
    assert volumes["host_root"].drive.upper() == "C:"
    assert volumes["data_root"].drive.upper() == "I:"
    assert isinstance(volumes["host_volume_id"], int)
    with pytest.raises(ValueError, match="frozen C:/I:"):
        _frozen_volumes(*paths[:3], Path("C:/trial"), *paths[4:])
    with pytest.raises(ValueError, match="frozen C:/I:"):
        _frozen_volumes(*paths[:4], Path("I:/"), Path("I:/"))


def test_document_inference_requires_separate_source_and_code_bound_gate(
    tmp_path: Path,
) -> None:
    from product_eval.tatr_asset_preflight import sha256_file

    files = {name: tmp_path / name for name in
             ("selection", "cohort", "cpu_lock", "ocr_lock", "gate.json")}
    for name, path in files.items():
        if name != "gate.json":
            path.write_text(name, encoding="utf-8")
    code = {"source_sha256": {"runner.py": "a" * 64}}
    gate = {
        "version": 1, "scope": "one_first_pdf_research_trial",
        "document_inference_permitted": True,
        "max_documents": 1, "gold_access_permitted": False,
        "selection_sha256": sha256_file(files["selection"]),
        "cohort_sha256": sha256_file(files["cohort"]),
        "cpu_runtime_lock_sha256": sha256_file(files["cpu_lock"]),
        "ocr_runtime_lock_sha256": sha256_file(files["ocr_lock"]),
        "code_source_sha256": code["source_sha256"],
    }
    gate_path = files["gate.json"]
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    args = {"code_provenance": code, "selection": files["selection"],
            "cohort": files["cohort"], "cpu_lock": files["cpu_lock"],
            "ocr_lock": files["ocr_lock"]}
    assert _verify_trial_gate(gate_path, **args)["max_documents"] == 1
    changed_code = {"source_sha256": {"runner.py": "b" * 64}}
    with pytest.raises(ValueError, match="research inference gate"):
        _verify_trial_gate(gate_path, **{**args, "code_provenance": changed_code})
    gate["gold_access_permitted"] = True
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    with pytest.raises(ValueError, match="research inference gate"):
        _verify_trial_gate(gate_path, **args)


def test_output_must_be_new_and_outside_inputs(tmp_path: Path) -> None:
    repo, corpus, assets, data = (tmp_path / name for name in
                                  ("repo", "corpus", "assets", "data"))
    for root in (repo, corpus, assets, data):
        root.mkdir()
    _validate_output_path(data / "new", repo, corpus, assets, data)
    (data / "used").mkdir()
    with pytest.raises(ValueError, match="already exists"):
        _validate_output_path(data / "used", repo, corpus, assets, data)
    with pytest.raises(ValueError, match="data disk"):
        _validate_output_path(repo / "new", repo, corpus, assets, data)


def test_empty_native_page_stops_before_detector(tmp_path: Path, official) -> None:
    pdfium = pytest.importorskip("pypdfium2")
    source = tmp_path / "blank.pdf"
    _synthetic_pdf(source, with_words=False)
    pdf = pdfium.PdfDocument(source)
    try:
        page = pdf[0]
        bitmap = page.render(scale=300 / 72)
        try:
            def must_not_infer(_image, _kind):
                raise AssertionError("image-only page reached model inference")

            with pytest.raises(MissingOcrRoute, match="no valid PDFium words"):
                parse_native_page(page, bitmap, 1, must_not_infer, official)
        finally:
            bitmap.close()
            page.close()
    finally:
        pdf.close()


def test_synthetic_pdf_cells_keep_source_pixels_and_require_review(tmp_path: Path, official) -> None:
    pdfium = pytest.importorskip("pypdfium2")
    from product_eval.tatr_asset_preflight import sha256_file

    source = tmp_path / "two_words.pdf"
    output = tmp_path / "output"
    output.mkdir()
    _synthetic_pdf(source, with_words=True)
    pdf = pdfium.PdfDocument(source)
    try:
        page = pdf[0]
        bitmap = page.render(scale=300 / 72)
        try:
            words = native_word_tokens(page, bitmap)
            assert [word.text for word in words] == ["Left", "Right"]
            x0 = min(word.bbox[0] for word in words) - 10
            y0 = min(word.bbox[1] for word in words) - 10
            x1 = max(word.bbox[2] for word in words) + 10
            y1 = max(word.bbox[3] for word in words) + 10
            proposal = (x0, y0, x1, y1)
            crop = table_crop_from_proposal(proposal, (bitmap.width, bitmap.height))
            split = (words[0].bbox[2] + words[1].bbox[0]) / 2 - crop.raster_box[0]
        finally:
            bitmap.close()
            page.close()
    finally:
        pdf.close()

    def object_row(label: str, box: tuple[float, float, float, float]) -> dict:
        return {"label": label, "score": 0.9, "bbox": box}

    def infer(image, kind):
        if kind == "detection":
            return [{"label": "table", "score": 0.9,
                     "bbox": proposal, "query_index": 0,
                     "above_frozen_threshold": True}]
        width, height = image.size
        assert (width, height) == crop.size
        return [
            object_row("table", (0, 0, width, height)),
            object_row("table row", (0, 0, width, height)),
            object_row("table column", (0, 0, split, height)),
            object_row("table column", (split, 0, width, height)),
        ]

    def unexpected_ocr(_image, _page_number):
        raise AssertionError("native words must suppress full-page OCR")

    receipt = run_document(source, sha256_file(source), output, infer, official,
                           unexpected_ocr)
    assert receipt["status"] == "first_pdf_needs_visual_review"
    assert receipt["gold_opened"] is False
    assert receipt["can_continue_other_11"] is False
    assert receipt["nonempty_cell_count"] >= 1
    parsed = json.loads((output / "parsed_document.json").read_text(encoding="utf-8"))
    assert parsed["contract_version"] == 2
    assert parsed["tables"]
    assert any(cell["text"] for table in parsed["tables"] for cell in table["cells"])
    assert (output / "first_nonempty_source_overlay.png").is_file()
    runtime_lock = output / "expected_lock.json"
    runtime_lock.write_text("{}\n", encoding="utf-8")
    manifest = output / "runtime_manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    (output / "startup.ready.json").write_text(json.dumps({
        "status": "models_loaded_offline", "pdf_opened": False,
        "runtime_lock_sha256": sha256_file(runtime_lock),
        "runtime_manifest_sha256": sha256_file(manifest),
    }), encoding="utf-8")
    (output / "worker_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    _verify_worker_result(output, sha256_file(source), runtime_lock)
    parsed_path = output / "parsed_document.json"
    receipt_path = output / "worker_receipt.json"
    parsed_bytes = parsed_path.read_bytes()
    altered = json.loads(parsed_bytes)
    altered["tables"] = []
    parsed_path.write_text(json.dumps(altered), encoding="utf-8")
    receipt["parsed_document_sha256"] = sha256_file(parsed_path)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="counts disagree"):
        _verify_worker_result(output, sha256_file(source), runtime_lock)
    parsed_path.write_bytes(parsed_bytes)
    receipt["parsed_document_sha256"] = sha256_file(parsed_path)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    overlay_path = output / "first_nonempty_source_overlay.png"
    overlay_bytes = overlay_path.read_bytes()
    overlay_path.write_bytes(b"not a PNG")
    receipt["overlay_sha256"] = sha256_file(overlay_path)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="parser artifact is malformed"):
        _verify_worker_result(output, sha256_file(source), runtime_lock)
    overlay_path.write_bytes(overlay_bytes)
    receipt["overlay_sha256"] = sha256_file(overlay_path)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    (output / "first_nonempty_source_overlay.png").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="artifact changed"):
        _verify_worker_result(output, sha256_file(source), runtime_lock)


def test_rotated_detector_crop_retains_source_page_cell_box(tmp_path: Path, official) -> None:
    pdfium = pytest.importorskip("pypdfium2")
    source = tmp_path / "rotated_table_proposal.pdf"
    _synthetic_pdf(source, with_words=True)
    pdf = pdfium.PdfDocument(source)
    try:
        page = pdf[0]
        bitmap = page.render(scale=300 / 72)
        try:
            words = native_word_tokens(page, bitmap)
            proposal = (
                min(word.bbox[0] for word in words) - 10,
                min(word.bbox[1] for word in words) - 10,
                max(word.bbox[2] for word in words) + 10,
                max(word.bbox[3] for word in words) + 10,
            )

            def infer(image, kind):
                if kind == "detection":
                    return [{"label": "table rotated", "score": 0.9,
                             "bbox": proposal, "query_index": 0,
                             "above_frozen_threshold": True}]
                width, height = image.size
                return [{"label": label, "score": 0.9,
                         "bbox": (0, 0, width, height)}
                        for label in ("table", "table row", "table column")]

            _, tables, detail = parse_native_page(page, bitmap, 1, infer, official)
            assert detail["tables"][0]["rotated_clockwise"] is True
            assert len(tables) == 1
            assert tables[0].cells[0].text == "Left Right"
            box = tables[0].cells[0].anchors[0].display_box
            assert box is not None
            assert 0 <= box.x0 < box.x1 <= 1
            assert 0 <= box.y0 < box.y1 <= 1
        finally:
            bitmap.close()
            page.close()
    finally:
        pdf.close()


def test_cropped_rotated_pdf_raw_boxes_have_explicit_transform_metadata(
    tmp_path: Path, official,
) -> None:
    pdfium = pytest.importorskip("pypdfium2")
    from product_eval.tatr_asset_preflight import sha256_file
    from product_eval.tatr_native_geometry import page_box_to_pixels

    source = tmp_path / "cropped_rotated.pdf"
    output = tmp_path / "output"
    output.mkdir()
    _synthetic_pdf(source, with_words=True, rotation=90, crop=True)
    pdf = pdfium.PdfDocument(source)
    try:
        page = pdf[0]
        bitmap = page.render(scale=300 / 72)
        try:
            words = native_word_tokens(page, bitmap)
            assert [word.text for word in words] == ["Left", "Right"]
            proposal = (
                min(word.bbox[0] for word in words) - 10,
                min(word.bbox[1] for word in words) - 10,
                max(word.bbox[2] for word in words) + 10,
                max(word.bbox[3] for word in words) + 10,
            )
            view_width, _ = page.get_size()
            assert max(word.pdf_bbox[2] for word in words) > view_width
        finally:
            bitmap.close()
            page.close()
    finally:
        pdf.close()


    def infer(image, kind):
        if kind == "detection":
            return [{"label": "table", "score": 0.9, "bbox": proposal,
                     "query_index": 0, "above_frozen_threshold": True}]
        width, height = image.size
        return [{"label": label, "score": 0.9,
                 "bbox": (0, 0, width, height)}
                for label in ("table", "table row", "table column")]

    run_document(source, sha256_file(source), output, infer, official)
    parsed = json.loads((output / "parsed_document.json").read_text(encoding="utf-8"))
    detail = json.loads((output / "raw_pages.json").read_text(encoding="utf-8"))[0]
    assert parsed["units"][0]["width"] is None
    assert parsed["units"][0]["height"] is None
    assert detail["pdf_rotation_degrees"] == 90
    assert detail["pdf_page_size_frame"] == "cropbox_after_rotation"
    assert detail["pdf_cropbox_points"] == [20.0, 15.0, 280.0, 180.0]
    assert detail["pdf_mediabox_points"] == [0.0, 0.0, 300.0, 200.0]

    pdf = pdfium.PdfDocument(source)
    try:
        page = pdf[0]
        bitmap = page.render(scale=300 / 72)
        try:
            converter = bitmap.get_posconv(page)
            cells = parsed["tables"][0]["cells"]
            assert any(cell["text"] for cell in cells)
            for cell in cells:
                anchor = cell["anchors"][0]
                raw = anchor["raw_box"]
                display = anchor["display_box"]
                assert raw["space"] == "pdf_points_bottom_left"
                assert display["space"] == "normalized_top_left"
                projected = page_box_to_pixels(
                    (raw["x0"], raw["y0"], raw["x1"], raw["y1"]),
                    converter, bitmap.width, bitmap.height,
                )
                normalized = (display["x0"] * bitmap.width,
                              display["y0"] * bitmap.height,
                              display["x1"] * bitmap.width,
                              display["y1"] * bitmap.height)
                assert all(abs(left - right) <= 1.01 for left, right in
                           zip(projected, normalized, strict=True))
        finally:
            bitmap.close()
            page.close()
    finally:
        pdf.close()


def test_table_anchor_encloses_cells_refined_beyond_structure_query(
    tmp_path: Path, official,
) -> None:
    pdfium = pytest.importorskip("pypdfium2")
    source = tmp_path / "refined_cells.pdf"
    _synthetic_pdf(source, with_words=True)
    pdf = pdfium.PdfDocument(source)
    try:
        page = pdf[0]
        bitmap = page.render(scale=300 / 72)
        try:
            words = native_word_tokens(page, bitmap)
            proposal = (
                min(word.bbox[0] for word in words) - 10,
                min(word.bbox[1] for word in words) - 10,
                max(word.bbox[2] for word in words) + 10,
                max(word.bbox[3] for word in words) + 10,
            )

            def infer(image, kind):
                if kind == "detection":
                    return [{"label": "table", "score": 0.9,
                             "bbox": proposal, "query_index": 0,
                             "above_frozen_threshold": True}]
                width, height = image.size
                return [
                    {"label": "table", "score": 0.9,
                     "bbox": (0, 0, width / 2, height)},
                    {"label": "table row", "score": 0.9,
                     "bbox": (0, 0, width, height)},
                    {"label": "table column", "score": 0.9,
                     "bbox": (0, 0, width, height)},
                ]

            _, tables, detail = parse_native_page(page, bitmap, 1, infer, official)
            assert len(tables) == 1
            assert any(cell.text.strip() for cell in tables[0].cells)
            raw_structure = detail["tables"][0]["raw_structure_table_page_pixel_box"]
            emitted = detail["tables"][0]["emitted_table_page_pixel_box"]
            assert emitted[2] > raw_structure[2]
            outer = tables[0].anchors[0].display_box
            assert outer is not None
            for cell in tables[0].cells:
                inner = cell.anchors[0].display_box
                assert inner is not None
                assert outer.x0 <= inner.x0 < inner.x1 <= outer.x1
                assert outer.y0 <= inner.y0 < inner.y1 <= outer.y1
        finally:
            bitmap.close()
            page.close()
    finally:
        pdf.close()

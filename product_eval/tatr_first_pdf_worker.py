"""One-document, native-text-only Table Transformer research worker.

The supervisor starts this module in the pinned CPU environment. It contains no
gold reader and never substitutes OCR text. A page without valid PDFium words
fails the document until the separate OCR geometry route is reviewed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import numbers
import os
import sys
import traceback
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from idpo.product_auto.parsed_document import (
    Box,
    ParsedDocument,
    SourceAnchor,
    SourceUnit,
    Table,
    TableCell,
)
from product_eval.table_crop_geometry import (
    crop_box_to_page_pixels,
    crop_box_to_pdf_page,
    page_word_to_crop,
    table_crop_from_proposal,
)
from product_eval.tatr_asset_preflight import sha256_file
from product_eval.tatr_cell_compat import (
    cells_from_synthetic_objects,
    load_official_cell_functions,
)
from product_eval.tatr_cpu_runtime_receipt import (
    UNUSED_DETECTION_BUFFERS,
    _runtime_lock,
)
from product_eval.tatr_native_geometry import (
    GeometryError,
    WordToken,
    native_word_tokens,
    page_box_to_pixels,
)
from product_eval.tatr_output_adapter import CLASS_LABELS, adapt_detr_outputs

DPI = 300
MAX_PAGES = 20
MAX_FILE_BYTES = 2_000_000
MAX_RENDER_PIXELS = 35_000_000
MAX_DETECTED_TABLES_PER_PAGE = 20
PARSER_ID = "table-transformer-detection+v1.1-all-pinned-cell-functions"
PARSER_VERSION = "research-native-first-pdf-v1"


class MissingOcrRoute(RuntimeError):
    """The page needs OCR, whose word geometry has not passed integration review."""


def _write_new_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")


def _as_box(values: Any) -> tuple[float, float, float, float]:
    if (not isinstance(values, (tuple, list)) or len(values) != 4
            or any(not isinstance(value, numbers.Real) or isinstance(value, bool)
                   for value in values)):
        raise GeometryError("model box must contain four coordinates")
    box = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in box):
        raise GeometryError("model box contains a nonfinite coordinate")
    if box[0] >= box[2] or box[1] >= box[3]:
        raise GeometryError("model box has no area")
    return box


def _source_anchor(
    unit_id: str,
    pixel_box: tuple[float, float, float, float],
    pdf_box: tuple[float, float, float, float],
    image_size: tuple[int, int],
) -> SourceAnchor:
    width, height = image_size
    return SourceAnchor(
        unit_id=unit_id,
        raw_box=Box(*pdf_box, space="pdf_points_bottom_left"),
        display_box=Box(
            pixel_box[0] / width, pixel_box[1] / height,
            pixel_box[2] / width, pixel_box[3] / height,
            space="normalized_top_left",
        ),
    )


def _check_source_reprojection(
    pixel_box: tuple[float, float, float, float],
    pdf_box: tuple[float, float, float, float],
    converter: Any,
    image_size: tuple[int, int],
) -> None:
    roundtrip = page_box_to_pixels(pdf_box, converter, *image_size)
    if max(abs(original - mapped) for original, mapped in zip(pixel_box, roundtrip, strict=True)) > 1.01:
        raise GeometryError("source-page box does not round-trip to rendered pixels")


def _contiguous_span(indexes: Any, label: str) -> tuple[int, int]:
    if (not isinstance(indexes, list) or not indexes
            or any(type(index) is not int or index < 0 for index in indexes)):
        raise ValueError(f"invalid TATR {label} indexes")
    ordered = sorted(indexes)
    if ordered != list(range(ordered[0], ordered[-1] + 1)):
        raise ValueError(f"noncontiguous TATR {label} span")
    return ordered[0], len(ordered)


def _active_tables(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in objects:
        score = item["score"]
        if (not isinstance(score, numbers.Real) or isinstance(score, bool)
                or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError("detector query has invalid probability")
        if item["label"] in {"table", "table rotated"} and (
            item["above_frozen_threshold"] != (score >= 0.5)
        ):
            raise ValueError("detector threshold flag differs from frozen 0.5 profile")
    active = [item for item in objects if item["label"] in {"table", "table rotated"}
              and item["above_frozen_threshold"]]
    if len(active) > MAX_DETECTED_TABLES_PER_PAGE:
        raise ValueError("detector exceeded the frozen table-per-page safety limit")
    return sorted(active, key=lambda item: int(item["query_index"]))


def parse_native_page(
    page: Any,
    bitmap: Any,
    page_number: int,
    infer: Callable[[Any, str], list[dict[str, Any]]],
    official: Any,
) -> tuple[SourceUnit, list[Table], dict[str, Any]]:
    """Project one real PDF page through detector, structure and cell adapters."""
    from PIL import Image

    image_size = (bitmap.width, bitmap.height)
    if bitmap.width * bitmap.height > MAX_RENDER_PIXELS:
        raise ValueError("rendered page exceeds the frozen pixel limit")
    words = native_word_tokens(page, bitmap)
    if not words:
        raise MissingOcrRoute(f"page {page_number} has no valid PDFium words")
    source_text = " ".join(word.text for word in words)
    unit_id = f"page-{page_number}"
    page_width, page_height = page.get_size()
    # PDFium's raw PDF boxes use the unrotated page coordinate system, while
    # get_size() applies CropBox and page rotation. The v2 unit has no origin
    # or rotation fields, so dimensions here would misdescribe raw_box. Keep
    # the complete page transform in raw_pages.json and the rendered overlay.
    unit = SourceUnit(unit_id, "pdf_page", page_number - 1, source_text)
    page_image = bitmap.to_pil().convert("RGB")
    raw_detection = infer(page_image, "detection")
    active = _active_tables(raw_detection)
    converter = bitmap.get_posconv(page)
    tables: list[Table] = []
    detail: dict[str, Any] = {
        "page_number": page_number,
        "rendered_size_pixels": image_size,
        "pdf_page_size_points": [page_width, page_height],
        "pdf_page_size_frame": "cropbox_after_rotation",
        "pdf_cropbox_points": list(page.get_cropbox()),
        "pdf_mediabox_points": list(page.get_mediabox()),
        "pdf_rotation_degrees": page.get_rotation(),
        "word_route": "pdfium_native",
        "native_words": [asdict(word) for word in words],
        "raw_detection_queries": raw_detection,
        "tables": [],
    }
    for table_number, detected in enumerate(active, 1):
        rotated = detected["label"] == "table rotated"
        crop = table_crop_from_proposal(_as_box(detected["bbox"]), image_size, padding=5)
        crop_image = page_image.crop(crop.raster_box)
        if rotated:
            crop_image = crop_image.rotate(270, expand=True, resample=Image.Resampling.BICUBIC)
        crop_words: list[WordToken] = []
        for word in words:
            local_box = page_word_to_crop(crop, word.bbox, rotated_clockwise=rotated)
            if local_box is not None:
                crop_words.append(replace(word, bbox=local_box))
        raw_structure = infer(crop_image, "structure")
        cell_result = cells_from_synthetic_objects(
            official, raw_structure, crop_words, crop_image.size,
        )
        structure_tables = [item for item in raw_structure
                            if item["label"] == "table" and item["score"] >= 0.5]
        if len(structure_tables) != 1:
            raise ValueError("structure model lacks one frozen table box")
        structure_table_box = _as_box(structure_tables[0]["bbox"])
        raw_table_pixel_box = crop_box_to_page_pixels(
            crop, structure_table_box, rotated_clockwise=rotated,
        )
        raw_table_pdf_box = crop_box_to_pdf_page(
            crop, structure_table_box, converter, rotated_clockwise=rotated,
        )
        _check_source_reprojection(raw_table_pixel_box, raw_table_pdf_box,
                                   converter, image_size)
        table_id = f"p{page_number}-t{table_number}"
        cells: list[TableCell] = []
        cell_details: list[dict[str, Any]] = []
        for raw_cell in cell_result.cells:
            row, row_span = _contiguous_span(raw_cell["row_nums"], "row")
            column, column_span = _contiguous_span(raw_cell["column_nums"], "column")
            local_box = _as_box(raw_cell["bbox"])
            pixel_box = crop_box_to_page_pixels(crop, local_box, rotated_clockwise=rotated)
            pdf_box = crop_box_to_pdf_page(crop, local_box, converter,
                                           rotated_clockwise=rotated)
            _check_source_reprojection(pixel_box, pdf_box, converter, image_size)
            text = raw_cell["cell text"]
            if not isinstance(text, str):
                raise TypeError("TATR cell text is not a string")
            if text and not raw_cell["spans"]:
                raise ValueError("nonempty TATR cell lacks source word spans")
            cells.append(TableCell(
                row, column, text, row_span, column_span,
                anchors=(_source_anchor(unit_id, pixel_box, pdf_box, image_size),),
            ))
            cell_details.append({
                "row": row, "column": column, "row_span": row_span,
                "column_span": column_span, "text": text,
                "source_token_ids": [span["source_token_id"] for span in raw_cell["spans"]],
                "local_box": local_box, "page_pixel_box": pixel_box,
                "pdf_page_box": pdf_box,
            })
        if not cell_details:
            raise ValueError("structure model produced no source-anchored cells")
        table_pixel_box = (
            min(item["page_pixel_box"][0] for item in cell_details),
            min(item["page_pixel_box"][1] for item in cell_details),
            max(item["page_pixel_box"][2] for item in cell_details),
            max(item["page_pixel_box"][3] for item in cell_details),
        )
        table_pdf_box = (
            min(item["pdf_page_box"][0] for item in cell_details),
            min(item["pdf_page_box"][1] for item in cell_details),
            max(item["pdf_page_box"][2] for item in cell_details),
            max(item["pdf_page_box"][3] for item in cell_details),
        )
        _check_source_reprojection(table_pixel_box, table_pdf_box, converter, image_size)
        tables.append(Table(table_id, tuple(cells), anchors=(
            _source_anchor(unit_id, table_pixel_box, table_pdf_box, image_size),
        )))
        detail["tables"].append({
            "table_id": table_id, "detector_query": detected,
            "raw_structure_table_crop_box": structure_table_box,
            "raw_structure_table_page_pixel_box": raw_table_pixel_box,
            "raw_structure_table_pdf_page_box": raw_table_pdf_box,
            "emitted_table_page_pixel_box": table_pixel_box,
            "emitted_table_pdf_page_box": table_pdf_box,
            "crop": asdict(crop), "rotated_clockwise": rotated,
            "crop_word_count": len(crop_words),
            "raw_structure_queries": raw_structure,
            "cell_confidence_unvalidated": cell_result.confidence_score,
            "unassigned_token_ids": cell_result.unassigned_token_ids,
            "cells": cell_details,
        })
    return unit, tables, detail


class PinnedCpuModels:
    """Offline safetensors only; one worker loads each checkpoint once."""

    def __init__(self, asset_root: Path) -> None:
        import torch
        from transformers import (
            DetrImageProcessor,
            TableTransformerConfig,
            TableTransformerForObjectDetection,
        )

        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        self._torch = torch
        self._processors: dict[str, Any] = {}
        self._models: dict[str, Any] = {}
        for kind in ("detection", "structure"):
            model_root = asset_root / kind
            config = TableTransformerConfig.from_pretrained(model_root, local_files_only=True)
            config.use_pretrained_backbone = False
            if tuple(config.id2label[index] for index in range(len(CLASS_LABELS[kind]))) != CLASS_LABELS[kind]:
                raise ValueError(f"pinned {kind} class map changed")
            model, loading = TableTransformerForObjectDetection.from_pretrained(
                model_root, config=config, local_files_only=True, use_safetensors=True,
                trust_remote_code=False, output_loading_info=True,
            )
            allowed = UNUSED_DETECTION_BUFFERS if kind == "detection" else set()
            if (loading["missing_keys"] or loading.get("mismatched_keys")
                    or set(loading["unexpected_keys"]) != allowed):
                raise ValueError(f"pinned {kind} safetensors have a load mismatch")
            self._models[kind] = model.eval().to("cpu")
            self._processors[kind] = DetrImageProcessor.from_pretrained(
                model_root, local_files_only=True,
            )

    def __call__(self, image: Any, kind: str) -> list[dict[str, Any]]:
        from PIL import Image

        if kind not in self._models:
            raise ValueError("unknown pinned TATR model kind")
        longest = 800 if kind == "detection" else 1000
        scale = longest / max(image.size)
        size = {"width": round(image.width * scale), "height": round(image.height * scale)}
        inputs = self._processors[kind](
            image, size=size, resample=Image.Resampling.BICUBIC, return_tensors="pt",
        )
        with self._torch.inference_mode():
            output = self._models[kind](**inputs)
        return adapt_detr_outputs(
            output.logits[0].tolist(), output.pred_boxes[0].tolist(), image.size,
            model_kind=kind,
        )


def _overlay_first_nonempty(
    source_bytes: bytes, document: ParsedDocument, output_dir: Path,
) -> tuple[Path, Path]:
    """Reopen the source and render a separate 300-DPI source-pixel overlay."""
    import pypdfium2 as pdfium
    from PIL import ImageDraw, ImageFont

    for table in document.tables:
        if not any(cell.text.strip() for cell in table.cells):
            continue
        first = table.anchors[0]
        page_number = int(first.unit_id.split("-")[1])
        pdf = pdfium.PdfDocument(source_bytes)
        try:
            page = pdf[page_number - 1]
            bitmap = page.render(scale=DPI / 72, rotation=0)
            try:
                image = bitmap.to_pil().convert("RGB")
                draw = ImageDraw.Draw(image)
                font = ImageFont.load_default(size=18)
                legend: list[dict[str, Any]] = []
                for cell in table.cells:
                    anchor = cell.anchors[0]
                    box = anchor.display_box
                    if box is None:
                        raise ValueError("cell lacks a page-pixel display box")
                    draw.rectangle((box.x0 * image.width, box.y0 * image.height,
                                    box.x1 * image.width, box.y1 * image.height),
                                   outline="red", width=3)
                    label = f"{table.table_id}:r{cell.row}c{cell.column}"
                    text_box = draw.textbbox((0, 0), label, font=font)
                    tag_width = text_box[2] - text_box[0] + 8
                    tag_height = text_box[3] - text_box[1] + 8
                    tag_x = min(int(box.x0 * image.width), image.width - tag_width)
                    tag_y = max(0, int(box.y0 * image.height) - tag_height)
                    draw.rectangle((tag_x, tag_y, tag_x + tag_width,
                                    tag_y + tag_height), fill="white", outline="red")
                    draw.text((tag_x + 4, tag_y + 4 - text_box[1]), label,
                              fill="red", font=font)
                    legend.append({
                        "label": label, "table_id": table.table_id,
                        "row": cell.row, "column": cell.column,
                        "text": cell.text, "display_box": asdict(box),
                    })
                path = output_dir / "first_nonempty_source_overlay.png"
                legend_path = output_dir / "first_nonempty_source_overlay_legend.json"
                image.save(path)
                _write_new_json(legend_path, {
                    "source_sha256": document.source_sha256,
                    "page_number": page_number,
                    "table_id": table.table_id,
                    "cells": legend,
                })
                return path, legend_path
            finally:
                bitmap.close()
                page.close()
        finally:
            pdf.close()
    raise ValueError("first PDF produced no nonempty table cell for source overlay")


def run_document(
    source: Path, expected_sha256: str, output_dir: Path,
    infer: Callable[[Any, str], list[dict[str, Any]]], official: Any,
) -> dict[str, Any]:
    import pypdfium2 as pdfium

    source_bytes = source.read_bytes()
    if len(source_bytes) > MAX_FILE_BYTES or hashlib.sha256(source_bytes).hexdigest() != expected_sha256:
        raise ValueError("source exceeds frozen limit or differs from the selection hash")
    pdf = pdfium.PdfDocument(source_bytes)
    units: list[SourceUnit] = []
    tables: list[Table] = []
    pages: list[dict[str, Any]] = []
    try:
        if not 1 <= len(pdf) <= MAX_PAGES:
            raise ValueError("PDF page count exceeds frozen limit")
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                width, height = page.get_size()
                scale = DPI / 72
                if width * height * scale * scale > MAX_RENDER_PIXELS:
                    raise ValueError("page would exceed frozen 300-DPI pixel limit")
                bitmap = page.render(scale=scale, rotation=0)
                try:
                    unit, page_tables, detail = parse_native_page(
                        page, bitmap, index + 1, infer, official,
                    )
                    units.append(unit)
                    tables.extend(page_tables)
                    pages.append(detail)
                finally:
                    bitmap.close()
            finally:
                page.close()
    finally:
        pdf.close()
    document = ParsedDocument(
        expected_sha256, "pdf", PARSER_ID, PARSER_VERSION,
        tuple(units), tuple(tables),
    )
    _write_new_json(output_dir / "parsed_document.json", document.to_dict())
    _write_new_json(output_dir / "raw_pages.json", pages)
    overlay, legend = _overlay_first_nonempty(source_bytes, document, output_dir)
    return {
        "status": "first_pdf_needs_visual_review",
        "source_sha256": expected_sha256,
        "page_count": len(units), "table_count": len(tables),
        "cell_count": sum(len(table.cells) for table in tables),
        "nonempty_cell_count": sum(bool(cell.text.strip()) for table in tables for cell in table.cells),
        "parsed_document_sha256": sha256_file(output_dir / "parsed_document.json"),
        "raw_pages_sha256": sha256_file(output_dir / "raw_pages.json"),
        "overlay_sha256": sha256_file(overlay),
        "overlay_file": overlay.name,
        "overlay_legend_sha256": sha256_file(legend),
        "overlay_legend_file": legend.name,
        "manual_source_pixel_verdict": "pending",
        "can_continue_other_11": False,
        "gold_opened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--tokenizers-sdist", type=Path, required=True)
    parser.add_argument("--torchvision-wheel", type=Path, required=True)
    parser.add_argument("--expected-runtime-lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    os.environ.update({
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1", "OMP_NUM_THREADS": "4",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    sys.dont_write_bytecode = True
    try:
        lock = _runtime_lock(args.asset_root, args.tokenizers_sdist,
                             args.torchvision_wheel)
        if lock != json.loads(args.expected_runtime_lock.read_text(encoding="utf-8")):
            raise ValueError("installed TATR CPU runtime differs from committed lock")
        _write_new_json(args.output_dir / "runtime_manifest.json", lock)
        official = load_official_cell_functions(args.asset_root)
        models = PinnedCpuModels(args.asset_root)
        _write_new_json(args.output_dir / "startup.ready.json", {
            "status": "models_loaded_offline",
            "runtime_lock_sha256": sha256_file(args.expected_runtime_lock),
            "runtime_manifest_sha256": sha256_file(args.output_dir / "runtime_manifest.json"),
            "asset_root": str(args.asset_root.resolve(strict=True)),
            "pdf_opened": False,
        })
        receipt = run_document(args.source, args.source_sha256, args.output_dir,
                               models, official)
        _write_new_json(args.output_dir / "worker_receipt.json", receipt)
    except Exception as exc:
        _write_new_json(args.output_dir / "worker_failure.json", {
            "status": "failed", "error_type": type(exc).__name__,
            "message": str(exc), "traceback": traceback.format_exc(),
            "gold_opened": False,
        })
        raise


if __name__ == "__main__":
    main()

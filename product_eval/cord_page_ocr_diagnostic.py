"""Source-locked, paired full-page OCR diagnostic on 60 CORD development PNGs.

This runner is not a product adapter. It retains original-pixel OCR geometry and
tests the existing deterministic extraction logic on each page string, without
using gold to propose a schema or reading the 40 reserved receipt images.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import subprocess
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from importlib import metadata, util
from pathlib import Path
from typing import Any

from PIL import Image

from product_eval.cord_word_ocr_diagnostic import (
    DEVELOPMENT_COHORT_SHA256,
    EXPECTED_ANNOTATED_BOXES,
    FROZEN_CROP_MANIFEST_SHA256,
    TESSERACT_ENG_SHA256,
    TESSERACT_EXE_SHA256,
    _development_sources,
    _read_jsonl,
    load_manifest,
    sha256_file,
)
from product_eval.datasets.cord_positive_score import score_cord_positive

DEVELOPMENT_GOLD_SHA256 = "84a097116eaad75fb66265447d1b831f5a2ffa98792e10e9ad7edb517cb8e318"
RESERVED_COHORT_SHA256 = "06d0bcfb05734557c54b85a9d7c0536008d9393a14012a1c7d01ab6e3058647e"
DET_SHA256 = "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f"
REC_SHA256 = "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884"
CLS_SHA256 = "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c"
BOOTSTRAP_SEED = 20261012
BOOTSTRAP_REPLICATES = 10000


def normalized_tokens(value: object) -> str:
    """A deliberately permissive string-presence proxy, not OCR transcription."""
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def contains_normalized(page_text: str, value: object) -> bool:
    target = normalized_tokens(value)
    return bool(target) and target in normalized_tokens(page_text)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (rank - low), 3)


def _bounded_error(exc: Exception) -> str:
    # Avoid leaking source paths or OCR text through exception messages.
    return type(exc).__name__


def _sample_rss(stop: threading.Event, process: Any, samples: list[int]) -> None:
    while not stop.is_set():
        try:
            samples.append(process.memory_info().rss)
        except Exception:  # noqa: BLE001 - process can exit between 20 ms samples
            break
        stop.wait(0.02)


def _rect_polygon(left: int, top: int, width: int, height: int) -> list[list[int]]:
    return [[left, top], [left + width, top], [left + width, top + height], [left, top + height]]


def _with_offsets(lines: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    parts: list[str] = []
    offset = 0
    for index, line in enumerate(lines):
        text = str(line["text"])
        if index:
            offset += 1
        line["raw_order"] = index
        line["start"] = offset
        line["end"] = offset + len(text)
        parts.append(text)
        offset += len(text)
    page_text = "\n".join(parts)
    if any(page_text[line["start"]:line["end"]] != line["text"] for line in lines):
        raise ValueError("OCR line offset integrity failed")
    by_position = sorted(range(len(lines)), key=lambda idx: (
        min(point[1] for point in lines[idx]["polygon"]),
        min(point[0] for point in lines[idx]["polygon"]), idx,
    ))
    for reading_order, index in enumerate(by_position):
        lines[index]["position_order"] = reading_order
    return page_text, lines


def parse_tesseract_tsv(tsv: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    reader = csv.DictReader(tsv.splitlines(), delimiter="\t")
    expected = {"level", "page_num", "block_num", "par_num", "line_num", "word_num",
                "left", "top", "width", "height", "conf", "text"}
    if reader.fieldnames is None or set(reader.fieldnames) != expected:
        raise ValueError("Tesseract TSV header differs from pinned contract")
    words: list[dict[str, Any]] = []
    grouped: dict[tuple[int, int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for item in reader:
        if item["level"] != "5" or not item["text"].strip():
            continue
        left, top, width, height = (int(item[name]) for name in ("left", "top", "width", "height"))
        if width <= 0 or height <= 0:
            continue
        confidence = float(item["conf"])
        hierarchy = tuple(int(item[name]) for name in ("page_num", "block_num", "par_num", "line_num"))
        word = {
            "text": item["text"], "confidence": confidence, "polygon": _rect_polygon(left, top, width, height),
            "hierarchy": list(hierarchy), "word_number": int(item["word_num"]), "raw_order": len(words),
        }
        words.append(word)
        grouped[hierarchy].append(word)
    lines: list[dict[str, Any]] = []
    for hierarchy, members in grouped.items():
        left = min(member["polygon"][0][0] for member in members)
        top = min(member["polygon"][0][1] for member in members)
        right = max(member["polygon"][2][0] for member in members)
        bottom = max(member["polygon"][2][1] for member in members)
        lines.append({
            "text": " ".join(member["text"] for member in members),
            "confidence": round(sum(member["confidence"] for member in members) / len(members), 3),
            "polygon": _rect_polygon(left, top, right - left, bottom - top),
            "hierarchy": list(hierarchy),
        })
    text, lines = _with_offsets(lines)
    return text, lines, words


def _tesseract_page(image_path: Path, executable: Path, tessdata: Path) -> dict[str, Any]:
    import psutil

    started = time.perf_counter()
    try:
        process = subprocess.Popen(
            [str(executable), str(image_path), "stdout", "-l", "eng", "--oem", "3", "--psm", "6",
             "--tessdata-dir", str(tessdata), "tsv"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "OMP_THREAD_LIMIT": "4"},
        )
    except OSError as exc:
        return {"text": "", "lines": [], "words": [], "failure": _bounded_error(exc),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), "peak_sampled_rss_bytes": 0}
    stop = threading.Event()
    samples: list[int] = []
    sampler = threading.Thread(target=_sample_rss, args=(stop, psutil.Process(process.pid), samples), daemon=True)
    sampler.start()
    try:
        stdout, _ = process.communicate(timeout=30)
        if process.returncode:
            failure = f"exit_{process.returncode}"
            text, lines, words = "", [], []
        else:
            text, lines, words = parse_tesseract_tsv(stdout.decode("utf-8", errors="replace"))
            failure = None
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        failure, text, lines, words = "timeout_30s", "", [], []
    except Exception as exc:  # noqa: BLE001 - preserve page failure in fixed denominator
        failure, text, lines, words = _bounded_error(exc), "", [], []
    finally:
        stop.set()
        sampler.join()
    return {"text": text, "lines": lines, "words": words, "failure": failure,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "peak_sampled_rss_bytes": max(samples, default=0)}


def _rapid_page(engine: Any, image_path: Path, worker: Any) -> dict[str, Any]:
    baseline = worker.memory_info().rss
    samples: list[int] = []
    stop = threading.Event()
    sampler = threading.Thread(target=_sample_rss, args=(stop, worker, samples), daemon=True)
    sampler.start()
    started = time.perf_counter()
    try:
        output = engine(str(image_path))
        texts = list(output.txts or ())
        scores = [float(score) for score in (output.scores or ())]
        boxes = output.boxes.tolist() if output.boxes is not None else []
        if not (len(texts) == len(scores) == len(boxes)):
            raise ValueError("RapidOCR text, score and box counts differ")
        lines = [
            {"text": str(text), "confidence": score,
             "polygon": [[float(x), float(y)] for x, y in box]}
            for text, score, box in zip(texts, scores, boxes, strict=True)
        ]
        text, lines = _with_offsets(lines)
        failure = None
    except Exception as exc:  # noqa: BLE001 - preserve page failure in fixed denominator
        text, lines, failure = "", [], _bounded_error(exc)
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    stop.set()
    sampler.join()
    return {"text": text, "lines": lines, "failure": failure, "elapsed_ms": elapsed,
            "rss_before_bytes": baseline,
            "peak_sampled_rss_bytes": max(baseline, worker.memory_info().rss, *samples)}


def _boxes_in_bounds(lines: list[dict[str, Any]], image_size: tuple[int, int]) -> int:
    width, height = image_size
    return sum(
        len(line["polygon"]) == 4 and all(
            len(point) == 2 and 0 <= point[0] <= width and 0 <= point[1] <= height
            for point in line["polygon"]
        )
        for line in lines
    )


def _bounds(polygon: list[list[float]] | list[tuple[float, float]]) -> tuple[float, float, float, float]:
    return (min(point[0] for point in polygon), min(point[1] for point in polygon),
            max(point[0] for point in polygon), max(point[1] for point in polygon))


def _gold_bounds(quad: dict[str, Any]) -> tuple[float, float, float, float]:
    points = [(float(quad[f"x{idx}"]), float(quad[f"y{idx}"])) for idx in range(1, 5)]
    return _bounds(points)


def _gold_overlap(gold: tuple[float, float, float, float], predicted: tuple[float, float, float, float]) -> float:
    width = max(0.0, min(gold[2], predicted[2]) - max(gold[0], predicted[0]))
    height = max(0.0, min(gold[3], predicted[3]) - max(gold[1], predicted[1]))
    area = max(1.0, (gold[2] - gold[0]) * (gold[3] - gold[1]))
    return width * height / area


def annotation_availability(annotation: dict[str, Any], engine: dict[str, Any]) -> dict[str, bool]:
    page = contains_normalized(engine["text"], annotation["gold_text"])
    gold = _gold_bounds(annotation["quad"])
    overlapping = [line["text"] for line in engine["lines"]
                   if _gold_overlap(gold, _bounds(line["polygon"])) >= 0.5]
    return {"page_text_present": page,
            "local_box_detected": bool(overlapping),
            "local_text_present": contains_normalized(" ".join(overlapping), annotation["gold_text"])}


def _extract_without_model(doc_id: str, source_path: str, text: str) -> dict[str, Any]:
    from idpo.core.types import AgentResult, Document, Page
    from idpo.product_auto.workflow import _process_document

    class SuppliedPageOcr:
        def run(self, payload: dict[str, Any], ctx: Any) -> AgentResult:
            return AgentResult(artifacts={"document": payload["document"]})

    document = Document(doc_id=doc_id, source="scanned", path=source_path, pages=[Page(1, text)])
    candidate, _ = _process_document(doc_id, document, None, SuppliedPageOcr(), None, None)
    return candidate


def _gold_text_targets(gold_path: Path) -> dict[str, dict[str, Any]]:
    records = _read_jsonl(gold_path)
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        scalars: list[str] = []
        cells: list[tuple[int, str, str]] = []
        rows: dict[int, dict[str, str]] = defaultdict(dict)
        for item in record["gold_values"]:
            field_id, value = item["field_id"], item["value"]
            if isinstance(value, str):
                scalars.append(value)
            elif isinstance(value, list):
                for cell in value:
                    cells.append((cell["row"], field_id, cell["value"]))
                    rows[cell["row"]][field_id] = cell["value"]
        complete_rows = [values for values in rows.values() if {"item_name", "item_price"} <= set(values)]
        result[record["doc_id"]] = {"scalars": scalars, "cells": cells, "rows": complete_rows}
    if len(result) != 60 or [sum(len(row[key]) for row in result.values()) for key in ("scalars", "cells", "rows")] != [195, 458, 157]:
        raise ValueError("CORD partial positive gold counts differ from frozen slice")
    return result


def _paired_metric(outcomes: list[tuple[bool, bool]]) -> dict[str, int]:
    counts = Counter(outcomes)
    return {"both": counts[(True, True)], "tesseract_only": counts[(True, False)],
            "rapidocr_only": counts[(False, True)], "neither": counts[(False, False)]}


def _box_bootstrap(per_doc: list[dict[str, Any]], metric: str) -> list[float]:
    rng = random.Random(BOOTSTRAP_SEED)
    deltas: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        selected = [per_doc[rng.randrange(len(per_doc))] for _ in per_doc]
        denominator = sum(row["boxes"] for row in selected)
        numerator = sum(row[f"rapid_{metric}"] - row[f"tess_{metric}"] for row in selected)
        deltas.append(numerator / denominator)
    return [_percentile(deltas, 0.025), _percentile(deltas, 0.975)]


def _summarize(
    stage_root: Path, records: list[dict[str, Any]], annotations: list[dict[str, Any]],
    preflight: dict[str, Any], output_dir: Path, *, cold_ms: float, providers: dict[str, list[str]],
    params: dict[str, Any],
) -> dict[str, Any]:
    by_doc = {row["doc_id"]: row for row in records}
    gold = _gold_text_targets(stage_root / "gold_development.jsonl")
    metrics = ("page_text_present", "local_box_detected", "local_text_present")
    box_outcomes: dict[str, list[tuple[bool, bool]]] = {name: [] for name in metrics}
    per_doc: dict[str, Counter[str]] = defaultdict(Counter)
    for annotation in annotations:
        row = by_doc[annotation["doc_id"]]
        tess = annotation_availability(annotation, row["tesseract"])
        rapid = annotation_availability(annotation, row["rapidocr"])
        stats = per_doc[annotation["doc_id"]]
        stats["boxes"] += 1
        for metric in metrics:
            stats[f"tess_{metric}"] += tess[metric]
            stats[f"rapid_{metric}"] += rapid[metric]
            box_outcomes[metric].append((tess[metric], rapid[metric]))
    positive: dict[str, list[tuple[bool, bool]]] = {name: [] for name in ("scalars", "cells", "text_complete_rows")}
    for row in records:
        labels = gold[row["doc_id"]]
        texts = (row["tesseract"]["text"], row["rapidocr"]["text"])
        for value in labels["scalars"]:
            positive["scalars"].append(tuple(contains_normalized(text, value) for text in texts))
        for _, _, value in labels["cells"]:
            positive["cells"].append(tuple(contains_normalized(text, value) for text in texts))
        for values in labels["rows"]:
            positive["text_complete_rows"].append(tuple(
                all(contains_normalized(text, value) for value in values.values()) for text in texts
            ))
    if len(records) != 60 or len(annotations) != 1389 or [len(positive[key]) for key in positive] != [195, 458, 157]:
        raise ValueError("Incomplete CORD full-page scoring denominator")
    doc_stats = [{"doc_id": doc_id, **dict(stats)} for doc_id, stats in sorted(per_doc.items())]
    box_summary = {}
    for metric in metrics:
        outcomes = box_outcomes[metric]
        box_summary[metric] = {
            "denominator": len(outcomes),
            "tesseract": sum(tess for tess, _ in outcomes),
            "rapidocr": sum(rapid for _, rapid in outcomes),
            "paired": _paired_metric(outcomes),
            "tesseract_document_macro": sum(row[f"tess_{metric}"] / row["boxes"] for row in doc_stats) / len(doc_stats),
            "rapidocr_document_macro": sum(row[f"rapid_{metric}"] / row["boxes"] for row in doc_stats) / len(doc_stats),
            "paired_receipt_bootstrap_95pct_delta": _box_bootstrap(doc_stats, metric),
        }
    positive_summary = {
        metric: {"denominator": len(outcomes), "tesseract": sum(t for t, _ in outcomes),
                 "rapidocr": sum(r for _, r in outcomes), "paired": _paired_metric(outcomes)}
        for metric, outcomes in positive.items()
    }
    downstream = {
        engine: score_cord_positive(
            stage_root / "cohort_development.jsonl", stage_root / "gold_development.jsonl",
            output_dir / f"{engine}_candidates.jsonl",
        )
        for engine in ("tesseract", "rapidocr")
    }
    timing = {}
    for engine in ("tesseract", "rapidocr"):
        values = [float(row[engine]["elapsed_ms"]) for row in records]
        timing[engine] = {"p50_ms": _percentile(values, 0.5), "p95_ms": _percentile(values, 0.95),
                          "sum_ms": round(sum(values), 3),
                          "failed_pages": sum(bool(row[engine]["failure"]) for row in records),
                          "empty_pages": sum(not row[engine]["text"].strip() for row in records),
                          "peak_sampled_rss_bytes": max(row[engine]["peak_sampled_rss_bytes"] for row in records)}
    summary = {
        "scope": "60 source-locked CORD v2 test development PNGs; full-page CPU detection and recognition",
        "documents": 60, "source_hashes": 60, "annotated_boxes": 1389,
        "normalization": "Unicode NFKC, casefold, alphanumeric-token string presence; optimistic partial positive proxy",
        "source_locks": preflight, "raw_sha256": sha256_file(output_dir / "raw.jsonl"),
        "candidate_sha256": {engine: sha256_file(output_dir / f"{engine}_candidates.jsonl")
                             for engine in ("tesseract", "rapidocr")},
        "params": params, "providers_actual": providers,
        "rapidocr_synthetic_cold_load_ms": cold_ms,
        "annotation_availability": box_summary,
        "partial_gold_page_text_presence": positive_summary,
        "deterministic_downstream": downstream,
        "timing_and_memory": timing,
        "geometry": {
            engine: {"lines": sum(len(row[engine]["lines"]) for row in records),
                     "lines_in_bounds": sum(row[engine]["lines_in_bounds"] for row in records)}
            for engine in ("tesseract", "rapidocr")
        },
        "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "per_document_annotation_counts": doc_stats,
    }
    return summary


def check_inputs(stage_root: Path, output_dir: Path, tesseract: Path, tessdata: Path) -> dict[str, Any]:
    """Verify immutable source, annotation, runtime, and output scope; no inference."""
    stage_root, output_dir = stage_root.resolve(), output_dir.resolve()
    if output_dir.exists():
        raise ValueError("Full-page OCR output directory already exists; use a new version")
    sources = _development_sources(stage_root / "cohort_development.jsonl", stage_root)
    annotations, _ = load_manifest(stage_root / "word-ocr-dev-v1" / "manifest.jsonl")
    if sha256_file(stage_root / "gold_development.jsonl") != DEVELOPMENT_GOLD_SHA256:
        raise ValueError("CORD development positive gold hash changed")
    if sha256_file(stage_root / "cohort_reserved.jsonl") != RESERVED_COHORT_SHA256:
        raise ValueError("CORD reserved source-list hash changed")
    reserved_hashes = {row["source_sha256"] for row in _read_jsonl(stage_root / "cohort_reserved.jsonl")}
    source_hashes = {row["source_sha256"] for row in sources}
    if len(reserved_hashes) != 40 or source_hashes & reserved_hashes:
        raise ValueError("CORD development/reserved source-hash separation failed")
    if len(annotations) != EXPECTED_ANNOTATED_BOXES or {row["source_sha256"] for row in annotations} != source_hashes:
        raise ValueError("CORD creator annotation sources differ from the frozen development set")
    for source in sources:
        with Image.open(source["source_path"]) as image:
            if image.format != "PNG" or image.width < 1 or image.height < 1:
                raise ValueError("CORD development source is not a valid PNG")
    if sha256_file(tesseract) != TESSERACT_EXE_SHA256 or sha256_file(tessdata / "eng.traineddata") != TESSERACT_ENG_SHA256:
        raise ValueError("Pinned Tesseract executable or English data changed")
    rapidocr_spec = util.find_spec("rapidocr")
    if rapidocr_spec is None or rapidocr_spec.origin is None:
        raise RuntimeError("Pinned RapidOCR is missing")
    model_root = Path(rapidocr_spec.origin).parent / "models"
    models = {"det": ("PP-OCRv6_det_small.onnx", DET_SHA256),
              "rec": ("PP-OCRv6_rec_small.onnx", REC_SHA256),
              "cls": ("ch_ppocr_mobile_v2.0_cls_mobile.onnx", CLS_SHA256)}
    for filename, expected_sha in models.values():
        if sha256_file(model_root / filename) != expected_sha:
            raise ValueError(f"Pinned RapidOCR {filename} hash changed")
    versions = {name: metadata.version(name) for name in ("rapidocr", "onnxruntime", "Pillow", "psutil")}
    if versions["rapidocr"] != "3.10.0" or versions["onnxruntime"] != "1.23.2":
        raise ValueError("Pinned RapidOCR or ONNX Runtime version changed")
    return {
        "ready": True, "inference_performed": False, "development_sources": len(sources),
        "annotated_boxes": len(annotations), "reserved_source_hashes_excluded": len(reserved_hashes),
        "cohort_sha256": DEVELOPMENT_COHORT_SHA256, "annotation_manifest_sha256": FROZEN_CROP_MANIFEST_SHA256,
        "gold_sha256": DEVELOPMENT_GOLD_SHA256, "reserved_cohort_sha256": RESERVED_COHORT_SHA256,
        "tesseract_exe_sha256": TESSERACT_EXE_SHA256, "tesseract_eng_sha256": TESSERACT_ENG_SHA256,
        "model_sha256": {part: digest for part, (_, digest) in models.items()},
        "runtime_versions": versions, "model_root": str(model_root),
    }


def run_diagnostic(stage_root: Path, output_dir: Path, tesseract: Path, tessdata: Path,
                   max_wall_seconds: int) -> dict[str, Any]:
    import numpy as np
    import psutil
    from PIL import ImageDraw
    from rapidocr import RapidOCR

    if max_wall_seconds < 1:
        raise ValueError("Full-page OCR wall budget must be positive")
    preflight = check_inputs(stage_root, output_dir, tesseract, tessdata)
    stage_root = stage_root.resolve()
    sources = _development_sources(stage_root / "cohort_development.jsonl", stage_root)
    annotations, _ = load_manifest(stage_root / "word-ocr-dev-v1" / "manifest.jsonl")
    model_root = Path(preflight["model_root"])
    params = {
        "Det.lang_type": "en", "Det.model_path": str(model_root / "PP-OCRv6_det_small.onnx"),
        "Rec.lang_type": "en", "Rec.model_path": str(model_root / "PP-OCRv6_rec_small.onnx"),
        "Cls.model_path": str(model_root / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"),
        "EngineConfig.onnxruntime.intra_op_num_threads": 4,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "EngineConfig.onnxruntime.use_cuda": False,
        "EngineConfig.onnxruntime.use_dml": False,
    }
    engine = RapidOCR(params=params)
    synthetic = Image.new("RGB", (500, 120), "white")
    ImageDraw.Draw(synthetic).text((20, 40), "OCR warmup 123", fill="black")
    cold_started = time.perf_counter()
    engine(np.asarray(synthetic))
    cold_ms = round((time.perf_counter() - cold_started) * 1000, 3)
    providers = {
        part: getattr(engine, part).session.session.get_providers()
        for part in ("text_det", "text_cls", "text_rec")
    }
    if any(value != ["CPUExecutionProvider"] for value in providers.values()):
        raise RuntimeError(f"RapidOCR did not use only CPUExecutionProvider: {providers}")
    worker = psutil.Process()
    output_dir.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, Any]] = []
    started = time.monotonic()
    with (output_dir / "raw.jsonl").open("w", encoding="utf-8", newline="\n") as raw, \
         (output_dir / "tesseract_candidates.jsonl").open("w", encoding="utf-8", newline="\n") as tess_candidates, \
         (output_dir / "rapidocr_candidates.jsonl").open("w", encoding="utf-8", newline="\n") as rapid_candidates:
        for index, source in enumerate(sources, 1):
            if time.monotonic() - started >= max_wall_seconds:
                raise TimeoutError("CORD full-page OCR wall budget exhausted; partial files are not a score")
            image_path = Path(source["source_path"])
            with Image.open(image_path) as image:
                image_size = image.size
            tess = _tesseract_page(image_path, tesseract, tessdata)
            rapid = _rapid_page(engine, image_path, worker)
            for result in (tess, rapid):
                result["lines_in_bounds"] = _boxes_in_bounds(result["lines"], image_size)
            record = {"doc_id": source["doc_id"], "source_id": source["source_id"],
                      "source_sha256": source["source_sha256"], "image_size": list(image_size),
                      "tesseract": tess, "rapidocr": rapid}
            raw.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            raw.flush()
            for result, stream in ((tess, tess_candidates), (rapid, rapid_candidates)):
                candidate = _extract_without_model(source["doc_id"], str(image_path), result["text"])
                stream.write(json.dumps(candidate, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
            records.append(record)
            print(f"{index}/{len(sources)} CORD full-page OCR", flush=True)
    summary = _summarize(stage_root, records, annotations, preflight, output_dir,
                         cold_ms=cold_ms, providers=providers, params=params)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "run"):
        command = commands.add_parser(name)
        command.add_argument("--stage-root", type=Path, required=True)
        command.add_argument("--output-dir", type=Path, required=True)
        command.add_argument("--tesseract", type=Path, required=True)
        command.add_argument("--tessdata", type=Path, required=True)
        if name == "run":
            command.add_argument("--max-wall-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.command == "check":
        result = check_inputs(args.stage_root, args.output_dir, args.tesseract, args.tessdata)
    else:
        result = run_diagnostic(args.stage_root, args.output_dir, args.tesseract, args.tessdata,
                                args.max_wall_seconds)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

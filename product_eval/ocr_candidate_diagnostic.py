"""Bounded, read-only OCR comparison on existing public gate render artifacts.

This diagnostic does not alter product OCR. It compares a pinned RapidOCR engine
with the already completed Tesseract output on identical, pre-rendered page PNGs.
Only OCR pages with page-local scalar gold evidence are eligible for selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_for_coverage(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def target_coverage(targets: list[dict[str, str]], text: str) -> list[dict[str, object]]:
    normalized_text = normalize_for_coverage(text)
    return [
        {"field_id": target["field_id"], "matched": bool(normalize_for_coverage(target["value"]))
         and normalize_for_coverage(target["value"]) in normalized_text}
        for target in targets
    ]


def scalar_targets(gold: dict[str, Any], page_number: int) -> list[dict[str, str]]:
    scalar_ids = {
        item["field_id"] for item in gold.get("gold_schema", [])
        if isinstance(item, dict) and item.get("type") != "array[object]"
    }
    targets = []
    for item in gold.get("gold_values", []):
        if not isinstance(item, dict) or item.get("field_id") not in scalar_ids:
            continue
        value, evidence = item.get("value"), item.get("evidence")
        if not isinstance(value, str) or not value.strip() or not isinstance(evidence, dict):
            continue
        if evidence.get("page") == page_number:
            targets.append({"field_id": item["field_id"], "value": value})
    return targets


def select_pages(
    cohort_path: Path, gold_path: Path, runs_root: Path, *, per_family: int,
) -> list[dict[str, Any]]:
    cohort = {item["doc_id"]: item for item in _read_jsonl(cohort_path)}
    gold = {item["doc_id"]: item for item in _read_jsonl(gold_path)}
    candidates: dict[str, list[dict[str, Any]]] = {}
    for run in sorted(runs_root.glob("vrdu_v5_*")):
        for sidecar in (run / "docs").glob("*/result.json"):
            doc_id = sidecar.parent.name
            row = cohort.get(doc_id)
            if row is None or doc_id not in gold:
                continue
            result = json.loads(sidecar.read_text(encoding="utf-8"))
            if result.get("source_sha256") != row["source_sha256"]:
                raise ValueError(f"Source hash mismatch: {doc_id}")
            page_text = {item["page"]: item["text"] for item in result.get("pages", [])}
            for item in result.get("ocr_pages", []):
                page_number = item.get("page")
                if item.get("engine") != "tesseract" or not isinstance(page_number, int):
                    continue
                targets = scalar_targets(gold[doc_id], page_number)
                if not targets:
                    continue
                rendered = list((run / "artifacts" / "derived_images").glob(
                    f"{doc_id}_p{page_number}_pdf_render_*.png"
                ))
                if len(rendered) != 1 or page_number not in page_text:
                    raise ValueError(f"Missing or ambiguous baseline page artifact: {doc_id} p{page_number}")
                candidates.setdefault(row["family"], []).append({
                    "doc_id": doc_id,
                    "family": row["family"],
                    "source_sha256": row["source_sha256"],
                    "page": page_number,
                    "image_path": str(rendered[0]),
                    "image_sha256": sha256_file(rendered[0]),
                    "v5_text": page_text[page_number],
                    "v5_confidence": item.get("confidence"),
                    "targets": targets,
                })
    selected = []
    for family in sorted(candidates):
        by_doc: dict[str, dict[str, Any]] = {}
        for row in candidates[family]:
            current = by_doc.get(row["doc_id"])
            if current is None or (-len(row["targets"]), row["page"]) < (
                -len(current["targets"]), current["page"]
            ):
                by_doc[row["doc_id"]] = row
        family_rows = sorted(by_doc.values(), key=lambda row: (row["source_sha256"], row["page"]))
        if len(family_rows) < per_family:
            raise ValueError(f"Only {len(family_rows)} eligible {family} documents")
        selected.extend(family_rows[:per_family])
    return selected


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    lower, upper = int(rank), min(int(rank) + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower), 3)


def _sample_rss(stop: threading.Event, process: Any, samples: list[int]) -> None:
    while not stop.wait(0.02):
        try:
            samples.append(process.memory_info().rss)
        except Exception:  # noqa: BLE001 - a short-lived child may exit between samples
            break


def _tesseract_single_pass(
    image: str, executable: Path, tessdata: Path,
) -> tuple[float, str | None, int]:
    import psutil

    started = time.perf_counter()
    env = {**os.environ, "OMP_THREAD_LIMIT": "4"}
    process = subprocess.Popen(
        [str(executable), image, "stdout", "-l", "eng", "--oem", "3", "--psm", "6",
         "--tessdata-dir", str(tessdata)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    child = psutil.Process(process.pid)
    stop = threading.Event()
    rss_samples: list[int] = []
    sampler = threading.Thread(target=_sample_rss, args=(stop, child, rss_samples), daemon=True)
    sampler.start()
    try:
        process.communicate(timeout=30)
        failure = None if process.returncode == 0 else f"exit_{process.returncode}"
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        failure = "timeout_30s"
    stop.set()
    sampler.join()
    return round((time.perf_counter() - started) * 1000, 3), failure, max(rss_samples, default=0)


def run_diagnostic(args: argparse.Namespace) -> dict[str, Any]:
    import numpy as np
    import onnxruntime as ort
    import psutil
    import rapidocr
    from PIL import Image, ImageDraw
    from rapidocr import RapidOCR

    selected = select_pages(args.cohort, args.gold, args.runs_root, per_family=args.per_family)
    params = {
        "Det.lang_type": "en",
        "Rec.lang_type": "en",
        "EngineConfig.onnxruntime.intra_op_num_threads": 4,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "EngineConfig.onnxruntime.use_cuda": False,
        "EngineConfig.onnxruntime.use_dml": False,
    }
    engine = RapidOCR(params=params)
    # Load all three local models before recording page latency.
    warmup_image = Image.new("RGB", (500, 120), "white")
    ImageDraw.Draw(warmup_image).text((20, 40), "OCR warmup 123", fill="black")
    warmup_started = time.perf_counter()
    engine(np.asarray(warmup_image))
    warmup_ms = round((time.perf_counter() - warmup_started) * 1000, 3)
    process = psutil.Process()
    records = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        for row in selected:
            rss_samples: list[int] = []
            stop = threading.Event()

            sampler = threading.Thread(
                target=_sample_rss, args=(stop, process, rss_samples), daemon=True
            )
            baseline_rss = process.memory_info().rss
            sampler.start()
            started = time.perf_counter()
            try:
                output = engine(row["image_path"])
                rapid_failure = None
                lines = list(output.txts or ())
                scores = [float(score) for score in (output.scores or ())]
                boxes = output.boxes.tolist() if output.boxes is not None else []
            except Exception as exc:  # noqa: BLE001 - keep page-level failures in denominator
                rapid_failure = f"{type(exc).__name__}: {str(exc)[:120]}"
                lines, scores, boxes = [], [], []
            rapid_ms = round((time.perf_counter() - started) * 1000, 3)
            stop.set()
            sampler.join()
            peak_rss = max([baseline_rss, process.memory_info().rss, *rss_samples])
            tess_ms, tess_failure, tess_peak_rss = _tesseract_single_pass(
                row["image_path"], args.tesseract, args.tessdata
            )
            with Image.open(row["image_path"]) as image:
                width, height = image.size
            boxes_in_bounds = sum(
                bool(box) and all(
                    len(point) == 2 and 0 <= point[0] < width and 0 <= point[1] < height
                    for point in box
                )
                for box in boxes
            )
            rapid_text = "\n".join(lines)
            record = {
                **row,
                "rapid_text": rapid_text,
                "rapid_lines": [
                    {"text": text, "confidence": score, "box": box}
                    for text, score, box in zip(lines, scores, boxes, strict=True)
                ],
                "rapid_ms": rapid_ms,
                "rapid_failure": rapid_failure,
                "rapid_rss_before_bytes": baseline_rss,
                "rapid_rss_peak_sampled_bytes": peak_rss,
                "image_size": [width, height],
                "rapid_boxes_in_bounds": boxes_in_bounds,
                "tesseract_single_pass_ms": tess_ms,
                "tesseract_single_pass_failure": tess_failure,
                "tesseract_single_pass_peak_sampled_rss_bytes": tess_peak_rss,
                "v5_coverage": target_coverage(row["targets"], row["v5_text"]),
                "rapid_coverage": target_coverage(row["targets"], rapid_text),
            }
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            records.append(record)
            print(f"{len(records)}/{len(selected)} {row['family']} {row['doc_id']} p{row['page']}", flush=True)
    by_family = {}
    for family in sorted({row["family"] for row in records}):
        family_rows = [row for row in records if row["family"] == family]
        by_family[family] = {
            "pages": len(family_rows),
            "gold_scalar_targets": sum(len(row["targets"]) for row in family_rows),
            "v5_targets_present": sum(item["matched"] for row in family_rows for item in row["v5_coverage"]),
            "rapid_targets_present": sum(item["matched"] for row in family_rows for item in row["rapid_coverage"]),
            "rapid_failures": sum(bool(row["rapid_failure"]) for row in family_rows),
            "rapid_empty_pages": sum(not row["rapid_text"].strip() for row in family_rows),
            "rapid_boxes": sum(len(row["rapid_lines"]) for row in family_rows),
            "rapid_boxes_in_bounds": sum(row["rapid_boxes_in_bounds"] for row in family_rows),
            "paired_targets": {
                label: sum(
                    (bool(v5["matched"]), bool(rapid["matched"])) == state
                    for row in family_rows
                    for v5, rapid in zip(row["v5_coverage"], row["rapid_coverage"], strict=True)
                )
                for label, state in (
                    ("both", (True, True)),
                    ("v5_only", (True, False)),
                    ("rapid_only", (False, True)),
                    ("neither", (False, False)),
                )
            },
        }
    summary = {
        "selected_pages": len(records),
        "unique_sources": len({row["source_sha256"] for row in records}),
        "cohort_sha256": sha256_file(args.cohort),
        "gold_sha256": sha256_file(args.gold),
        "raw_sha256": sha256_file(args.output),
        "rapidocr": "3.10.0",
        "onnxruntime": ort.__version__,
        "bundled_models_sha256": {
            name: sha256_file(Path(rapidocr.__file__).parent / "models" / name)
            for name in (
                "PP-OCRv6_det_small.onnx",
                "PP-OCRv6_rec_small.onnx",
                "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
            )
        },
        "engine_parameters": params,
        "image_parameters": {
            "max_side_len": engine.cfg.Global.max_side_len,
            "detection_limit_side_len": engine.cfg.Det.limit_side_len,
            "preprocess_image": engine.cfg.Global.use_preprocess_img,
            "vertical_padding": engine.cfg.Global.use_vertical_padding,
        },
        "host_processor": platform.processor(),
        "host_logical_cpus": psutil.cpu_count(),
        "host_ram_bytes": psutil.virtual_memory().total,
        "providers_available": ort.get_available_providers(),
        "providers_selected": {
            part: getattr(engine, part).session.session.get_providers()
            if getattr(engine, part) is not None else []
            for part in ("text_det", "text_cls", "text_rec")
        },
        "warmup_ms": warmup_ms,
        "rapid_latency_ms_p50": _percentile([row["rapid_ms"] for row in records], 0.5),
        "rapid_latency_ms_p95": _percentile([row["rapid_ms"] for row in records], 0.95),
        "tesseract_direct_latency_ms_p50": _percentile(
            [row["tesseract_single_pass_ms"] for row in records], 0.5
        ),
        "tesseract_direct_latency_ms_p95": _percentile(
            [row["tesseract_single_pass_ms"] for row in records], 0.95
        ),
        "tesseract_direct_failures": sum(bool(row["tesseract_single_pass_failure"]) for row in records),
        "rapid_peak_rss_bytes": max(row["rapid_rss_peak_sampled_bytes"] for row in records),
        "tesseract_direct_peak_sampled_rss_bytes": max(
            row["tesseract_single_pass_peak_sampled_rss_bytes"] for row in records
        ),
        "by_family": by_family,
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--tesseract", type=Path, required=True)
    parser.add_argument("--tessdata", type=Path, required=True)
    parser.add_argument("--per-family", type=int, default=15)
    args = parser.parse_args()
    if args.per_family < 1 or args.per_family > 20:
        parser.error("per-family must be from 1 to 20")
    print(json.dumps(run_diagnostic(args), indent=2))


if __name__ == "__main__":
    main()

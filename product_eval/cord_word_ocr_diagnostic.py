"""Paired recognition-only OCR diagnostic on CORD development annotation crops.

`prepare` freezes PNG crops from creator `valid_line.words[].quad` in the
60-source development split. `run` gives each identical saved crop to Tesseract
and PP-OCRv6 small recognition; neither engine performs page text detection.
The 40 reserved sources are never selected or parsed. This is not a CORD
full-page OCR, detection, extraction, or official parsing benchmark.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from product_eval.datasets.cord_test import PARQUET_SHA256

DEVELOPMENT_COHORT_SHA256 = "48f9af8c04a5ee874c68ccb4c70a5fb81bcfddc508064747779678949103414a"
EXPECTED_DEVELOPMENT_SOURCES = 60
EXPECTED_DEVELOPMENT_LINES = 796
EXPECTED_ANNOTATED_BOXES = 1389
EXPECTED_MULTI_TOKEN_BOXES = 20
TESSERACT_EXE_SHA256 = "c66f0f12ed76f6aa455dac97684bbc86756d6a732380bee09122454cfda3f420"
TESSERACT_ENG_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
RAPIDOCR_REC_SHA256 = "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884"
CROP_MARGIN_PX = 2
CROP_UPSCALE = 3
BOOTSTRAP_SEED = 20261012
BOOTSTRAP_REPLICATES = 10000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical_text(value: str) -> str:
    """Normalize Unicode and whitespace only; preserve case and punctuation."""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def character_edits(reference: str, prediction: str) -> int:
    """Code-point Levenshtein distance; never cap insertions at reference length."""
    prior = list(range(len(prediction) + 1))
    for i, source_char in enumerate(reference, 1):
        current = [i]
        for j, output_char in enumerate(prediction, 1):
            current.append(min(prior[j] + 1, current[j - 1] + 1, prior[j - 1] + (source_char != output_char)))
        prior = current
    return prior[-1]


def _quad_points(quad: dict[str, Any], image_size: tuple[int, int]) -> list[tuple[float, float]]:
    if not isinstance(quad, dict):
        raise ValueError("CORD word quad is missing")
    points = []
    for index in range(1, 5):
        x, y = quad.get(f"x{index}"), quad.get(f"y{index}")
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise ValueError("CORD word quad has a nonnumeric coordinate")
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("CORD word quad has a nonfinite coordinate")
        if not (-2 <= x <= image_size[0] + 2 and -2 <= y <= image_size[1] + 2):
            raise ValueError("CORD word quad extends beyond the two-pixel annotation tolerance")
        points.append((float(x), float(y)))
    return points


def crop_quad(image: Image.Image, quad: dict[str, Any]) -> Image.Image:
    """Rectify CORD points 1,2,3,4 (TL,TR,BR,BL) to one RGB crop."""
    p1, p2, p3, p4 = _quad_points(quad, image.size)
    width = math.ceil(max(math.dist(p1, p2), math.dist(p4, p3)))
    height = math.ceil(max(math.dist(p1, p4), math.dist(p2, p3)))
    if width < 2 or height < 2 or width > image.width * 2 or height > image.height * 2:
        raise ValueError("CORD word quad has invalid dimensions")
    # Pillow QUAD expects TL, BL, BR, TR. White fills the one known -1 px edge.
    pixels = (*p1, *p4, *p3, *p2)
    rectified = image.convert("RGB").transform(
        (width, height), Image.Transform.QUAD, pixels,
        resample=Image.Resampling.BICUBIC, fillcolor=(255, 255, 255),
    )
    padded = ImageOps.expand(rectified, border=CROP_MARGIN_PX, fill="white")
    return padded.resize((padded.width * CROP_UPSCALE, padded.height * CROP_UPSCALE), Image.Resampling.LANCZOS)


def _development_sources(cohort_path: Path, stage_root: Path) -> list[dict[str, Any]]:
    if sha256_file(cohort_path) != DEVELOPMENT_COHORT_SHA256:
        raise ValueError("CORD development cohort hash differs from the frozen split")
    sources = _read_jsonl(cohort_path)
    if len(sources) != EXPECTED_DEVELOPMENT_SOURCES:
        raise ValueError("CORD development source count changed")
    seen_indices: set[int] = set()
    seen_hashes: set[str] = set()
    for row in sources:
        match = re.fullmatch(r"cord-v2/test/(\d{4})", str(row.get("source_id", "")))
        index = int(match.group(1)) if match else -1
        source_path = Path(str(row.get("source_path", ""))).resolve()
        if (
            row.get("evaluation_split") != "development"
            or source_path.parent != (stage_root / "input_development").resolve()
            or not 0 <= index < 100
            or index in seen_indices
            or row.get("source_sha256") in seen_hashes
        ):
            raise ValueError("CORD source is not a unique frozen development image")
        if not source_path.is_file() or sha256_file(source_path) != row["source_sha256"]:
            raise ValueError(f"CORD development image hash changed: {row.get('source_id')}")
        seen_indices.add(index)
        seen_hashes.add(row["source_sha256"])
    return sources


def prepare_manifest(*, stage_root: Path, parquet_path: Path, output_dir: Path) -> dict[str, Any]:
    """Create frozen annotation crops without invoking either OCR engine."""
    stage_root, parquet_path, output_dir = stage_root.resolve(), parquet_path.resolve(), output_dir.resolve()
    cohort_path = stage_root / "cohort_development.jsonl"
    sources = _development_sources(cohort_path, stage_root)
    if sha256_file(parquet_path) != PARQUET_SHA256:
        raise ValueError("CORD creator parquet hash changed")
    if output_dir.exists():
        raise ValueError("CORD crop output already exists; use a new directory")
    try:
        import pyarrow
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("prepare requires pinned pyarrow, outside the OCR inference runtime") from exc
    parquet = pq.ParquetFile(parquet_path)
    if parquet.metadata.num_rows != 100 or parquet.metadata.num_row_groups != 1:
        raise ValueError("CORD creator parquet structure changed")
    # The file has one row group; Arrow decompresses the annotation column, but
    # only the 60 source-locked development indices are parsed or used below.
    annotations = parquet.read_row_group(0, columns=["ground_truth"]).column("ground_truth")
    records: list[dict[str, Any]] = []
    line_count = 0
    multi_token_count = 0
    crop_root = output_dir / "crops"
    crop_root.mkdir(parents=True)
    for source in sources:
        index = int(source["source_id"].rsplit("/", 1)[1])
        annotation = json.loads(annotations[index].as_py())
        meta = annotation.get("meta", {})
        if meta.get("version") != "2.0.0" or meta.get("split") != "test" or meta.get("image_id") != index:
            raise ValueError(f"CORD annotation identity mismatch at row {index}")
        lines = annotation.get("valid_line")
        if not isinstance(lines, list):
            raise ValueError(f"CORD valid_line missing at row {index}")
        source_path = Path(source["source_path"])
        with Image.open(source_path) as opened:
            if opened.format != "PNG" or meta.get("image_size") != {"width": opened.width, "height": opened.height}:
                raise ValueError(f"CORD annotated image dimensions mismatch at row {index}")
            image = opened.convert("RGB")
        line_count += len(lines)
        for line_index, line in enumerate(lines):
            words = line.get("words") if isinstance(line, dict) else None
            if not isinstance(words, list):
                raise ValueError(f"CORD line words missing at row {index}, line {line_index}")
            for word_index, word in enumerate(words):
                if not isinstance(word, dict) or not isinstance(word.get("text"), str):
                    raise ValueError(f"CORD annotated text missing at row {index}, line {line_index}")
                gold_text = word["text"]
                if not gold_text.strip():
                    continue
                multi_token_count += any(character.isspace() for character in gold_text.strip())
                crop = crop_quad(image, word.get("quad"))
                crop_path = crop_root / source["doc_id"] / f"l{line_index:03d}_w{word_index:03d}.png"
                crop_path.parent.mkdir(exist_ok=True)
                crop.save(crop_path, format="PNG", compress_level=6)
                records.append({
                    "crop_id": f"{source['doc_id']}:l{line_index:03d}:w{word_index:03d}",
                    "doc_id": source["doc_id"],
                    "source_id": source["source_id"],
                    "source_sha256": source["source_sha256"],
                    "annotation_row": index,
                    "line_index": line_index,
                    "word_index": word_index,
                    "category": line.get("category"),
                    "gold_text": gold_text,
                    "quad": word["quad"],
                    "crop_path": str(crop_path),
                    "crop_sha256": sha256_file(crop_path),
                    "crop_size": list(crop.size),
                })
    if (line_count, len(records), multi_token_count) != (
        EXPECTED_DEVELOPMENT_LINES, EXPECTED_ANNOTATED_BOXES, EXPECTED_MULTI_TOKEN_BOXES
    ):
        raise ValueError("CORD development valid_line counts differ from the frozen audit")
    manifest_path = output_dir / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    receipt = {
        "dataset": "CORD v2 creator test, source-locked development subset",
        "scope": "valid_line annotated text-box quads only; no page detection or reserved images",
        "creator_parquet_sha256": PARQUET_SHA256,
        "cohort_development_sha256": DEVELOPMENT_COHORT_SHA256,
        "manifest_sha256": sha256_file(manifest_path),
        "source_count": len(sources),
        "line_count": line_count,
        "crop_count": len(records),
        "multi_token_box_count": multi_token_count,
        "crop_rule": {"quad_order": "TL,TR,BR,BL", "rectify_resample": "bicubic", "margin_px": CROP_MARGIN_PX,
                      "upscale": CROP_UPSCALE, "upscale_resample": "lanczos", "color": "RGB", "outside_fill": "white"},
        "reader_versions": {"pyarrow": pyarrow.__version__, "pillow": Image.__version__},
    }
    (output_dir / "manifest_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def load_manifest(manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    receipt_path = manifest_path.parent / "manifest_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if sha256_file(manifest_path) != receipt["manifest_sha256"]:
        raise ValueError("CORD crop manifest changed")
    records = _read_jsonl(manifest_path)
    if len(records) != EXPECTED_ANNOTATED_BOXES or len({row["doc_id"] for row in records}) != 60:
        raise ValueError("CORD crop manifest count changed")
    if len({row["crop_id"] for row in records}) != len(records):
        raise ValueError("CORD crop IDs are not unique")
    for row in records:
        path = Path(row["crop_path"])
        if path.parent.parent != (manifest_path.parent / "crops").resolve():
            raise ValueError("CORD crop path escaped the frozen output directory")
        if not path.is_file() or sha256_file(path) != row["crop_sha256"]:
            raise ValueError(f"CORD crop changed: {row['crop_id']}")
    return records, receipt


def _tesseract_crop(image_path: Path, executable: Path, tessdata: Path) -> tuple[str, float, str | None]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            [str(executable), str(image_path), "stdout", "-l", "eng", "--oem", "3", "--psm", "7",
             "--tessdata-dir", str(tessdata)],
            capture_output=True, timeout=15, env={**os.environ, "OMP_THREAD_LIMIT": "4"}, check=False,
        )
    except subprocess.TimeoutExpired:
        return "", round((time.perf_counter() - started) * 1000, 3), "timeout_15s"
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    if result.returncode:
        return "", elapsed, f"exit_{result.returncode}:{result.stderr.decode(errors='replace')[:120]}"
    return result.stdout.decode("utf-8", errors="replace"), elapsed, None


def _rapid_crop(engine: Any, image_path: Path) -> tuple[str, float, float | None, str | None]:
    started = time.perf_counter()
    try:
        output = engine(image_path, use_det=False, use_cls=False, use_rec=True)
        texts = output.txts or ()
        scores = output.scores or ()
        if len(texts) != 1:
            raise ValueError("recognition-only output does not contain exactly one text box")
        return str(texts[0]), round((time.perf_counter() - started) * 1000, 3), float(scores[0]), None
    except Exception as exc:  # noqa: BLE001 - failed crops remain in the fixed denominator
        return "", round((time.perf_counter() - started) * 1000, 3), None, f"{type(exc).__name__}:{str(exc)[:120]}"


def run_recognizers(
    *, manifest_path: Path, output_path: Path, summary_path: Path, tesseract: Path, tessdata: Path,
    max_wall_seconds: int = 3600,
) -> dict[str, Any]:
    import importlib.metadata as metadata

    import rapidocr
    from rapidocr import RapidOCR

    records, receipt = load_manifest(manifest_path)
    if output_path.exists() or summary_path.exists() or output_path.resolve() == summary_path.resolve():
        raise ValueError("OCR output already exists; choose new paths to preserve evidence")
    if max_wall_seconds < 1:
        raise ValueError("OCR wall-time budget must be positive")
    if sha256_file(tesseract) != TESSERACT_EXE_SHA256 or sha256_file(tessdata / "eng.traineddata") != TESSERACT_ENG_SHA256:
        raise ValueError("Pinned Tesseract executable or English traineddata changed")
    model = Path(rapidocr.__file__).parent / "models" / "PP-OCRv6_rec_small.onnx"
    if sha256_file(model) != RAPIDOCR_REC_SHA256:
        raise ValueError("Pinned PP-OCRv6 small recognition weights changed")
    if metadata.version("rapidocr") != "3.10.0" or metadata.version("onnxruntime") != "1.23.2":
        raise ValueError("Pinned RapidOCR or ONNX Runtime version changed")
    params = {
        "Global.use_det": False, "Global.use_cls": False, "Global.use_rec": True,
        "Global.use_preprocess_img": False,
        "Rec.lang_type": "en", "Rec.ocr_version": "PP-OCRv6", "Rec.model_type": "small",
        "Rec.model_path": str(model),
        "EngineConfig.onnxruntime.intra_op_num_threads": 4,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "EngineConfig.onnxruntime.use_cuda": False,
        "EngineConfig.onnxruntime.use_dml": False,
    }
    engine = RapidOCR(params=params)
    # The first real crop loads the pinned model. Its latency remains in the raw record.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for index, row in enumerate(records, 1):
            if time.monotonic() - started >= max_wall_seconds:
                raise TimeoutError("CORD OCR wall-time budget exhausted; partial raw records are not a score")
            path = Path(row["crop_path"])
            tess_text, tess_ms, tess_failure = _tesseract_crop(path, tesseract, tessdata)
            rapid_text, rapid_ms, rapid_score, rapid_failure = _rapid_crop(engine, path)
            result = {
                "crop_id": row["crop_id"], "doc_id": row["doc_id"],
                "source_sha256": row["source_sha256"], "crop_sha256": row["crop_sha256"],
                "tesseract_text": tess_text, "tesseract_ms": tess_ms, "tesseract_failure": tess_failure,
                "rapid_text": rapid_text, "rapid_ms": rapid_ms, "rapid_score": rapid_score,
                "rapid_failure": rapid_failure,
            }
            handle.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            if index % 50 == 0 or index == len(records):
                print(f"{index}/{len(records)} recognition-only CORD crops", flush=True)
    providers = engine.text_rec.session.session.get_providers() if engine.text_rec is not None else []
    if providers != ["CPUExecutionProvider"]:
        raise RuntimeError(f"Unexpected RapidOCR inference providers: {providers}")
    return summarize_predictions(
        manifest_path, output_path, summary_path, receipt=receipt, params=params,
        model_sha256=RAPIDOCR_REC_SHA256, providers=providers,
        versions={"rapidocr": metadata.version("rapidocr"), "onnxruntime": metadata.version("onnxruntime"),
                  "pillow": Image.__version__},
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower), 6)


def _paired_bootstrap(by_doc: list[dict[str, Any]], reps: int, seed: int) -> dict[str, list[float]]:
    rng = random.Random(seed)
    samples: dict[str, list[float]] = {name: [] for name in (
        "exact_micro_delta", "exact_macro_delta", "cer_micro_delta", "cer_macro_delta"
    )}
    count = len(by_doc)
    for _ in range(reps):
        selected = [by_doc[rng.randrange(count)] for _ in range(count)]
        boxes = sum(doc["boxes"] for doc in selected)
        chars = sum(doc["gold_chars"] for doc in selected)
        samples["exact_micro_delta"].append(
            (sum(doc["rapid_exact"] - doc["tesseract_exact"] for doc in selected)) / boxes
        )
        samples["exact_macro_delta"].append(
            sum((doc["rapid_exact"] - doc["tesseract_exact"]) / doc["boxes"] for doc in selected) / count
        )
        samples["cer_micro_delta"].append(
            sum(doc["rapid_edits"] - doc["tesseract_edits"] for doc in selected) / chars
        )
        samples["cer_macro_delta"].append(
            sum((doc["rapid_edits"] - doc["tesseract_edits"]) / doc["gold_chars"] for doc in selected) / count
        )
    return {name: [_percentile(values, 0.025), _percentile(values, 0.975)] for name, values in samples.items()}


def score_predictions(manifest: list[dict[str, Any]], predictions: list[dict[str, Any]], *,
                      bootstrap_replicates: int = BOOTSTRAP_REPLICATES) -> dict[str, Any]:
    if len(manifest) != len(predictions):
        raise ValueError("Incomplete CORD OCR predictions")
    docs: dict[str, Counter[str]] = {}
    paired: Counter[str] = Counter()
    for gold, result in zip(manifest, predictions, strict=True):
        if (
            gold["crop_id"] != result.get("crop_id") or gold["doc_id"] != result.get("doc_id")
            or gold["crop_sha256"] != result.get("crop_sha256")
            or gold["source_sha256"] != result.get("source_sha256")
        ):
            raise ValueError("CORD OCR prediction order or source identity differs from manifest")
        reference = canonical_text(gold["gold_text"])
        if not reference:
            raise ValueError("CORD OCR reference is blank")
        tess = canonical_text(str(result["tesseract_text"]))
        rapid = canonical_text(str(result["rapid_text"]))
        item = docs.setdefault(gold["doc_id"], Counter())
        item["boxes"] += 1
        item["gold_chars"] += len(reference)
        item["tesseract_exact"] += tess == reference
        item["rapid_exact"] += rapid == reference
        item["tesseract_edits"] += character_edits(reference, tess)
        item["rapid_edits"] += character_edits(reference, rapid)
        item["tesseract_failures"] += bool(result.get("tesseract_failure"))
        item["rapid_failures"] += bool(result.get("rapid_failure"))
        paired[(tess == reference, rapid == reference)] += 1
    per_doc = [{"doc_id": doc_id, **dict(stats)} for doc_id, stats in sorted(docs.items())]
    n_boxes = sum(doc["boxes"] for doc in per_doc)
    n_chars = sum(doc["gold_chars"] for doc in per_doc)
    n_docs = len(per_doc)
    summary = {
        "scope": "CORD source-locked development valid_line annotated text boxes; recognition only",
        "documents": n_docs, "annotated_boxes": n_boxes, "gold_codepoints": n_chars,
        "normalization": "Unicode NFKC; collapse all whitespace to one space; case and punctuation retained",
        "tesseract": {
            "exact_micro": sum(doc["tesseract_exact"] for doc in per_doc) / n_boxes,
            "exact_macro_document": sum(doc["tesseract_exact"] / doc["boxes"] for doc in per_doc) / n_docs,
            "cer_micro": sum(doc["tesseract_edits"] for doc in per_doc) / n_chars,
            "cer_macro_document": sum(doc["tesseract_edits"] / doc["gold_chars"] for doc in per_doc) / n_docs,
            "failures": sum(doc.get("tesseract_failures", 0) for doc in per_doc),
        },
        "rapidocr": {
            "exact_micro": sum(doc["rapid_exact"] for doc in per_doc) / n_boxes,
            "exact_macro_document": sum(doc["rapid_exact"] / doc["boxes"] for doc in per_doc) / n_docs,
            "cer_micro": sum(doc["rapid_edits"] for doc in per_doc) / n_chars,
            "cer_macro_document": sum(doc["rapid_edits"] / doc["gold_chars"] for doc in per_doc) / n_docs,
            "failures": sum(doc.get("rapid_failures", 0) for doc in per_doc),
        },
        "paired_exact_boxes": {
            "both": paired[(True, True)], "tesseract_only": paired[(True, False)],
            "rapidocr_only": paired[(False, True)], "neither": paired[(False, False)],
        },
        "paired_document_bootstrap_95pct": _paired_bootstrap(per_doc, bootstrap_replicates, BOOTSTRAP_SEED),
        "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_replicates": bootstrap_replicates,
        "per_document": per_doc,
    }
    if all("tesseract_ms" in row and "rapid_ms" in row for row in predictions):
        summary["latency_ms"] = {
            engine: {
                "p50": _percentile([float(row[key]) for row in predictions], 0.5),
                "p95": _percentile([float(row[key]) for row in predictions], 0.95),
                "sum": round(sum(float(row[key]) for row in predictions), 3),
            }
            for engine, key in (("tesseract", "tesseract_ms"), ("rapidocr", "rapid_ms"))
        }
        summary["latency_ms"]["rapidocr"]["first_crop"] = float(predictions[0]["rapid_ms"])
    return summary


def summarize_predictions(
    manifest_path: Path, output_path: Path, summary_path: Path, *, receipt: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None, model_sha256: str | None = None,
    providers: list[str] | None = None, versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    manifest, locked_receipt = load_manifest(manifest_path)
    if receipt is not None and receipt != locked_receipt:
        raise ValueError("CORD crop receipt changed during inference")
    raw = _read_jsonl(output_path)
    summary = score_predictions(manifest, raw)
    summary.update({
        "manifest_sha256": locked_receipt["manifest_sha256"], "raw_sha256": sha256_file(output_path),
        "cohort_development_sha256": DEVELOPMENT_COHORT_SHA256,
        "creator_parquet_sha256": PARQUET_SHA256,
        "tesseract_exe_sha256": TESSERACT_EXE_SHA256,
        "tesseract_eng_sha256": TESSERACT_ENG_SHA256,
        "rapidocr_rec_model_sha256": model_sha256 or RAPIDOCR_REC_SHA256,
        "rapidocr_params": params,
        "rapidocr_selected_providers": providers,
        "runtime_versions": versions,
    })
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Freeze only the 60 development crop images and manifest")
    prepare.add_argument("--stage-root", type=Path, required=True)
    prepare.add_argument("--parquet", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    run = commands.add_parser("run", help="Run paired recognition on the frozen manifest")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--summary", type=Path, required=True)
    run.add_argument("--tesseract", type=Path, required=True)
    run.add_argument("--tessdata", type=Path, required=True)
    run.add_argument("--max-wall-seconds", type=int, default=3600)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_manifest(stage_root=args.stage_root, parquet_path=args.parquet, output_dir=args.output_dir)
    else:
        result = run_recognizers(
            manifest_path=args.manifest, output_path=args.output, summary_path=args.summary,
            tesseract=args.tesseract, tessdata=args.tessdata, max_wall_seconds=args.max_wall_seconds,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

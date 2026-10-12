"""CPU-only, oracle-schema GLiNER2.5 Small diagnostic on six locked OCR sources.

The model workers read only a committed ID/shape schema and source-locked OCR.
Gold values are opened only by the separate score command after inference ends.
Raw OCR and model replies stay outside Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError
from product_eval.graph_schema_diagnostic import (
    LOCK_PATH,
    _gold_for_scored,
    _verified_inventory,
    sha256_file,
)
from product_eval.nuextract3_dev_diagnostic import score_values


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_LOCK = Path(__file__).with_name("fixtures") / "gliner25_small_oracle_six.json"
SOURCE_LOCK_SHA256 = "61bef64cafb35739eba3a087fe5a742c57e68c340834325a8f77e49f63c5b047"
SCHEMA_LOCK_SHA256 = "1871cf55460944e748257c4e5de8832870250a581158126aba8b90f51ca5e77b"
MODEL_ID = "fastino/gliner2.5-small-v1"
MODEL_REVISION = "df5910e44bc4ffdb0d95399a83b0ca4516349aa5"
MODEL_WEIGHT_SHA256 = "4ee982787ace270d4bf15dbcb28ced38e0aa201372347114ceedd6336055de2b"
MODEL_WEIGHT_BYTES = 295_567_700
MODEL_FILES = {
    "model.safetensors": {"bytes": MODEL_WEIGHT_BYTES, "sha256": MODEL_WEIGHT_SHA256},
    "config.json": {"bytes": 4104,
                    "sha256": "1b4e63ac964dc4204165bd1420735cd4c2e4bce97394d0b69fa3f7ea192a8e97"},
    "encoder_config/config.json": {"bytes": 856,
                                   "sha256": "db837d0dc587f5858687ef860c1f400de10f3c3e44f88daef8cbda80d74e4c9c"},
    "tokenizer.json": {"bytes": 8341713,
                       "sha256": "cbc8ae6037812709c9c26f2a160f8dc48b0440bcb79c8141804259ae2d6adac3"},
    "tokenizer_config.json": {"bytes": 645,
                              "sha256": "0bf3ea0873234bd9bfdd3853c440395009ac6365a925b91654daed5396d655e1"},
}
GLINER2_VERSION = "2.1.0"
CHUNK_SIZE = 384
CHUNK_OVERLAP = 64
CPU_THREADS = 4
MAX_WORKER_SECONDS = 240
MIN_AVAILABLE_RAM_BYTES = 4 * 1024**3
MAX_WORKER_RSS_BYTES = 4 * 1024**3
MIN_FREE_STORAGE_BYTES = 1 * 1024**3
MAX_RAW_REPLY_BYTES = 10 * 1024**2


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _schema_rows(gold: dict[str, dict[str, Any]], inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in (item for item in inventory if item["role"] == "scored"):
        fields = [{"field_id": item["field_id"], "type": item["type"]}
                  for item in gold[row["doc_id"]]["gold_schema"]]
        if (not fields or len({item["field_id"] for item in fields}) != len(fields)
                or any(item["type"] not in {"string", "array[string]", "array[object]"}
                       for item in fields)):
            raise ContractError("unsupported or duplicate oracle field")
        linked = [item["field_id"] for item in fields if item["type"] == "array[object]"]
        result.append({
            "doc_id": row["doc_id"], "family": row["family"],
            "source_sha256": row["source_sha256"],
            "ocr_text_sha256": _sha_text(row["ocr_text"]),
            "sidecar_sha256": sha256_file(row["sidecar_path"]),
            "fields": fields,
            "record": {"name": "line_items", "mode": "natural", "anchor": linked[0],
                       "fields": linked} if linked else None,
        })
    if len(result) != 6 or len({row["source_sha256"] for row in result}) != 6:
        raise ContractError("oracle diagnostic requires six distinct scored sources")
    return result


def freeze(paths: dict[str, Path], runs_root: Path, output: Path) -> dict[str, Any]:
    if output.exists() or sha256_file(LOCK_PATH) != SOURCE_LOCK_SHA256:
        raise ContractError("source lock changed or oracle lock already exists")
    inventory = _verified_inventory(paths, runs_root, LOCK_PATH)
    gold = _gold_for_scored(paths, inventory)
    result = {
        "version": 1, "kind": "oracle_schema_text_only_development",
        "source_lock_sha256": SOURCE_LOCK_SHA256,
        "gold_manifest_sha256": {"vrdu": sha256_file(paths["vrdu_gold"]),
                                 "cord": sha256_file(paths["cord_gold"])},
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION,
                  "files": MODEL_FILES, "gliner2_version": GLINER2_VERSION},
        "settings": {"device": "cpu", "threads": CPU_THREADS, "chunk_size": CHUNK_SIZE,
                     "chunk_overlap": CHUNK_OVERLAP, "include_spans": True,
                     "include_confidence": True, "max_worker_seconds": MAX_WORKER_SECONDS,
                     "scalar_multiple_distinct_values": "abstain",
                     "linked_rows": "natural_anchor_first_linked_field_in_reference_order",
                     "cross_chunk_join": False},
        "sources": _schema_rows(gold, inventory),
    }
    _json(output, result)
    return result


def verified_inputs(paths: dict[str, Path], runs_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if (sha256_file(LOCK_PATH) != SOURCE_LOCK_SHA256
            or not SCHEMA_LOCK.exists() or sha256_file(SCHEMA_LOCK) != SCHEMA_LOCK_SHA256):
        raise ContractError("source or oracle-schema lock changed")
    manifest = json.loads(SCHEMA_LOCK.read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or manifest.get("kind") != "oracle_schema_text_only_development":
        raise ContractError("oracle-schema lock version differs")
    inventory = [row for row in _verified_inventory(paths, runs_root, LOCK_PATH)
                 if row["role"] == "scored"]
    if len(inventory) != 6 or len(manifest.get("sources", [])) != 6:
        raise ContractError("oracle-schema source count differs")
    for row, pinned in zip(inventory, manifest["sources"], strict=True):
        for key in ("doc_id", "family", "source_sha256"):
            if row[key] != pinned[key]:
                raise ContractError(f"oracle-schema source differs: {row['doc_id']}")
        if (_sha_text(row["ocr_text"]) != pinned["ocr_text_sha256"]
                or sha256_file(row["sidecar_path"]) != pinned["sidecar_sha256"]):
            raise ContractError(f"oracle-schema OCR differs: {row['doc_id']}")
    return manifest, inventory


def _model_files(model_dir: Path) -> dict[str, str]:
    files = {}
    for name, expected in MODEL_FILES.items():
        path = model_dir / name
        if not path.is_file():
            raise ContractError(f"pinned local model lacks {name}")
        files[name] = sha256_file(path)
        if path.stat().st_size != expected["bytes"] or files[name] != expected["sha256"]:
            raise ContractError(f"pinned GLiNER model file differs: {name}")
    return files


def _resource_guard(output: Path) -> dict[str, int]:
    import psutil

    available = psutil.virtual_memory().available
    free = psutil.disk_usage(str(output.parent)).free
    if available < MIN_AVAILABLE_RAM_BYTES or free < MIN_FREE_STORAGE_BYTES:
        raise ContractError("host RAM or output storage is below frozen floor")
    return {"host_available_ram_bytes": available, "output_disk_free_bytes": free}


def _build_schema(model: Any, source: dict[str, Any]) -> Any:
    schema = model.create_schema()
    entity_ids = [field["field_id"] for field in source["fields"]
                  if field["type"] != "array[object]"]
    if entity_ids:
        schema.entities(entity_ids)
    record = source["record"]
    if record is not None:
        builder = schema.structure(record["name"], mode="natural", anchor=record["anchor"])
        for field_id in record["fields"]:
            builder.field(field_id, dtype="str",
                          cardinality="required_one" if field_id == record["anchor"]
                          else "optional_one")
    return schema


def infer_worker(input_path: Path, model_dir: Path, output_path: Path) -> None:
    import psutil
    import torch
    from gliner2 import AutoExtractor

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    text = payload["ocr_text"]
    source = payload["source"]
    if _sha_text(text) != source["ocr_text_sha256"]:
        raise ContractError("worker OCR text changed")
    if torch.version.cuda is not None and os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
        raise ContractError("CPU-only worker CUDA visibility guard failed")
    torch.set_num_threads(CPU_THREADS)
    torch.set_num_interop_threads(1)
    started = time.perf_counter()
    model = AutoExtractor.from_pretrained(str(model_dir), map_location="cpu")
    if next(model.parameters()).device.type != "cpu":
        raise ContractError("GLiNER worker loaded outside CPU")
    load_seconds = time.perf_counter() - started
    schema = _build_schema(model, source)
    extracted_at = time.perf_counter()
    raw = model.extract_long(text, schema, chunk_size=CHUNK_SIZE,
                             chunk_overlap=CHUNK_OVERLAP,
                             include_spans=True, include_confidence=True)
    if not isinstance(raw, dict):
        raise ContractError("GLiNER returned non-object extraction")
    _json(output_path, {"doc_id": source["doc_id"], "status": "complete",
                        "ocr_text_sha256": source["ocr_text_sha256"], "raw": raw,
                        "load_seconds": round(load_seconds, 4),
                        "inference_seconds": round(time.perf_counter() - extracted_at, 4),
                        "worker_seconds": round(time.perf_counter() - started, 4),
                        "worker_rss_bytes_after_inference": psutil.Process().memory_info().rss})


def run(paths: dict[str, Path], runs_root: Path, model_dir: Path, output: Path) -> dict[str, Any]:
    import psutil

    manifest, inventory = verified_inputs(paths, runs_root)
    if output.exists() or output.resolve().is_relative_to(REPO_ROOT):
        raise ContractError("raw output must use a fresh directory outside Git")
    if output.parent.resolve() == output.resolve():
        raise ContractError("raw output path must be a child directory")
    resource_start = _resource_guard(output)
    model_hashes = _model_files(model_dir)
    import importlib.metadata as metadata

    if metadata.version("gliner2") != GLINER2_VERSION:
        raise ContractError("GLiNER2 package version differs from lock")
    output.mkdir(parents=True)
    started = time.perf_counter()
    records = []
    for source, row in zip(manifest["sources"], inventory, strict=True):
        _resource_guard(output)
        input_path = output / f"input-{source['doc_id']}.json"
        reply_path = output / f"reply-{source['doc_id']}.json"
        _json(input_path, {"source": source, "ocr_text": row["ocr_text"]})
        environment = dict(os.environ, CUDA_VISIBLE_DEVICES="-1", HF_HUB_OFFLINE="1",
                           TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
        command = [sys.executable, "-m", "product_eval.gliner25_small_oracle_diagnostic",
                   "worker", "--input", str(input_path), "--model-dir", str(model_dir),
                   "--reply", str(reply_path)]
        launched = time.perf_counter()
        status, error = "running", None
        peak_rss = 0
        min_available = psutil.virtual_memory().available
        stdout_path = output / f"stdout-{source['doc_id']}.txt"
        stderr_path = output / f"stderr-{source['doc_id']}.txt"
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(command, cwd=REPO_ROOT, env=environment,
                                       stdout=stdout, stderr=stderr)
            child = psutil.Process(process.pid)
            while process.poll() is None:
                try:
                    peak_rss = max(peak_rss, child.memory_info().rss)
                except psutil.NoSuchProcess:
                    pass
                available = psutil.virtual_memory().available
                min_available = min(min_available, available)
                if peak_rss > MAX_WORKER_RSS_BYTES or available < 2 * 1024**3:
                    status, error = "resource_guard", "worker RSS or host available RAM crossed floor"
                    process.kill()
                    break
                if time.perf_counter() - launched > MAX_WORKER_SECONDS:
                    status, error = "timeout", f"worker exceeded {MAX_WORKER_SECONDS} seconds"
                    process.kill()
                    break
                time.sleep(0.5)
            process.wait(timeout=10)
        if status == "running":
            if process.returncode or not reply_path.is_file() or reply_path.stat().st_size > MAX_RAW_REPLY_BYTES:
                status = "failure"
                error = stderr_path.read_text(encoding="utf-8", errors="replace")[-500:]
            else:
                status = "complete"
        record = {"doc_id": source["doc_id"], "status": status, "error": error,
                  "wall_seconds": round(time.perf_counter() - launched, 4),
                  "peak_worker_rss_bytes_sampled": peak_rss,
                  "min_host_available_ram_bytes_sampled": min_available,
                  "reply_sha256": sha256_file(reply_path) if status == "complete" else None}
        records.append(record)
        _json(output / "progress.json", {"records": records})
        if status in {"resource_guard", "timeout"}:
            break
    result = {"version": 1, "status": "sealed", "completed_utc": datetime.now(timezone.utc).isoformat(),
              "schema_lock_sha256": SCHEMA_LOCK_SHA256, "source_lock_sha256": SOURCE_LOCK_SHA256,
              "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "files_sha256": model_hashes},
              "runtime": {"python": sys.version.split()[0], "gliner2": GLINER2_VERSION,
                          "torch": metadata.version("torch"), "transformers": metadata.version("transformers")},
              "resource_start": resource_start, "records": records,
              "wall_seconds": round(time.perf_counter() - started, 4)}
    _json(output / "run.json", result)
    return result


def _atom(value: Any, text: str, spans: Counter[str]) -> str | None:
    if isinstance(value, str):
        spans["missing_offsets"] += 1
        return value
    if not isinstance(value, dict) or not isinstance(value.get("text"), str):
        spans["invalid_value"] += 1
        return None
    raw = value["text"]
    start, end = value.get("start"), value.get("end")
    if type(start) is int and type(end) is int and 0 <= start < end <= len(text) and text[start:end] == raw:
        spans["verified_offsets"] += 1
    else:
        spans["invalid_or_missing_offsets"] += 1
    return raw


def _candidate_to_reply(raw: dict[str, Any], source: dict[str, Any], text: str) -> tuple[dict[str, Any], dict[str, int]]:
    spans: Counter[str] = Counter()
    entities = raw.get("entities") if isinstance(raw.get("entities"), dict) else {}
    reply: dict[str, Any] = {}
    for field in source["fields"]:
        field_id, kind = field["field_id"], field["type"]
        if kind == "array[object]":
            continue
        candidates = entities.get(field_id, [])
        if not isinstance(candidates, list):
            candidates = []
        values = [value for candidate in candidates
                  if (value := _atom(candidate, text, spans)) is not None]
        if kind == "array[string]":
            reply[field_id] = values
        else:
            distinct = set(values)
            reply[field_id] = next(iter(distinct)) if len(distinct) == 1 else None
            if len(distinct) > 1:
                spans["ambiguous_scalar_fields"] += 1
    records = raw.get("line_items", [])
    reply["line_items"] = []
    if isinstance(records, list):
        linked_ids = source["record"]["fields"] if source["record"] else []
        for record in records:
            if not isinstance(record, dict):
                spans["invalid_record"] += 1
                continue
            linked = {}
            for field_id in linked_ids:
                atom = _atom(record.get(field_id), text, spans)
                if atom is not None:
                    linked[field_id] = atom
            reply["line_items"].append(linked)
    else:
        spans["invalid_record_list"] += 1
    return reply, dict(spans)


def score(paths: dict[str, Path], runs_root: Path, output: Path) -> dict[str, Any]:
    manifest, inventory = verified_inputs(paths, runs_root)
    run_path = output / "run.json"
    if not run_path.is_file():
        raise ContractError("inference run is not sealed")
    run_data = json.loads(run_path.read_text(encoding="utf-8"))
    if run_data.get("status") != "sealed" or run_data.get("schema_lock_sha256") != SCHEMA_LOCK_SHA256:
        raise ContractError("inference seal differs")
    gold = _gold_for_scored(paths, inventory)
    result_rows = []
    for source, row in zip(manifest["sources"], inventory, strict=True):
        doc_id = source["doc_id"]
        record = next((item for item in run_data["records"] if item["doc_id"] == doc_id), None)
        status = record["status"] if record else "not_attempted"
        reply, spans = {}, {}
        if status == "complete":
            path = output / f"reply-{doc_id}.json"
            if not path.is_file() or sha256_file(path) != record["reply_sha256"]:
                raise ContractError(f"model reply changed: {doc_id}")
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("status") != "complete" or raw.get("ocr_text_sha256") != source["ocr_text_sha256"]:
                raise ContractError(f"model reply source differs: {doc_id}")
            reply, spans = _candidate_to_reply(raw["raw"], source, row["ocr_text"])
        value_score = score_values(reply, gold[doc_id])
        result_rows.append({"doc_id": doc_id, "family": source["family"], "status": status,
                            "spans": spans, "scores": value_score})
    totals = Counter()
    span_totals = Counter()
    for row in result_rows:
        totals.update(row["scores"])
        span_totals.update(row["spans"])
    report = {"version": 1, "kind": "oracle_schema_text_only_development",
              "schema_lock_sha256": SCHEMA_LOCK_SHA256,
              "scored_sources": len(result_rows), "sources": result_rows,
              "totals": dict(totals), "span_totals": dict(span_totals),
              "failed_or_unattempted": sum(row["status"] != "complete" for row in result_rows),
              "machine_auto_accepted_values": 0}
    _json(output / "score.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("freeze", "check", "run", "score"):
        command = commands.add_parser(name)
        command.add_argument("--vrdu-cohort", required=True, type=Path)
        command.add_argument("--vrdu-gold", required=True, type=Path)
        command.add_argument("--cord-cohort", required=True, type=Path)
        command.add_argument("--cord-gold", required=True, type=Path)
        command.add_argument("--runs-root", required=True, type=Path)
        if name == "freeze":
            command.add_argument("--output", required=True, type=Path)
        if name in {"run", "score"}:
            command.add_argument("--output", required=True, type=Path)
        if name == "run":
            command.add_argument("--model-dir", required=True, type=Path)
    worker = commands.add_parser("worker")
    worker.add_argument("--input", required=True, type=Path)
    worker.add_argument("--model-dir", required=True, type=Path)
    worker.add_argument("--reply", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "worker":
        infer_worker(args.input, args.model_dir, args.reply)
        return
    paths = {"vrdu_cohort": args.vrdu_cohort, "vrdu_gold": args.vrdu_gold,
             "cord_cohort": args.cord_cohort, "cord_gold": args.cord_gold}
    if args.command == "freeze":
        result = freeze(paths, args.runs_root, args.output)
        print(json.dumps({"frozen_sources": len(result["sources"]) }))
    elif args.command == "check":
        manifest, inventory = verified_inputs(paths, args.runs_root)
        print(json.dumps({"ready": True, "sources": len(inventory),
                          "schema_lock_sha256": sha256_file(SCHEMA_LOCK)}))
    elif args.command == "run":
        result = run(paths, args.runs_root, args.model_dir, args.output)
        print(json.dumps({"attempted": len(result["records"]), "output": str(args.output)}))
    else:
        result = score(paths, args.runs_root, args.output)
        print(json.dumps({"scored": result["scored_sources"], "totals": result["totals"]}))


if __name__ == "__main__":
    main()

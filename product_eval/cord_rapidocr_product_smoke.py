"""Two fixed development receipt originals through fresh product RapidOCR.

Prepare reads source identities and schema, never gold. Run is single-attempt,
at most two Luna 6 calls, and seals all outputs before a separate gold scorer.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import time
from pathlib import Path

from PIL import Image

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.provider import OpenAICompatibleChat
from idpo.product_auto.rapid_ocr import RapidOcrConfig
from idpo.product_auto.rapid_ocr_protocol import MODEL_SHA256, REVISION, validate_image_size
from idpo.product_auto.workflow import process_auto
from product_eval.cord_model_ocr_replay import ReplayChat, SOURCE_HASHES
from product_eval.execution import verify_runs
from product_eval.icore_capability_diagnostic import BASE_URL, load_credential
from product_eval.icore_confirmed_dev import MODEL, OUTPUT_TOKENS, TIMEOUT_SECONDS, append, code_receipt, sha, write

REPLAY_PROTOCOL_SHA256 = "e793c023601c4b91972aee96b37c0078406af78d0f602f920f856a663df7711c"


def verify_sources(sources: list[dict]) -> dict[str, dict]:
    if len(sources) != 2 or {source["source_sha256"] for source in sources} != SOURCE_HASHES:
        raise ValueError("Only the two frozen original development receipts are allowed")
    result = {}
    for source in sources:
        path = Path(source["source_path"])
        if sha(path) != source["source_sha256"] or path.stat().st_size != source["source_size_bytes"]:
            raise ValueError("Frozen source bytes differ")
        with Image.open(path) as image:
            size = validate_image_size(image.size)
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("Expected a single-frame original")
            with image.convert("RGB") as rgb, io.BytesIO() as stream:
                rgb.save(stream, format="PNG")
                raster_hash = hashlib.sha256(stream.getvalue()).hexdigest()
        result[source["doc_id"]] = {"image_size": list(size), "rgb_png_sha256": raster_hash}
    return result


def prepare(args) -> dict:
    if sha(args.replay_protocol) != REPLAY_PROTOCOL_SHA256:
        raise ValueError("Prior frozen replay protocol changed")
    previous = json.loads(args.replay_protocol.read_text(encoding="utf-8"))
    raster_identity = verify_sources(previous["sources"])
    schema_info = previous["schema"]
    load_confirmed_schema(Path(schema_info["path"]), schema_info["sha256"])
    config = RapidOcrConfig(args.rapidocr_python.absolute())
    output = args.output_dir.resolve()
    if any((parent / ".git").exists() for parent in (output, *output.parents)):
        raise ValueError("Raw evaluation artifacts must stay outside Git")
    code = code_receipt()
    output.mkdir(parents=True, exist_ok=False)
    schema = output / "receipt-confirmed-schema.json"
    schema.write_bytes(Path(schema_info["path"]).read_bytes())
    protocol = {
        "version": 1, "mode": "fresh_rapidocr_product_development_smoke", "code": code,
        "previous_replay_protocol_sha256": REPLAY_PROTOCOL_SHA256,
        "sources": previous["sources"], "raster_identity": raster_identity,
        "schema": {"path": str(schema), "sha256": sha(schema)},
        "provider": BASE_URL, "model": MODEL, "max_total_calls": 2,
        "max_calls_per_source": 1, "max_output_tokens": OUTPUT_TOKENS,
        "timeout_seconds": TIMEOUT_SECONDS, "sdk_retries": 0, "concurrency": 1,
        "rapidocr": {"python": str(config.python), "revision": REVISION,
                     "model_sha256": MODEL_SHA256, "timeout_s": config.timeout_s,
                     "max_rss_mib": config.max_rss_mib},
        "prepared_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "Two previously used development originals, fresh intake and isolated local OCR. "
                 "Exact prior receipt schema and unchanged product prompt, parser, grounding and review rules. "
                 "Text only; no image geometry prompt, vision, schema discovery, gold or reserved inputs. "
                 "At most one call per source. Keep both originals in denominators. Seal before offline scoring. "
                 "ORT1.31.0 replaces the prior cached diagnostic1.23.2; not an accuracy or scale claim.",
    }
    write(output / "protocol.json", protocol)
    return {"protocol_sha256": sha(output / "protocol.json"), "sources_verified": 2,
            "code_commit": code["commit"], "max_model_calls": 2}


def verify_ocr_result(sidecar: dict, source: dict, raster_identity: dict) -> dict:
    if sidecar["source_sha256"] != source["source_sha256"]:
        raise ValueError("Product source identity differs")
    if len(sidecar["pages"]) != 1 or len(sidecar["ocr_pages"]) != 1:
        raise ValueError("Expected one original receipt page")
    page, ocr = sidecar["pages"][0], sidecar["ocr_pages"][0]
    if ocr["engine"] != "rapidocr" or ocr["rerun_attempted"]:
        raise ValueError("Unexpected OCR path")
    if ocr["failure_reason"]:
        if sidecar["candidate"]["document_status"] != "failed":
            raise ValueError("Failed single-page OCR must not become accepted extraction")
        return {"failure": ocr["failure_reason"], "line_count": 0}
    provenance = ocr["ocr_provenance"]
    if (provenance["revision"] != REVISION or provenance["model_sha256"] != MODEL_SHA256
            or provenance["input_png_sha256"] != raster_identity["rgb_png_sha256"]
            or provenance["image_size_px"] != raster_identity["image_size"]
            or provenance["text_sha256"] != hashlib.sha256(page["text"].encode()).hexdigest()
            or any(page["text"][line["start"]:line["end"]] != line["text"] for line in ocr["ocr_lines"])):
        raise ValueError("OCR source binding or exact line offsets differ")
    return {"failure": None, "line_count": len(ocr["ocr_lines"]),
            "worker_elapsed_ms": provenance["worker_elapsed_ms"],
            "peak_tree_rss_bytes_sampled": provenance["peak_tree_rss_bytes_sampled"],
            "text_sha256": provenance["text_sha256"]}


def run(args) -> dict:
    output = args.output_dir.resolve()
    protocol_path = output / "protocol.json"
    if sha(protocol_path) != args.protocol_sha256:
        raise ValueError("Frozen protocol changed")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol["code"] != code_receipt() or protocol["model"] != MODEL:
        raise ValueError("Frozen extraction code changed")
    if verify_sources(protocol["sources"]) != protocol["raster_identity"]:
        raise ValueError("Frozen original raster differs")
    schema = load_confirmed_schema(Path(protocol["schema"]["path"]), protocol["schema"]["sha256"])
    rapid = protocol["rapidocr"]
    if rapid["revision"] != REVISION or rapid["model_sha256"] != MODEL_SHA256:
        raise ValueError("Frozen OCR model profile changed")
    write(output / "run-started.json", {"protocol_sha256": args.protocol_sha256})
    scratch = output / "scratch"
    scratch.mkdir()
    settings = {"IDPO_RAPIDOCR_PYTHON": rapid["python"],
                "IDPO_RAPIDOCR_TIMEOUT_S": str(rapid["timeout_s"]),
                "IDPO_RAPIDOCR_MAX_RSS_MIB": str(rapid["max_rss_mib"]),
                "IDPO_RAPIDOCR_WORK_DIR": str(scratch)}
    previous = {name: os.environ.get(name) for name in [*settings, "ICORE_API_KEY"]}
    client = None
    try:
        os.environ.update(settings)
        key = load_credential(args.credential_file)
        os.environ["ICORE_API_KEY"] = key
        client = OpenAICompatibleChat(base_url=BASE_URL, model=MODEL, api_key_env="ICORE_API_KEY",
                                      timeout_s=TIMEOUT_SECONDS, max_tokens=OUTPUT_TOKENS)
        os.environ.pop("ICORE_API_KEY", None)
        if client.client.max_retries != 0:
            raise ValueError("Provider retries must remain disabled")
        chat = ReplayChat(client, output, key)
        client.client._client.event_hooks["response"].append(chat.http_response)
        started, records, run_dirs = time.perf_counter(), [], []
        for index, source in enumerate(protocol["sources"], 1):
            chat.for_source(source)
            result = process_auto(source["source_path"], run_id=f"rapidocr_dev2_{index:02d}",
                                  model=chat, ocr_engine="rapidocr", confirmed_schema=schema,
                                  output_root=output / "product_runs")
            directory = Path(result["run_dir"])
            run_dirs.append(directory)
            candidate = json.loads((directory / "candidates.jsonl").read_text(encoding="utf-8"))
            sidecar = json.loads((directory / "docs" / candidate["doc_id"] / "result.json").read_text(encoding="utf-8"))
            ocr = verify_ocr_result(sidecar, source, protocol["raster_identity"][source["doc_id"]])
            # Preserve original product artifacts; this separate assessment join
            # uses the existing selected-document ID and exact source digest.
            append(output / "candidates.jsonl", {**candidate, "doc_id": source["doc_id"],
                                                   "source_sha256": source["source_sha256"]})
            record = {"selected_doc_id": source["doc_id"], "actual_doc_id": candidate["doc_id"],
                      "source_sha256": source["source_sha256"], "run_dir": str(directory),
                      "document_status": candidate["document_status"], "reason": sidecar["reason"],
                      "duration_ms": sidecar["duration_ms"], "ocr": ocr,
                      "model_calls": len(sidecar["model_calls"]),
                      "linked_cells": sum(len(row["value"]) for row in candidate["extracted_values"]
                                          if isinstance(row["value"], list))}
            records.append(record)
            append(output / "documents.jsonl", record)
            print(json.dumps({"completed": index, "status": candidate["document_status"],
                              "ocr_failure": ocr["failure"], "model_calls": chat.calls}), flush=True)
        write(output / "execution.json", verify_runs(run_dirs, min_unique=2))
        summary = {"protocol_sha256": args.protocol_sha256, "documents": records,
                   "model_calls": chat.calls, "sdk_attempts": sum(r["sdk_attempts"] or 0 for r in chat.reply_records),
                   "prompt_tokens": sum(r["prompt_tokens"] or 0 for r in chat.reply_records),
                   "completion_tokens": sum(r["completion_tokens"] or 0 for r in chat.reply_records),
                   "usage_complete": all(r["prompt_tokens"] is not None and r["completion_tokens"] is not None
                                         for r in chat.reply_records),
                   "wall_seconds": time.perf_counter() - started, "api_cost_usd": None,
                   "stop_reason": chat.stop_reason, "original_sources_verified": 2,
                   "output_sha256": {path.relative_to(output).as_posix(): sha(path)
                                     for path in output.rglob("*") if path.is_file()}}
        write(output / "summary.json", summary)
        return {key: summary[key] for key in ("model_calls", "sdk_attempts", "prompt_tokens", "completion_tokens", "wall_seconds")}
    finally:
        if client is not None:
            client.client.close()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prep = subparsers.add_parser("prepare")
    prep.add_argument("--output-dir", type=Path, required=True)
    prep.add_argument("--replay-protocol", type=Path, required=True)
    prep.add_argument("--rapidocr-python", type=Path, required=True)
    execute = subparsers.add_parser("run")
    execute.add_argument("--output-dir", type=Path, required=True)
    execute.add_argument("--protocol-sha256", required=True)
    execute.add_argument("--credential-file", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args) if args.command == "prepare" else run(args), indent=2))


if __name__ == "__main__":
    main()

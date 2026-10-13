"""Source-locked development replay: cached PP-OCRv6 text into product extraction.

This isolates downstream extraction on two previously used receipt images. It
does not execute OCR or intake and is not a fresh end-to-end product benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from idpo.core.types import AgentResult, Document, Page
from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.provider import ModelReply, OpenAICompatibleChat
from idpo.product_auto.workflow import _process_document
from product_eval.icore_capability_diagnostic import BASE_URL, load_credential
from product_eval.icore_confirmed_dev import (
    MODEL,
    OUTPUT_TOKENS,
    TIMEOUT_SECONDS,
    RecordedChat,
    append,
    code_receipt,
    sha,
    write,
)

RAW_SHA256 = "3c1322181b893cc948b0dbde6414dcf7ed9669a1609ec007b09a12e52e40a92f"
BASELINE_PROTOCOL_SHA256 = "f69920e4113b37061f22209f52e52af427006c75706dbb05dfcb7e15e3301356"
SOURCE_HASHES = {
    "28a8c9e154f9971aaae01212e395618460e610da9eca8f82d05b9b5277eb8c7c",
    "4322ab5ec4f0b1365e08af0c31288e65e8cbd2c8eb5241adfb329244acbbb30b",
}


def selected_pages(raw_path: Path, sources: list[dict]) -> dict[str, str]:
    """Require the sealed OCR cache and exactly the previously selected originals."""
    if sha(raw_path) != RAW_SHA256:
        raise ValueError("Sealed OCR cache changed")
    if len(sources) != 2 or {row["source_sha256"] for row in sources} != SOURCE_HASHES:
        raise ValueError("Replay requires the two fixed development sources")
    rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != 60 or len({row["source_sha256"] for row in rows}) != 60:
        raise ValueError("Cached development inventory is incomplete or duplicated")
    cached = {row["source_sha256"]: row for row in rows}
    texts = {}
    for source in sources:
        if sha(Path(source["source_path"])) != source["source_sha256"]:
            raise ValueError("Original source bytes changed")
        row = cached[source["source_sha256"]]
        result = row["rapidocr"]
        if row["doc_id"] != source["doc_id"] or result["failure"] or not result["lines_in_bounds"]:
            raise ValueError("Cached OCR identity or execution failed")
        text = result["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Cached OCR has no text")
        if any(text[line["start"]:line["end"]] != line["text"] for line in result["lines"]):
            raise ValueError("Cached OCR offsets changed")
        texts[source["doc_id"]] = text
    return texts


class SuppliedPageOcr:
    def run(self, payload, ctx):
        return AgentResult(artifacts={"document": payload["document"]})


class ReplayChat(RecordedChat):
    def complete_json(self, *, system: str, prompt: str) -> ModelReply:
        if self.calls >= 2:
            return ModelReply("", 0, error="local_call_budget", error_category="local_budget", sdk_attempts=0)
        return super().complete_json(system=system, prompt=prompt)


def prepare(args) -> dict:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if any((parent / ".git").exists() for parent in (output, *output.parents)):
        raise ValueError("Raw replay artifacts must stay outside Git")
    if sha(args.baseline_protocol) != BASELINE_PROTOCOL_SHA256:
        raise ValueError("Paired baseline protocol changed")
    baseline = json.loads(args.baseline_protocol.read_text(encoding="utf-8"))
    sources = [source for source in baseline["sources"] if source["family"] == "receipt"]
    texts = selected_pages(args.ocr_cache, sources)
    schema_info = baseline["schemas"]["receipt"]
    load_confirmed_schema(Path(schema_info["path"]), schema_info["sha256"])
    schema_path = output / "receipt-confirmed-schema.json"
    schema_path.write_bytes(Path(schema_info["path"]).read_bytes())
    protocol = {
        "version": 1, "mode": "cached_ocr_downstream_development_replay", "code": code_receipt(),
        "baseline_protocol_sha256": BASELINE_PROTOCOL_SHA256,
        "raw_ocr_cache": str(args.ocr_cache.resolve()), "raw_ocr_cache_sha256": RAW_SHA256,
        "sources": sources, "schema": {"path": str(schema_path), "sha256": sha(schema_path)},
        "page_text_sha256": {key: hashlib.sha256(value.encode()).hexdigest() for key, value in texts.items()},
        "model": MODEL, "provider": BASE_URL, "max_total_calls": 2, "max_calls_per_source": 1,
        "max_output_tokens": OUTPUT_TOKENS, "timeout_seconds": TIMEOUT_SECONDS,
        "sdk_retries": 0, "concurrency": 1,
        "scope": "Previously used development originals and cached full-page RapidOCR text. "
                 "Same receipt schema as baseline, unchanged extraction prompt and grounding. "
                 "No OCR inference, image geometry prompt, vision, schema discovery, gold or reserved inputs. "
                 "Not a product intake, OCR latency or generalization measurement. Keep both sources in denominator.",
    }
    write(output / "protocol.json", protocol)
    return {"protocol_sha256": sha(output / "protocol.json"), "documents": len(sources), "max_model_calls": 2}


def run(args) -> dict:
    output = args.output_dir.resolve()
    protocol_path = output / "protocol.json"
    if sha(protocol_path) != args.protocol_sha256:
        raise ValueError("Frozen replay protocol changed")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol["code"] != code_receipt() or protocol["model"] != MODEL:
        raise ValueError("Frozen replay code changed")
    texts = selected_pages(Path(protocol["raw_ocr_cache"]), protocol["sources"])
    if protocol["page_text_sha256"] != {key: hashlib.sha256(value.encode()).hexdigest() for key, value in texts.items()}:
        raise ValueError("Frozen page text changed")
    schema = load_confirmed_schema(Path(protocol["schema"]["path"]), protocol["schema"]["sha256"])
    # Exclusive attempt marker is written before creating the provider client.
    write(output / "run-started.json", {"protocol_sha256": args.protocol_sha256})
    key = load_credential(args.credential_file)
    previous = os.environ.get("ICORE_API_KEY")
    os.environ["ICORE_API_KEY"] = key
    try:
        underlying = OpenAICompatibleChat(base_url=BASE_URL, model=MODEL, api_key_env="ICORE_API_KEY",
                                          timeout_s=TIMEOUT_SECONDS, max_tokens=OUTPUT_TOKENS)
    finally:
        if previous is None:
            os.environ.pop("ICORE_API_KEY", None)
        else:
            os.environ["ICORE_API_KEY"] = previous
    chat = ReplayChat(underlying, output, key)
    underlying.client._client.event_hooks["response"].append(chat.http_response)
    results = []
    started = time.perf_counter()
    try:
        for source in protocol["sources"]:
            doc_id = source["doc_id"]
            chat.for_source(source)
            page = Page(1, texts[doc_id], metadata={"ocr_engine_used": "cached_rapidocr_ppocr_v6_small"})
            document = Document(doc_id, "scanned", source["source_path"], [page])
            candidate, sidecar = _process_document(doc_id, document, None, SuppliedPageOcr(), chat, None,
                                                   confirmed_schema=schema)
            candidate["source_sha256"] = source["source_sha256"]
            sidecar["ocr_cache_sha256"] = RAW_SHA256
            sidecar["execution_scope"] = protocol["mode"]
            append(output / "candidates.jsonl", candidate)
            write(output / f"{doc_id}-result.json", sidecar)
            record = {"doc_id": doc_id, "source_sha256": source["source_sha256"],
                      "document_status": candidate["document_status"], "reason": sidecar["reason"],
                      "source_characters": len(texts[doc_id]),
                      "linked_cells": sum(len(row["value"]) for row in candidate["extracted_values"]
                                          if isinstance(row["value"], list))}
            results.append(record)
            print(json.dumps(record), flush=True)
    finally:
        underlying.client.close()
    summary = {"protocol_sha256": args.protocol_sha256, "documents": results, "model_calls": chat.calls,
               "prompt_tokens": sum(row["prompt_tokens"] or 0 for row in chat.reply_records),
               "completion_tokens": sum(row["completion_tokens"] or 0 for row in chat.reply_records),
               "usage_complete": all(row["prompt_tokens"] is not None and row["completion_tokens"] is not None
                                     for row in chat.reply_records),
               "wall_seconds": time.perf_counter() - started, "stop_reason": chat.stop_reason,
               "api_cost_usd": None, "fresh_ocr_executions": 0}
    # Seal before a separate offline scorer is allowed to read development gold.
    summary["output_sha256"] = {path.name: sha(path) for path in output.iterdir() if path.is_file()}
    write(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prep = subparsers.add_parser("prepare")
    prep.add_argument("--output-dir", type=Path, required=True)
    prep.add_argument("--baseline-protocol", type=Path, required=True)
    prep.add_argument("--ocr-cache", type=Path, required=True)
    execute = subparsers.add_parser("run")
    execute.add_argument("--output-dir", type=Path, required=True)
    execute.add_argument("--protocol-sha256", required=True)
    execute.add_argument("--credential-file", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args) if args.command == "prepare" else run(args), indent=2))


if __name__ == "__main__":
    main()

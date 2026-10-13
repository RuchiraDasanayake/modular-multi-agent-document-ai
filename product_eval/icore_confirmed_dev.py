"""Six public development documents through confirmed-schema product extraction.

Prepare is source-only. Run makes at most one Luna 6 value call per document.
Raw sanitized provider bodies and product artifacts stay outside Git.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.provider import ModelReply, OpenAICompatibleChat
from idpo.product_auto.workflow import process_auto
from product_eval.execution import verify_runs
from product_eval.icore_capability_diagnostic import BASE_URL, load_credential
from product_eval.run_gate import _preflight_ocr

ROOT = Path(__file__).resolve().parents[1]
SOURCE_LOCK = ROOT / "product_eval/fixtures/docling_graph_v1_dev_sources.json"
SOURCE_LOCK_SHA256 = "6dae1ba273a9c5f9b68419dd61dd79bddde33cbc46092d7c9466969ea9d62ec1"
MODEL = "innobot-luna-6"
MAX_CALLS = 6
OUTPUT_TOKENS = 8192
TIMEOUT_SECONDS = 180
MAX_PROMPT_CHARS = 50000
MAX_PROMPT_BYTES = 200000
EVALUATION_OWNER = str(uuid.uuid5(uuid.NAMESPACE_URL, "docai:evaluation:icore-confirmed-dev6-v1"))

# Fixed task definitions, not target-document gold fields, values, or presence.
FIELD_DEFINITIONS = {
    "registration-form": {
        "file_date": "Date explicitly identified as filing or receipt of the registration. Do not substitute a signature date unless it is also explicitly the filing date.",
        "foreign_principle_name": "Name of the foreign principal represented by the registrant; this field ID preserves the published task spelling. Do not substitute the registered agent or signer.",
        "registrant_name": "Name of the registered organization or person identified as registrant. Do not substitute the foreign principal, signatory or preparer.",
        "registration_num": "Registration identifier assigned to the registrant, preserving letters and leading zeros; not an exhibit, page or filing number.",
        "signer_name": "Name of the person who signs the registration or declaration, when explicitly readable in source text.",
        "signer_title": "Stated position or title of the signatory who signs the registration or declaration.",
    },
    "ad-buy-form": {
        "advertiser": "Name of the advertiser or advertising client on the order; distinguish it from the agency and broadcaster.",
        "agency": "Name of the advertising agency placing the order, if separately stated.",
        "contract_num": "Advertising order or contract identifier, preserving the exact source spelling and leading zeros.",
        "flight_from": "Start date of the overall advertising flight or order period.",
        "flight_to": "End date of the overall advertising flight or order period.",
        "gross_amount": "Gross amount for the entire advertising order, not a line amount, net amount or commission.",
        "product": "Advertised product or campaign description explicitly named in the order.",
        "tv_address": "Postal address of the television station or broadcaster, not the advertiser or agency address.",
        "property": "Broadcast property or television station name explicitly associated with the advertising order.",
        "channel": "Channel or station identifier on each advertising line. Keep it aligned with the other values from that same source line.",
        "program_desc": "Program or advertising spot description on each ordered line, aligned with its own dates and amount.",
        "program_start_date": "Start date explicitly associated with each advertising line, not an unrelated overall order date.",
        "program_end_date": "End date explicitly associated with each advertising line, not an unrelated overall order date.",
        "sub_amount": "Amount charged for each advertising line or program schedule line, not the order total or unit rate.",
    },
    "receipt": {
        "total_amount": "Final total price due for the receipt, preserving the printed amount and separators.",
        "cash_amount": "Cash tendered or cash paid on the receipt, when explicitly printed.",
        "change_amount": "Change returned to the customer, when explicitly printed.",
        "subtotal_amount": "Receipt subtotal before tax or other separately stated final charges.",
        "tax_amount": "Separately printed tax amount for the receipt; not a percentage or service charge.",
        "item_name": "Name or description of each purchased menu item on its own receipt line.",
        "item_quantity": "Quantity purchased for each menu item. Keep its row aligned with the item name and line total.",
        "item_price": "Total price for each menu item line (CORD menu.price), not unit price (menu.unitprice). Keep it aligned with the same item's name and quantity.",
    },
}
LINKED = {"registration-form": set(), "ad-buy-form": {
    "channel", "program_desc", "program_start_date", "program_end_date", "sub_amount"},
    "receipt": {"item_name", "item_quantity", "item_price"}}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def append(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        output.flush()
        os.fsync(output.fileno())


def code_receipt() -> dict:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    if dirty:
        raise ValueError("A clean committed evaluation checkout is required")
    paths = subprocess.check_output(["git", "ls-files", "idpo", "product_eval"], cwd=ROOT, text=True).splitlines()
    return {"commit": commit, "python_files": {path: sha(ROOT / path) for path in paths if path.endswith(".py")}}


def environment(tesseract: str, tessdata: str, output: Path) -> dict:
    os.environ["TESSERACT_CMD"] = tesseract
    os.environ["TESSDATA_PREFIX"] = tessdata
    os.environ["IDPO_DATA_DIR"] = str(output / "runtime")
    temporary = output / "temp"
    temporary.mkdir(exist_ok=True)
    os.environ["TMP"] = os.environ["TEMP"] = str(temporary)
    tempfile.tempdir = str(temporary)
    return {"python_executable": sys.executable, "python_version": sys.version,
            "packages": {name: importlib.metadata.version(name) for name in (
                "openai", "httpx", "pypdfium2", "pypdf", "pytesseract", "pillow", "psutil", "numpy")},
            "ocr": {**_preflight_ocr(), "tesseract_sha256": sha(Path(tesseract))}}


def prepare(args: argparse.Namespace) -> dict:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any((parent / ".git").exists() for parent in (output, *output.parents)):
        raise ValueError("Raw evaluation artifacts must remain outside Git")
    if (output / "protocol.json").exists():
        raise ValueError("Protocol already exists")
    code = code_receipt()
    normalized_lock = SOURCE_LOCK.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(normalized_lock).hexdigest() != SOURCE_LOCK_SHA256:
        raise ValueError("Development source lock changed")
    lock = json.loads(normalized_lock)
    rows = []
    for path, expected in ((args.vrdu_cohort, lock["cohort_sha256"]["vrdu"]),
                           (args.cord_cohort, lock["cohort_sha256"]["cord"])):
        if sha(path) != expected:
            raise ValueError("Source cohort metadata changed")
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    by_id = {row["doc_id"]: row for row in rows}
    sources = []
    for item in lock["sources"]:
        if item["role"] != "scored":
            continue
        source = by_id[item["doc_id"]]
        path = Path(source["source_path"])
        if source["source_sha256"] != item["source_sha256"] or sha(path) != item["source_sha256"]:
            raise ValueError("Selected development original changed")
        sources.append({"family": item["family"], "doc_id": item["doc_id"], "source_path": str(path),
                        "source_sha256": item["source_sha256"], "source_size_bytes": path.stat().st_size})
    if len(sources) != 6 or len({s["source_sha256"] for s in sources}) != 6:
        raise ValueError("Exactly six distinct development originals required")
    parser_environment = environment(str(args.tesseract.resolve()), str(args.tessdata.resolve()), output)
    schemas = {}
    for family, definitions in FIELD_DEFINITIONS.items():
        identity = uuid.uuid5(uuid.NAMESPACE_URL, "docai:confirmed-development:" + family).hex
        fields = [{"field_id": key, "type": "array[object]" if key in LINKED[family] else "string",
                   "description": meaning, "example_values": [],
                   **({"group": "line_items"} if key in LINKED[family] else {})}
                  for key, meaning in definitions.items()]
        payload = {"contract_version": 1, "brief_id": "brief_" + identity, "revision": 2,
                   "audit_event_id": identity, "state": "confirmed", "owner_user_id": EVALUATION_OWNER,
                   "job_id": identity,
                   "intent": "Extract only the defined fields using exact source text. Preserve source formatting. "
                             "Use null for absent or ambiguous scalar values; do not arbitrarily choose among multiple values. "
                             "For repeated columns preserve each complete source row relation and exact supporting quotes.",
                   "fields": fields, "sample_sources": [{"file_id": s["doc_id"], "source_sha256": s["source_sha256"]}
                                                         for s in sources if s["family"] == family]}
        payload["payload_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        path = output / (family + "-confirmed-schema.json")
        write(path, payload)
        digest = sha(path)
        load_confirmed_schema(path, digest)
        schemas[family] = {"path": str(path), "sha256": digest, "field_count": len(fields)}
    protocol = {"version": 1, "mode": "supplied_schema_development_product_smoke", "code": code,
                "provider": BASE_URL, "model": MODEL, "max_total_calls": MAX_CALLS, "max_calls_per_source": 1,
                "schema_discovery_calls": 0, "sdk_retries": 0, "max_output_tokens": OUTPUT_TOKENS,
                "request_timeout_seconds": TIMEOUT_SECONDS, "max_prompt_chars": MAX_PROMPT_CHARS,
                "max_prompt_utf8_bytes": MAX_PROMPT_BYTES, "concurrency": 1,
                "ocr_call_timeout_seconds": 30, "ocr_page_budget_seconds": 120,
                "parser_environment": parser_environment, "evaluation_owner_uuid": EVALUATION_OWNER,
                "schemas": schemas, "sources": sources,
                "scope": "Existing development originals, no reserved inputs. Schemas fixed per family independent of target gold presence. "
                         "Evaluator-supplied schema, not observed human onboarding approval. Raw strings; scalar-list limitation explicit. "
                         "All six selected originals remain in denominators. No retries or substitutions. No dollar cost claim.",
                "schema_specifications": ["https://github.com/google-research-datasets/vrdu", "https://github.com/clovaai/cord"],
                "protocol_prepared_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    write(output / "protocol.json", protocol)
    return {"protocol_sha256": sha(output / "protocol.json"), "sources": sources, "parser_environment": parser_environment}


def redact(text: str, key: str) -> str:
    return re.sub(r"iba_[A-Za-z0-9_-]{20,}", "[REDACTED]", text.replace(key, "[REDACTED]"))


class RecordedChat:
    def __init__(self, underlying: OpenAICompatibleChat, output: Path, key: str):
        self.underlying, self.output, self.key = underlying, output, key
        self.model = MODEL
        self.calls = 0
        self.per_source_calls = 0
        self.source: dict | None = None
        self.stop_reason: str | None = None
        self.reply_records: list[dict] = []
        self.http_index = 0

    def http_response(self, response: Any) -> None:
        response.read()
        self.http_index += 1
        write(self.output / f"http-response-{self.http_index:02d}.json", {
            "attempt": self.calls, "http_status": response.status_code,
            "body": redact(response.text, self.key), "headers_saved": False})

    def for_source(self, source: dict) -> None:
        self.source = source
        self.per_source_calls = 0

    def complete_json(self, *, system: str, prompt: str) -> ModelReply:
        if self.source is None:
            raise ValueError("No selected source bound to this request")
        if self.stop_reason or self.calls >= MAX_CALLS or self.per_source_calls >= 1:
            return ModelReply("", 0, error="local_call_budget", error_category="local_budget", sdk_attempts=0)
        if len(prompt) > MAX_PROMPT_CHARS or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            return ModelReply("", 0, error="local_prompt_budget", error_category="local_budget", sdk_attempts=0)
        self.calls += 1
        self.per_source_calls += 1
        request = {"model": MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                   "max_tokens": OUTPUT_TOKENS}
        request_path = self.output / f"request-{self.calls:02d}.json"
        write(request_path, request)
        started = {"event": "attempt_started", "attempt": self.calls, "doc_id": self.source["doc_id"],
                   "source_sha256": self.source["source_sha256"], "phase": "values", "request_sha256": sha(request_path)}
        append(self.output / "calls.jsonl", started)
        reply = self.underlying.complete_json(system=system, prompt=prompt)
        raw = {**dataclasses.asdict(reply), "text": redact(reply.text, self.key)}
        reply_path = self.output / f"reply-{self.calls:02d}.json"
        write(reply_path, raw)
        receipt = {**started, "event": "attempt_completed", **{k: v for k, v in raw.items() if k != "text"},
                   "reply_sha256": sha(reply_path), "reply_chars": len(reply.text)}
        append(self.output / "calls.jsonl", receipt)
        self.reply_records.append(receipt)
        if reply.error_category in {"authentication", "rate_limit"} or (reply.error_category or "").startswith("transport_"):
            self.stop_reason = reply.error_category
        return reply


def run(args: argparse.Namespace) -> dict:
    output = args.output_dir.resolve()
    protocol_path = output / "protocol.json"
    if sha(protocol_path) != args.protocol_sha256:
        raise ValueError("Frozen protocol digest changed")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol["code"] != code_receipt() or protocol["model"] != MODEL:
        raise ValueError("Frozen runtime changed")
    if (output / "run-started.json").exists():
        raise ValueError("A prior attempt exists; resuming could duplicate billed requests")
    previous_environment = protocol["parser_environment"]
    current = environment(previous_environment["ocr"]["tesseract_executable"], previous_environment["ocr"]["tessdata_dir"], output)
    if current != previous_environment:
        raise ValueError("Frozen parser environment changed")
    for source in protocol["sources"]:
        if sha(Path(source["source_path"])) != source["source_sha256"]:
            raise ValueError("Source changed since protocol freeze")
    schemas = {family: load_confirmed_schema(Path(schema["path"]), schema["sha256"])
               for family, schema in protocol["schemas"].items()}
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
    chat = RecordedChat(underlying, output, key)
    # Audit HTTP response bytes before the product provider parses them. No headers
    # are persisted, and the supplied credential is redacted in every saved body.
    underlying.client._client.event_hooks["response"].append(chat.http_response)
    write(output / "run-started.json", {"protocol_sha256": args.protocol_sha256, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    results, run_dirs = [], []
    started = time.perf_counter()
    try:
        for index, source in enumerate(protocol["sources"], 1):
            chat.for_source(source)
            result = process_auto(Path(source["source_path"]), run_id=f"confirmed_dev6_{index:02d}", model=chat,
                                  confirmed_schema=schemas[source["family"]], output_root=output / "product_runs")
            run_dir = Path(result["run_dir"])
            run_dirs.append(run_dir)
            candidate = json.loads((run_dir / "candidates.jsonl").read_text(encoding="utf-8"))
            sidecar = json.loads((run_dir / "docs" / candidate["doc_id"] / "result.json").read_text(encoding="utf-8"))
            record = {"index": index, "family": source["family"], "selected_doc_id": source["doc_id"],
                      "actual_doc_id": candidate["doc_id"], "source_sha256": source["source_sha256"],
                      "document_status": candidate["document_status"], "reason": sidecar.get("reason"),
                      "run_dir": str(run_dir), "pages": len(sidecar["pages"]),
                      "source_characters": sum(len(p["text"]) for p in sidecar["pages"]),
                      "sdk_attempts": sum(c.get("sdk_attempts") or 0 for c in sidecar["model_calls"]),
                      "field_count": len(candidate["proposed_schema"]),
                      "accepted_fields": sum(v["status"] == "accepted" for v in candidate["extracted_values"]),
                      "linked_cells": sum(len(v["value"]) for v in candidate["extracted_values"]
                                          if isinstance(v["value"], list))}
            results.append(record)
            append(output / "documents.jsonl", record)
            print(json.dumps(record), flush=True)
    finally:
        underlying.client.close()
    execution = verify_runs(run_dirs, min_unique=6)
    write(output / "execution.json", execution)
    summary = {"protocol_sha256": args.protocol_sha256, "documents": results, "model_calls": chat.calls,
               "prompt_tokens": sum(r["prompt_tokens"] or 0 for r in chat.reply_records),
               "completion_tokens": sum(r["completion_tokens"] or 0 for r in chat.reply_records),
               "usage_complete": all(r["prompt_tokens"] is not None and r["completion_tokens"] is not None for r in chat.reply_records),
               "wall_seconds": time.perf_counter() - started, "stop_reason": chat.stop_reason,
               "api_cost_usd": None, "original_sources_verified": 6}
    write(output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--vrdu-cohort", type=Path, required=True)
    prepare_parser.add_argument("--cord-cohort", type=Path, required=True)
    prepare_parser.add_argument("--tesseract", type=Path, required=True)
    prepare_parser.add_argument("--tessdata", type=Path, required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--output-dir", type=Path, required=True)
    run_parser.add_argument("--protocol-sha256", required=True)
    run_parser.add_argument("--credential-file", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args) if args.command == "prepare" else run(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

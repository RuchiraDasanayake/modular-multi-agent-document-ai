"""Source-only freeze and one-shot paired development trial; never loads labels."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.provider import ModelReply, OpenAICompatibleChat
from idpo.product_auto.strict_output import parse_confirmed_strict_values_reply
from idpo.product_auto.visual_input import MAX_REQUEST_BYTES, PreparedVisualRequest
from idpo.product_auto.visual_output import parse_visual_values_reply
from idpo.product_auto.workflow import _doc_id, process_auto
from product_eval.execution import verify_result_receipts, verify_run, verify_runs
from product_eval.final_gate_freeze import (
    BASE_URL,
    MODEL,
    code_receipt,
    digest_file,
    read_json,
    runtime_receipt,
    write_new,
)
from product_eval.final_gate_ledger import GateStopped, Ledger, exclusive_run_lock
from product_eval.final_model_gate import sanitized_reply

BASELINE_SHA256 = "2900c5d167825d1924e2b90ee225f8e16007cfdc370d57d01b8be7d2404d83fa"
ARMS = {"text": "disabled", "visual": "bounded_visual_v1"}
FAMILIES = {"registration-form": 2, "ad-buy-form": 2, "receipt": 2}
MAX_CALLS, CALLS_PER_SLOT, OUTPUT_TOKENS, TIMEOUT_SECONDS = 48, 4, 8192, 180
_HEX = re.compile(r"[a-f0-9]{64}\Z")
_TEXT_SUCCESS = {"confirmed_schema_requires_review", "confirmed_schema_no_grounded_values", "long_document_scalar_conflict"}


def write_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(payload).hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> str:
    return write_bytes(path, b"".join((json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8") for row in rows))


def slot_id(arm: str, source: dict) -> str:
    return f"{arm}_{source['doc_id']}"


def trial_schedule(sources: list[dict]) -> list[dict]:
    return [{"index": index, "arm": arm, "doc_id": source["doc_id"], "slot_id": slot_id(arm, source)}
            for index, source in enumerate(sources) for arm in (("text", "visual") if index % 2 == 0 else ("visual", "text"))]


def require_interfaces() -> None:
    from idpo.product_auto.visual_workflow import PROFILE
    required = {"confirmed_schema", "response_format_profile", "long_document_profile", "visual_document_profile", "output_root"}
    if (not required <= set(inspect.signature(process_auto).parameters) or PROFILE != ARMS["visual"]
            or not hasattr(OpenAICompatibleChat, "complete_visual_json")):
        raise ValueError("The bounded visual product interface is not implemented")


def outside_git(path: Path) -> None:
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise ValueError("Private trial outputs and scratch must be outside Git")


@contextmanager
def configured_environment(python: Path, scratch: Path):
    python, scratch = python.resolve(strict=True), scratch.resolve(strict=True)
    if not python.is_file() or not scratch.is_dir():
        raise ValueError("Existing OCR interpreter and scratch directory are required")
    outside_git(scratch)
    changes = {"IDPO_RAPIDOCR_PYTHON": str(python), "IDPO_RAPIDOCR_WORK_DIR": str(scratch),
               "TEMP": str(scratch), "TMP": str(scratch)}
    previous = {key: os.environ.get(key) for key in changes}
    previous_temp = tempfile.tempdir
    os.environ.update(changes)
    tempfile.tempdir = str(scratch)
    try:
        yield
    finally:
        tempfile.tempdir = previous_temp
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def verify_sources(sources: list[dict]) -> None:
    if len(sources) != 6 or Counter(source["family"] for source in sources) != FAMILIES:
        raise ValueError("The exact paired six-source family allocation is required")
    if len({source["doc_id"] for source in sources}) != 6 or len({source["source_sha256"] for source in sources}) != 6:
        raise ValueError("Six distinct originals and IDs are required")
    for source in sources:
        path = Path(source["source_path"])
        if (not path.is_absolute() or path.is_symlink() or path.suffix.lower() not in {".pdf", ".png"}
                or path.stat().st_size != source["source_size_bytes"] or digest_file(path) != source["source_sha256"]
                or _doc_id(path.name, source["source_sha256"], 0) != source["doc_id"]):
            raise ValueError("Selected original bytes or intake identity changed")


def prepare(baseline_protocol: Path, output: Path, *, rapidocr_python: Path, scratch: Path) -> str:
    require_interfaces()
    output = output.resolve()
    outside_git(output)
    if output.exists():
        raise ValueError("Choose a new private output directory")
    if digest_file(baseline_protocol) != BASELINE_SHA256:
        raise ValueError("The required development baseline protocol changed")
    baseline = read_json(baseline_protocol)
    keys = ("family", "doc_id", "source_path", "source_sha256", "source_size_bytes")
    sources = [{key: row[key] for key in keys} for row in baseline["sources"]]
    verify_sources(sources)
    if set(baseline["schemas"]) != set(FAMILIES):
        raise ValueError("The three fixed family schemas are required")
    schemas = {}
    for family, item in baseline["schemas"].items():
        load_confirmed_schema(Path(item["path"]), item["sha256"])
        schemas[family] = {"path": f"schemas/{family}.json", "sha256": item["sha256"]}
    code = code_receipt()
    with configured_environment(rapidocr_python, scratch):
        runtime = runtime_receipt()  # Metadata and model-file hashes; no OCR.
    protocol = {
        "version": 1, "mode": "paired_product_candidate_development", "baseline_protocol_sha256": BASELINE_SHA256,
        "code": code, "driver_sha256": digest_file(Path(__file__)), "runtime": runtime,
        "sources": sources, "schemas": schemas, "schedule": trial_schedule(sources),
        "provider": BASE_URL, "model": MODEL, "max_total_calls": MAX_CALLS, "max_calls_per_source_arm": CALLS_PER_SLOT,
        "max_output_tokens": OUTPUT_TOKENS, "request_timeout_seconds": TIMEOUT_SECONDS, "sdk_retries": 0,
        "concurrency": 1, "schema_discovery_calls": 0, "labels_opened": False,
        "ocr_engine": "rapidocr", "response_format_profile": "strict_confirmed_values_v1",
        "long_document_profile": "bounded_text_segments_v1", "arms": ARMS,
        "fresh_original_intake_and_ocr_per_arm": True, "cached_ocr_allowed": False,
        "scope": "Six development originals; fixed schemas; paired operational/value proposals; no accuracy claim before independent scoring.",
    }
    output.mkdir(parents=True, exist_ok=False)
    for family, item in baseline["schemas"].items():
        target = output / schemas[family]["path"]
        write_bytes(target, Path(item["path"]).read_bytes())
        load_confirmed_schema(target, item["sha256"])
    sha = write_new(output / "protocol.json", protocol)
    Ledger(output / "ledger.sqlite3").initialize([{"doc_id": row["slot_id"]} for row in protocol["schedule"]], sha, MAX_CALLS)
    return sha


def _redact(text: str, key: str) -> str:
    return re.sub(r"iba_[A-Za-z0-9_-]{20,}", "[REDACTED]", text.replace(key, "[REDACTED]") if key else text)


class RecordedTrial:
    def __init__(self, provider, output: Path, arm: str, source: dict, key: str):
        self.provider, self.output, self.arm, self.source, self.key = provider, output, arm, source, key
        self.model, self.max_tokens = MODEL, OUTPUT_TOKENS
        self.slot = slot_id(arm, source)
        self.ledger = Ledger(output / "ledger.sqlite3")
        self.replies: list[dict] = []
        self.receipts: list[dict] = []

    def _send(self, body: bytes, kind: str, invoke, visual_receipt=None) -> ModelReply:
        if len(body) > MAX_REQUEST_BYTES:
            self.ledger.stop("request_byte_budget")
            raise GateStopped("request_byte_budget")
        ordinal = len(self.replies) + 1
        directory = self.output / "arms" / self.arm / "requests" / self.source["doc_id"]
        request_path = directory / f"{ordinal:02d}.body.json"
        request_sha = write_bytes(request_path, body)
        request_record = {"slot_id": self.slot, "doc_id": self.source["doc_id"], "arm": self.arm,
                          "source_sha256": self.source["source_sha256"], "kind": kind,
                          "body_sha256": request_sha, "body_bytes": len(body), "visual_receipt": visual_receipt}
        write_new(directory / f"{ordinal:02d}.request.json", request_record)
        # Commit a durable marker before invoking even the provider adapter.
        attempt_id, count = self.ledger.begin_attempt(self.slot, request_sha)
        if count != ordinal:
            raise GateStopped("source_attempt_sequence_mismatch")
        started = time.monotonic()
        try:
            reply = invoke()
        except Exception:  # noqa: BLE001 - provider exceptions may contain credentials
            reply = ModelReply("", (time.monotonic() - started) * 1000,
                               error="provider_exception", error_category="provider_other", sdk_attempts=None)
        payload = sanitized_reply(reply)
        payload["text"] = _redact(payload["text"], self.key)
        if isinstance(payload.get("error"), str):
            payload["error"] = _redact(payload["error"], self.key)
        reply_path = directory / f"{ordinal:02d}.reply.json"
        reply_sha = write_new(reply_path, payload)
        self.ledger.finish_attempt(attempt_id, reply_sha, payload)
        completed = {**request_record, "attempt_id": attempt_id, "reply_sha256": reply_sha,
                     "reply_path": reply_path.relative_to(self.output).as_posix(),
                     "request_path": request_path.relative_to(self.output).as_posix(),
                     "usage": {key: value for key, value in payload.items() if key != "text"}}
        write_new(directory / f"{ordinal:02d}.completed.json", completed)
        self.receipts.append(completed)
        self.replies.append(payload)
        # This development comparison stops on the FIRST uncertain error.
        # Known bad requests stop too; repeatedly sending a rejected profile is unhelpful.
        if payload.get("error") or payload.get("error_category"):
            self.ledger.stop(payload.get("error_category") or "provider_error")
        return ModelReply(**payload)

    def complete_json(self, *, system: str, prompt: str, response_format=None) -> ModelReply:
        if not isinstance(response_format, dict) or response_format.get("type") != "json_schema":
            raise GateStopped("strict_response_required")
        body = {"model": MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "max_tokens": OUTPUT_TOKENS, "response_format": response_format}
        raw = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        return self._send(raw, "strict_text", lambda: self.provider.complete_json(system=system, prompt=prompt, response_format=response_format))

    def complete_visual_json(self, request: PreparedVisualRequest) -> ModelReply:
        if self.arm != "visual" or not isinstance(request, PreparedVisualRequest) or request.source_sha256 != self.source["source_sha256"]:
            raise GateStopped("visual_source_or_arm_mismatch")
        request.validated_body(model=MODEL, max_tokens=OUTPUT_TOKENS)
        return self._send(request.body_json, "strict_visual", lambda: self.provider.complete_visual_json(request), request.receipt())


def extraction_metrics(sidecar: dict, recorded: RecordedTrial, schema) -> dict:
    """No expected values are consulted; validity/coverage are not correctness."""
    pages, replies = sidecar["pages"], recorded.replies
    provider_ok = bool(replies) and all(not reply["error"] and not reply["refusal"] and
                                       reply["finish_reason"] == "stop" and reply["sdk_attempts"] == 1 for reply in replies)
    visual = sidecar.get("visual_document") or {}
    long = sidecar.get("long_document_coverage") or {}
    route = visual.get("route", "text")
    chars = sum(len(page["text"]) for page in pages)
    strict_count = 0
    if route == "visual":
        requests = visual.get("requests", [])
        for reply, request in zip(replies, requests):
            selected = [page for page in pages if page["page"] in request["covered_pages"]]
            strict_count += (not reply["error"] and not reply["refusal"] and reply["finish_reason"] == "stop" and
                             parse_visual_values_reply(reply["text"], schema.candidate_fields, selected) is not None)
        covered = bool(visual.get("full_source_covered") and visual.get("source_pages") and
                       visual.get("valid_pages") == visual.get("planned_pages") == visual.get("source_pages") and
                       visual.get("valid_requests") == visual.get("planned_requests") == len(replies) and
                       not visual.get("failure_reason"))
        valid = provider_ok and covered and strict_count == len(replies) and sidecar["document_status"] != "failed"
    elif long:
        strict_count = long.get("completed_segments", 0)
        covered = bool(long.get("full_source_covered") and long.get("completed_char_count") == long.get("planned_char_count") == chars
                       and long.get("planned_segments") == long.get("completed_segments") == len(replies))
        valid = provider_ok and covered and sidecar["reason"] in _TEXT_SUCCESS
    else:
        covered = bool(0 < chars <= 24_000 and len(replies) == 1)
        if provider_ok and covered:
            strict_count = int(parse_confirmed_strict_values_reply(replies[0]["text"], schema.candidate_fields, pages) is not None)
        valid = provider_ok and covered and strict_count == 1 and sidecar["reason"] in _TEXT_SUCCESS
    values = sidecar["candidate"]["extracted_values"]
    scalar_values = [value for value in values if not isinstance(value.get("value"), list)]
    cells = [cell for value in values if isinstance(value.get("value"), list) for cell in value["value"]]
    return {"route": route, "reason": sidecar["reason"], "document_status": sidecar["document_status"],
            "effective_response_format_profile": sidecar["response_format_profile"],
            "provider_finished": provider_ok, "valid_strict_calls": strict_count,
            "complete_coverage": covered, "valid_complete_extraction": bool(valid),
            "coverage_scope": "complete_source_pages" if route == "visual" else "complete_extracted_text",
            "scalar_conflicts": len(sidecar.get("scalar_conflicts") or {}),
            "non_null_scalars": sum(value.get("value") is not None for value in scalar_values),
            "accepted_scalars": sum(value.get("value") is not None and value.get("status") == "accepted" for value in scalar_values),
            "linked_cells": len(cells), "accepted_linked_cells": sum(cell.get("status") == "accepted" for cell in cells),
            "linked_cells_need_review": sum(cell.get("status") == "needs_review" for cell in cells),
            "all_null": not cells and not any(value.get("value") is not None for value in scalar_values),
            "requires_review": sidecar["document_status"] == "needs_review",
            "visual_grounding_verified": False, "page_count": len(pages), "source_characters": chars,
            "long_document_coverage": long or None, "visual_document": visual or None}


def _verify_protocol(output: Path, sha: str) -> dict:
    if not _HEX.fullmatch(sha) or digest_file(output / "protocol.json") != sha:
        raise ValueError("Frozen protocol digest changed")
    protocol = read_json(output / "protocol.json")
    if (protocol.get("version") != 1 or protocol.get("mode") != "paired_product_candidate_development"
            or protocol.get("baseline_protocol_sha256") != BASELINE_SHA256 or protocol.get("arms") != ARMS
            or protocol.get("max_total_calls") != MAX_CALLS or protocol.get("max_calls_per_source_arm") != CALLS_PER_SLOT
            or protocol.get("model") != MODEL or protocol.get("provider") != BASE_URL
            or protocol.get("max_output_tokens") != OUTPUT_TOKENS or protocol.get("request_timeout_seconds") != TIMEOUT_SECONDS
            or protocol.get("ocr_engine") != "rapidocr" or protocol.get("response_format_profile") != "strict_confirmed_values_v1"
            or protocol.get("long_document_profile") != "bounded_text_segments_v1"
            or protocol.get("sdk_retries") != 0 or protocol.get("concurrency") != 1
            or protocol.get("cached_ocr_allowed") is not False or protocol.get("fresh_original_intake_and_ocr_per_arm") is not True
            or protocol.get("schedule") != trial_schedule(protocol["sources"])):
        raise ValueError("Unsupported trial protocol")
    require_interfaces()
    if protocol["code"] != code_receipt() or protocol["driver_sha256"] != digest_file(Path(__file__)):
        raise ValueError("Clean committed code changed")
    verify_sources(protocol["sources"])
    if set(protocol["schemas"]) != set(FAMILIES):
        raise ValueError("Frozen family schema set changed")
    for family, item in protocol["schemas"].items():
        if item["path"] != f"schemas/{family}.json":
            raise ValueError("Unsafe frozen schema path")
        load_confirmed_schema(output / item["path"], item["sha256"])
    state = Ledger(output / "ledger.sqlite3").snapshot()
    if (state["settings"]["protocol_sha256"] != sha or int(state["settings"]["max_calls"]) != MAX_CALLS
            or state["settings"]["stop_reason"] or state["controls"] or state["attempts"]
            or any(row["state"] != "unstarted" for row in state["sources"])):
        raise ValueError("Ledger is not pristine; replay is forbidden")
    if [row["doc_id"] for row in state["sources"]] != [row["slot_id"] for row in protocol["schedule"]]:
        raise ValueError("Trial schedule changed")
    return protocol


def _placeholder(source: dict, reason: str) -> tuple[dict, dict]:
    candidate = {"contract_version": 1, "doc_id": source["doc_id"], "document_status": "failed",
                 "proposed_schema": [], "extracted_values": []}
    record = {"family": source["family"], "selected_doc_id": source["doc_id"], "actual_doc_id": None,
              "source_sha256": source["source_sha256"], "document_status": "failed", "reason": reason,
              "product_executed": False, "metrics": None, "sdk_attempts": 0, "run_dir": None}
    return candidate, record


def _hash_outputs(output: Path, *, skip: set[str]) -> dict:
    hashes = {}
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise ValueError("Cannot seal linked output files")
        if path.is_file() and path.name not in skip:
            hashes[path.relative_to(output).as_posix()] = digest_file(path)
    return hashes


def run(output: Path, sha: str, *, api_key_env: str = "ICORE_API_KEY") -> dict:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env) or not os.environ.get(api_key_env, "").strip():
        raise ValueError("A credential environment variable is required")
    key = os.environ[api_key_env].strip()
    output = output.resolve()
    outside_git(output)
    with exclusive_run_lock(output / "run.lock"):
        if (output / "run-started.json").exists():
            raise ValueError("Prior run-started marker exists; replay could duplicate billed requests")
        protocol = _verify_protocol(output, sha)
        config = protocol["runtime"]["ocr_config"]
        with configured_environment(Path(config["python"]), Path(config["work_dir"])):
            if runtime_receipt() != protocol["runtime"]:
                raise ValueError("Frozen parser/model runtime changed")
            # The exclusive/fsynced marker also prevents replay after a crash.
            write_new(output / "run-started.json", {"protocol_sha256": sha, "started_unix": time.time()})
            return _execute(output, protocol, key, api_key_env)


def _execute(output: Path, protocol: dict, key: str, api_key_env: str) -> dict:
    ledger = Ledger(output / "ledger.sqlite3")
    sources = {source["doc_id"]: source for source in protocol["sources"]}
    schemas = {family: load_confirmed_schema(output / item["path"], item["sha256"]) for family, item in protocol["schemas"].items()}
    results, candidates, run_dirs = {}, {}, {arm: [] for arm in ARMS}
    provider = None
    started = time.monotonic()
    try:
        provider = OpenAICompatibleChat(base_url=BASE_URL, model=MODEL, api_key_env=api_key_env,
                                        timeout_s=TIMEOUT_SECONDS, max_tokens=OUTPUT_TOKENS)
        if provider.client.max_retries != 0:
            raise ValueError("SDK retry contract changed")
        for entry in protocol["schedule"]:
            arm, source, slot = entry["arm"], sources[entry["doc_id"]], entry["slot_id"]
            if not ledger.claim(slot):
                break
            recorded = RecordedTrial(provider, output, arm, source, key)
            run_id = f"candidate_{arm}_{entry['index']:02d}"
            run_dir = output / "arms" / arm / "product_runs" / run_id
            stage = "original_verification"
            try:
                if digest_file(Path(source["source_path"])) != source["source_sha256"]:
                    raise ValueError("source_changed")
                stage = "product_execution"
                process_auto(Path(source["source_path"]), run_id=run_id, output_root=run_dir.parent,
                             model=recorded, confirmed_schema=schemas[source["family"]], ocr_engine="rapidocr",
                             response_format_profile="strict_confirmed_values_v1", long_document_profile="bounded_text_segments_v1",
                             visual_document_profile=ARMS[arm])
                stage = "product_receipt_verification"
                if verify_run(run_dir)["documents"] != 1 or verify_result_receipts([run_dir]) != 1:
                    raise ValueError("single_original_contract")
                candidate = json.loads((run_dir / "candidates.jsonl").read_text(encoding="utf-8"))
                sidecar = read_json(run_dir / "docs" / candidate["doc_id"] / "result.json")
                if (candidate["doc_id"] != source["doc_id"] or sidecar["source_sha256"] != source["source_sha256"]
                        or len(sidecar["model_calls"]) != len(recorded.replies)):
                    raise ValueError("product_source_or_call_receipt_mismatch")
                metrics = extraction_metrics(sidecar, recorded, schemas[source["family"]])
                record = {"index": entry["index"], "arm": arm, "family": source["family"], "selected_doc_id": source["doc_id"],
                          "actual_doc_id": candidate["doc_id"], "source_sha256": source["source_sha256"],
                          "document_status": candidate["document_status"], "reason": sidecar["reason"], "product_executed": True,
                          "run_dir": str(run_dir), "sdk_attempts": sum(reply["sdk_attempts"] or 0 for reply in recorded.replies),
                          "field_count": len(candidate["proposed_schema"]), "linked_cells": metrics["linked_cells"],
                          "accepted_fields": metrics["accepted_scalars"], "pages": metrics["page_count"],
                          "source_characters": metrics["source_characters"], "metrics": metrics}
                run_dirs[arm].append(run_dir)
            except Exception as exc:  # noqa: BLE001 - preserve safe failure receipts, stop the trial
                candidate, record = _placeholder(source, "local_trial_failure")
                record.update(failure_stage=stage, exception_type=type(exc).__name__, arm=arm, index=entry["index"])
                ledger.stop("local_trial_failure")
            candidates[slot], results[slot] = candidate, record
            outcome = {"record": record, "request_receipts": recorded.receipts,
                       "product_output_hashes": _hash_outputs(run_dir, skip=set()) if run_dir.exists() else {}}
            outcome_path = output / "arms" / arm / "outcomes" / f"{source['doc_id']}.json"
            outcome_path.parent.mkdir(parents=True, exist_ok=True)
            ledger.seal_source(slot, write_new(outcome_path, outcome), record["reason"])
            if ledger.snapshot()["settings"]["stop_reason"]:
                break
    except Exception as exc:  # noqa: BLE001 - initialization also needs a redacted receipt
        ledger.stop("trial_initialization_or_sealing_failed")
        write_new(output / "fatal.json", {"exception_type": type(exc).__name__})
    finally:
        if provider is not None:
            provider.client.close()
    ledger.recover_interrupted()
    state = ledger.snapshot()
    arm_summaries = {}
    for arm in ARMS:
        rows, records = [], []
        for source in protocol["sources"]:
            slot = slot_id(arm, source)
            candidate, record = (candidates[slot], results[slot]) if slot in candidates else _placeholder(source, "unattempted_after_global_stop")
            rows.append(candidate)
            records.append(record)
        arm_dir = output / "arms" / arm
        write_jsonl(arm_dir / "candidates.jsonl", rows)
        write_jsonl(arm_dir / "documents.jsonl", records)
        attempts = [item for item in state["attempts"] if item["doc_id"].startswith(arm + "_")]
        measured = [record["metrics"] for record in records if record["metrics"] is not None]
        summary = {"documents": records, "selected_originals": 6, "product_executed_originals": len(measured),
                   "model_calls": len(attempts), "model_attempted_originals": len({item["doc_id"] for item in attempts}),
                   "request_begun_originals": len({item["doc_id"] for item in attempts}),
                   "known_sdk_attempts": sum(item["sdk_attempts"] or 0 for item in attempts),
                   "known_sdk_attempt_originals": len({item["doc_id"] for item in attempts if (item["sdk_attempts"] or 0) > 0}),
                   "attempts_with_unknown_sdk_count": sum(item["sdk_attempts"] is None for item in attempts),
                   "prompt_tokens": sum(item["prompt_tokens"] or 0 for item in attempts),
                   "completion_tokens": sum(item["completion_tokens"] or 0 for item in attempts),
                   "usage_complete": all(item["prompt_tokens"] is not None and item["completion_tokens"] is not None for item in attempts),
                   "uncertain_attempts": sum(item["state"] != "replied" for item in attempts),
                   "finish_reason_counts": dict(Counter(item["finish_reason"] or "unknown" for item in attempts)),
                   "provider_error_category_counts": dict(Counter(item["error_category"] for item in attempts if item["error_category"])),
                   "refused_attempts": sum(bool(item["refusal"]) for item in attempts),
                   "provider_latency_ms": sum(item["latency_ms"] or 0 for item in attempts),
                   "valid_complete_extractions": sum(item["valid_complete_extraction"] for item in measured),
                   "all_null_originals": sum(item["all_null"] for item in measured),
                   "route_counts": dict(Counter(item["route"] for item in measured)),
                   "reason_counts": dict(Counter(record["reason"] for record in records)),
                   "execution": verify_runs(run_dirs[arm]) if run_dirs[arm] else None, "api_cost_usd": None}
        write_new(arm_dir / "summary.json", summary)
        arm_summaries[arm] = summary
    summary = {"arms": arm_summaries, "selected_originals": 6, "selected_source_arm_slots": 12,
               "model_calls": len(state["attempts"]), "stop_reason": state["settings"]["stop_reason"] or None,
               "wall_seconds": time.monotonic() - started, "labels_opened": False, "accuracy_measured": False,
               "all_product_slots_executed": len(results) == 12 and all(record["product_executed"] for record in results.values()),
               "all_slots_accounted": True, "api_cost_usd": None}
    write_new(output / "ledger-snapshot.json", state)
    write_new(output / "summary.json", summary)
    seal = {"files": _hash_outputs(output, skip={"ledger.sqlite3", "ledger.sqlite3-wal", "ledger.sqlite3-shm", "run.lock"}),
            "labels_opened": False, "all_slots_accounted": True}
    seal_sha = write_new(output / "prediction-seal.json", seal)
    return {"summary": summary, "prediction_seal_sha256": seal_sha}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("prepare")
    for flag in ("baseline-protocol", "output-dir", "rapidocr-python", "scratch-dir"):
        command.add_argument(f"--{flag}", required=True, type=Path)
    command = sub.add_parser("run")
    command.add_argument("--output-dir", required=True, type=Path)
    command.add_argument("--protocol-sha256", required=True)
    command.add_argument("--api-key-env", default="ICORE_API_KEY")
    args = parser.parse_args()
    result = ({"protocol_sha256": prepare(args.baseline_protocol, args.output_dir, rapidocr_python=args.rapidocr_python, scratch=args.scratch_dir)}
              if args.command == "prepare" else run(args.output_dir, args.protocol_sha256, api_key_env=args.api_key_env))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

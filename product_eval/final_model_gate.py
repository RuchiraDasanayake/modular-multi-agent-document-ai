"""Freeze and conservatively resume genuine model-assisted original intake runs.

No label/scoring API is imported. Private requests and sanitized ModelReply
receipts are persisted; raw HTTP error bodies and headers are never retained.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import inspect
import json
import math
import multiprocessing
import os
import re
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.provider import ModelReply, OpenAICompatibleChat
from idpo.product_auto.strict_output import parse_confirmed_strict_values_reply
from idpo.product_auto.visual_output import parse_visual_values_reply
from product_eval.execution import verify_result_receipts, verify_run
from product_eval.final_gate_freeze import (
    DEFAULT_PROFILE,
    digest_file,
    digest_json,
    freeze,
    read_json,
    verify_freeze,
    write_new,
    write_new_bytes,
)
from product_eval.final_gate_ledger import GateStopped, Ledger, exclusive_run_lock

_ERROR_CATEGORIES = {
    "authentication", "rate_limit", "provider_server", "request_rejected", "provider_http",
    "transport_timeout", "transport_connect", "transport_protocol", "transport_other",
    "provider_other", "provider_unknown", "unknown",
}
_SUCCESS_REASONS = {"confirmed_schema_requires_review", "confirmed_schema_no_grounded_values",
                    "long_document_scalar_conflict"}
_VISUAL_SUCCESS_REASONS = {"visual_values_require_review", "visual_scalar_conflict"}


def sanitized_reply(reply: ModelReply, *, credential: str | None = None) -> dict:
    payload = dataclasses.asdict(reply)
    # Provider implementations are required to sanitize too; this boundary
    # also protects the private gate receipts from an accidental future change.
    for key, value in payload.items():
        if isinstance(value, str):
            if credential:
                value = value.replace(credential, "[REDACTED]")
            payload[key] = re.sub(r"iba_[A-Za-z0-9_-]+", "[REDACTED]", value)
    if not isinstance(payload.get("text"), str):
        payload["text"] = ""
        payload["error"] = "invalid_reply_text"
    if payload.get("error") is not None and (not isinstance(payload["error"], str) or
            not re.fullmatch(r"[A-Za-z0-9_]{1,128}", payload["error"])):
        payload["error"] = "provider_error"
    category = payload.get("error_category")
    if category is not None and category not in _ERROR_CATEGORIES:
        payload["error_category"] = "provider_unknown"
    if payload.get("error") and payload.get("error_category") is None:
        payload["error_category"] = "provider_unknown"
    if payload.get("finish_reason") not in {None, "stop", "length", "content_filter", "tool_calls", "function_call"}:
        payload["finish_reason"] = "unknown"
    for key in ("prompt_tokens", "completion_tokens", "sdk_attempts"):
        if type(payload.get(key)) is not int or payload[key] < 0:
            payload[key] = None
    if type(payload.get("latency_ms")) not in (int, float) or not math.isfinite(payload["latency_ms"]):
        payload["latency_ms"] = None
    payload["refusal"] = bool(payload.get("refusal"))
    return payload


class RecordedModel:
    def __init__(self, provider, output: Path, doc_id: str, *, credential: str | None = None,
                 source_sha256: str | None = None):
        self.provider, self.output, self.doc_id = provider, output, doc_id
        self.model = provider.model
        self.max_tokens = provider.max_tokens
        self._credential = credential
        self.source_sha256 = source_sha256
        self.ledger = Ledger(output / "ledger.sqlite3")
        self.replies: list[dict] = []
        self.requests: list[dict] = []

    def complete_json(self, *, system: str, prompt: str, response_format=None) -> ModelReply:
        if not isinstance(response_format, dict) or response_format.get("type") != "json_schema":
            raise GateStopped("strict_response_required")
        request = {"model": self.model, "messages": [{"role": "system", "content": system},
                   {"role": "user", "content": prompt}], "max_tokens": self.provider.max_tokens,
                   "response_format": response_format}
        request_sha = digest_json(request)
        # Distinct workers own distinct source directories. Identical bodies
        # cannot expose another worker's not-yet-fsynced request file.
        requests = self.output / "requests" / self.doc_id
        requests.mkdir(parents=True, exist_ok=True)
        path = requests / f"{request_sha}.json"
        try:
            write_new(path, request)
        except FileExistsError:
            if digest_file(path) != request_sha:
                raise ValueError("Private request receipt changed") from None
        # No provider method can execute until the request_begun transaction
        # has committed to SQLite with synchronous=FULL.
        attempt_id, _ = self.ledger.begin_attempt(self.doc_id, request_sha)
        self.requests.append({"kind": "text", "request_sha256": request_sha})
        reply = self.provider.complete_json(system=system, prompt=prompt, response_format=response_format)
        return self._record_reply(attempt_id, reply)

    def complete_visual_json(self, request) -> ModelReply:
        from idpo.product_auto.visual_input import PreparedVisualRequest
        if not isinstance(request, PreparedVisualRequest):
            raise GateStopped("prepared_visual_request_required")
        request.validated_body(model=self.model, max_tokens=self.max_tokens)
        if self.source_sha256 is None or request.source_sha256 != self.source_sha256:
            raise GateStopped("visual_request_source_mismatch")
        request_sha = hashlib.sha256(request.body_json).hexdigest()
        request_dir = self.output / "requests" / self.doc_id
        request_dir.mkdir(parents=True, exist_ok=True)
        path = request_dir / f"{request_sha}.json"
        try:
            write_new_bytes(path, request.body_json)
        except FileExistsError:
            if digest_file(path) != request_sha:
                raise ValueError("Private visual request receipt changed") from None
        attempt_id, _ = self.ledger.begin_attempt(self.doc_id, request_sha)
        self.requests.append({"kind": "visual", "request_sha256": request_sha, "receipt": request.receipt()})
        reply = self.provider.complete_visual_json(request)
        return self._record_reply(attempt_id, reply)

    def _record_reply(self, attempt_id: int, reply: ModelReply) -> ModelReply:
        payload = sanitized_reply(reply, credential=self._credential)
        reply_dir = self.output / "replies"
        reply_dir.mkdir(exist_ok=True)
        reply_sha = write_new(reply_dir / f"{attempt_id:06d}.json", payload)
        self.ledger.finish_attempt(attempt_id, reply_sha, payload)
        self.replies.append(payload)
        return ModelReply(**payload)


def _nonempty(value) -> bool:
    if value is None or value == "" or value == [] or value == {}:
        return False
    if isinstance(value, list):
        return any(_nonempty(item) for item in value)
    if isinstance(value, dict):
        return _nonempty(value.get("value"))
    return True


def _visual_coverage(sidecar: dict, replies: list[dict], schema, requests: list[dict] | None) -> tuple[bool, bool]:
    """Bind successful page coverage to recorded requests and parse every reply."""
    try:
        receipt = sidecar["visual_document"]
        pages = sidecar["pages"]
        ids = [page["page"] for page in pages]
        sent = requests or []
        recorded = receipt["requests"]
        source_sha = sidecar["source_container_sha256"]
        if (receipt["profile"] != "bounded_visual_v1" or receipt["route"] != "visual" or
                sidecar["response_format_profile"] != "strict_visual_confirmed_values_v1" or
                receipt["failure_reason"] is not None or receipt["source_sha256"] != source_sha or
                not 1 <= len(ids) <= 48 or ids != list(range(1, len(ids) + 1)) or
                any(receipt[key] != ids for key in ("source_pages", "observed_ocr_pages", "planned_pages", "attempted_pages", "valid_pages")) or
                receipt["full_source_covered"] is not True or not 1 <= len(replies) <= 4 or
                not len(recorded) == len(sent) == len(replies) or
                any(receipt[key] != len(replies) for key in ("planned_requests", "attempted_requests", "valid_requests"))):
            return False, False
        helpers = []
        covered = []
        parsed = True
        for index, (item, request, reply) in enumerate(zip(recorded, sent, replies, strict=True)):
            helper = {key: value for key, value in item.items() if key not in {"outcome", "model_call_index", "usage"}}
            batch = item["covered_pages"]
            if (item["outcome"] != "valid" or request["kind"] != "visual" or request["receipt"] != helper or
                    item["request_sha256"] != request["request_sha256"] or
                    not re.fullmatch(r"[a-f0-9]{64}", item["request_sha256"]) or
                    type(item["request_bytes"]) is not int or not 0 < item["request_bytes"] <= 4 * 1024 * 1024 or
                    item["request_index"] != index or item["request_count"] != len(replies) or
                    item["total_pages"] != len(ids) or item["source_sha256"] != source_sha or
                    item["planned_covered_pages"] != ids or item["uncovered_pages"] != [] or
                    not 1 <= len(batch) <= 12 or [page["page"] for page in item["pages"]] != batch or
                    any(page["source_sha256"] != source_sha for page in item["pages"])):
                return False, False
            covered.extend(batch)
            helpers.append(helper)
            batch_pages = [page for page in pages if page["page"] in batch]
            parsed = parsed and parse_visual_values_reply(reply["text"], schema.candidate_fields, batch_pages) is not None
        plan_sha = hashlib.sha256(json.dumps(helpers, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=False).encode("utf-8")).hexdigest()
        complete = covered == ids and receipt["plan_sha256"] == plan_sha
        return complete, complete and parsed
    except (KeyError, TypeError, ValueError, RecursionError, OverflowError):
        return False, False


def source_metrics(sidecar: dict, replies: list[dict], schema, *, requests: list[dict] | None = None) -> dict:
    """Operational validity is intentionally separate from source correctness."""
    pages = sidecar.get("pages", [])
    chars = sum(len(page["text"]) for page in pages)
    reason = sidecar.get("reason")
    provider_ok = bool(replies) and all(
        not reply.get("error") and reply.get("error_category") is None and not reply.get("refusal") and reply.get("finish_reason") == "stop"
        and reply.get("sdk_attempts") == 1 for reply in replies
    )
    long_plan = sidecar.get("long_document_plan")
    visual = isinstance(sidecar.get("visual_document"), dict) and sidecar["visual_document"].get("route") == "visual"
    if visual:
        full_coverage, strict_parsed = _visual_coverage(sidecar, replies, schema, requests)
        strict_parsed = provider_ok and strict_parsed
    elif long_plan is not None:
        coverage = sidecar.get("long_document_coverage") or {}
        full_coverage = (
            coverage.get("full_source_covered") is True and chars > 0
            and coverage.get("source_char_count") == coverage.get("planned_char_count") == chars
            and coverage.get("completed_char_count") == chars
            and coverage.get("planned_segments") == coverage.get("completed_segments") == len(replies)
            and coverage.get("attempted_segments") == len(replies)
            and 1 <= len(replies) <= 4
        )
        # Rebuild the frozen deterministic plan and independently reparse every
        # reply. Counters or a product success reason alone are insufficient.
        from idpo.product_auto.long_document import plan_receipt, segment_pages
        from idpo.product_auto.segments import plan_segments
        rebuilt = plan_segments(pages, max_chars=24_000)
        full_coverage = full_coverage and rebuilt.supported and len(rebuilt.segments) == len(replies) and plan_receipt(rebuilt) == long_plan
        strict_parsed = bool(provider_ok and full_coverage and all(
            parse_confirmed_strict_values_reply(reply["text"], schema.candidate_fields, segment_pages(segment)) is not None
            for reply, segment in zip(replies, rebuilt.segments, strict=True)))
    else:
        full_coverage = bool(pages) and 0 < chars <= 24_000 and len(replies) == 1
        strict_parsed = bool(provider_ok and full_coverage and
                             parse_confirmed_strict_values_reply(replies[0]["text"], schema.candidate_fields, pages) is not None)
    values = sidecar.get("candidate", {}).get("extracted_values", [])
    non_null = sum(_nonempty(value.get("value")) for value in values)
    fields_complete = (len(values) == len(schema.candidate_fields) and
        {value.get("field_id") for value in values} == {field["field_id"] for field in schema.candidate_fields})
    valid = bool(strict_parsed and full_coverage and fields_complete and sidecar.get("document_status") == "needs_review"
                 and reason in (_VISUAL_SUCCESS_REASONS if visual else _SUCCESS_REASONS))
    if visual and any(value.get("status") == "accepted" or isinstance(value.get("value"), list) and
                      any(cell.get("status") == "accepted" for cell in value["value"]) for value in values):
        valid = False
    return {
        "reason": reason, "document_status": sidecar.get("document_status"), "page_count": len(pages),
        "source_text_chars": chars, "provider_finished": provider_ok,
        "strict_parsed": strict_parsed, "full_text_coverage": full_coverage if not visual else None,
        "full_visual_coverage": full_coverage if visual else None,
        "coverage_scope": "complete_source_page_images" if visual else "complete_extracted_source_text",
        "valid_full_coverage": valid,
        "non_null_fields": non_null, "accepted_non_null_fields": sum(
            _nonempty(value.get("value")) and value.get("status") == "accepted" for value in values),
        "accepted_linked_cells": sum(
            _nonempty(cell.get("value")) and cell.get("status") == "accepted"
            for value in values if isinstance(value.get("value"), list) for cell in value["value"] if isinstance(cell, dict)),
        "all_null": non_null == 0, "long_document_coverage": sidecar.get("long_document_coverage"),
        "scalar_conflict": reason in {"long_document_scalar_conflict", "visual_scalar_conflict"},
        "requires_human_review": sidecar.get("document_status") == "needs_review",
    }


def _seal_files(output: Path, run_dir: Path) -> dict[str, str]:
    hashes = {}
    if run_dir.exists():
        for path in sorted(run_dir.rglob("*")):
            if path.is_symlink():
                raise ValueError("Output symlinks cannot be sealed")
            if path.is_file():
                hashes[path.relative_to(output).as_posix()] = digest_file(path)
    return hashes


def _run_source(output_s: str, row: dict, protocol: dict, api_key_env: str) -> str:
    """One original input goes through actual product intake/OCR in a process."""
    from idpo.product_auto.workflow import process_auto
    output = Path(output_s)
    ledger = Ledger(output / "ledger.sqlite3")
    profile = protocol["profile"]
    path = Path(row["source_path"])
    run_id = f"model2000_{row['doc_id']}"
    run_dir = output / "product_runs" / run_id
    schema_item = protocol["schemas"][row["family"]]
    provider = None
    model = None
    reason = None
    failure_stage = None
    exception_type = None
    metrics = None
    started = time.monotonic()
    try:
        stage = "source_verification"
        if digest_file(path) != row["source_sha256"] or path.stat().st_size != row["source_size_bytes"]:
            raise ValueError("source_changed")
        schema = load_confirmed_schema(output / schema_item["path"], schema_item["sha256"])
        stage = "provider_initialization"
        provider = OpenAICompatibleChat(base_url=profile["base_url"], model=profile["model"],
                                        api_key_env=api_key_env, timeout_s=profile["timeout_s"],
                                        max_tokens=profile["max_tokens"])
        if provider.client.max_retries != 0:
            raise ValueError("SDK retries must be disabled")
        model = RecordedModel(provider, output, row["doc_id"], credential=os.environ.get(api_key_env),
                              source_sha256=row["source_sha256"])
        stage = "product_execution"
        visual_kwargs = ({"visual_document_profile": profile["visual_document_profile"]}
                         if "visual_document_profile" in inspect.signature(process_auto).parameters else {})
        process_auto(path, run_id=run_id, output_root=output / "product_runs", model=model,
                     ocr_engine=profile["ocr_engine"], confirmed_schema=schema,
                     response_format_profile=profile["response_format_profile"],
                     long_document_profile=profile["long_document_profile"], **visual_kwargs)
        stage = "product_receipt_verification"
        verification = verify_run(run_dir)
        if verification["documents"] != 1 or verify_result_receipts([run_dir]) != 1:
            raise ValueError("one_original_one_document_contract")
        manifest = [json.loads(line) for line in (run_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line]
        if (len(manifest) != 1 or manifest[0]["doc_id"] != row["doc_id"]
                or manifest[0]["source_sha256"] != row["source_sha256"]
                or manifest[0]["model_call_count"] != len(model.replies)):
            raise ValueError("product_receipt_mismatch")
        sidecar = read_json(run_dir / "docs" / row["doc_id"] / "result.json")
        metrics = source_metrics(sidecar, model.replies, schema, requests=model.requests)
        reason = metrics["reason"]
    except Exception as exc:  # noqa: BLE001 - isolate/redact unexpected worker failures
        # Any unexpected local failure stops dispatch. Raw exception text may
        # contain credentials/documents and is deliberately not persisted.
        reason = "worker_execution_failed"
        failure_stage = stage
        exception_type = type(exc).__name__
        ledger.stop(reason)
    finally:
        if provider is not None:
            provider.client.close()
    receipt = {"doc_id": row["doc_id"], "source_sha256": row["source_sha256"],
               "reason": reason, "duration_ms": round((time.monotonic() - started) * 1000, 3),
               "failure_stage": failure_stage, "exception_type": exception_type,
               "metrics": metrics, "output_files": _seal_files(output, run_dir)}
    receipts = output / "outcomes"
    receipts.mkdir(exist_ok=True)
    receipt_sha = write_new(receipts / f"{row['doc_id']}.json", receipt)
    ledger.seal_source(row["doc_id"], receipt_sha, reason)
    return row["doc_id"]


def _verify_existing(output: Path, snapshot: dict, protocol: dict, sha: str) -> None:
    settings = snapshot["settings"]
    if settings["protocol_sha256"] != sha or int(settings["max_calls"]) != protocol["profile"]["max_calls"]:
        raise ValueError("Ledger is not bound to this protocol")
    if [item["doc_id"] for item in snapshot["sources"]] != [item["doc_id"] for item in protocol["sources"]]:
        raise ValueError("Ledger source inventory changed")
    for source in snapshot["sources"]:
        if source["receipt_sha256"]:
            path = output / "outcomes" / f"{source['doc_id']}.json"
            if digest_file(path) != source["receipt_sha256"]:
                raise ValueError("Sealed source outcome changed")
            for name, expected in read_json(path)["output_files"].items():
                item = (output / name).resolve(strict=True)
                if not item.is_relative_to(output.resolve()) or digest_file(item) != expected:
                    raise ValueError("Sealed product artifact changed")
    for attempt in snapshot["attempts"]:
        if digest_file(output / "requests" / attempt["doc_id"] / f"{attempt['request_sha256']}.json") != attempt["request_sha256"]:
            raise ValueError("Sealed request changed")
        if attempt["reply_sha256"] and digest_file(output / "replies" / f"{attempt['attempt_id']:06d}.json") != attempt["reply_sha256"]:
            raise ValueError("Sealed model reply changed")


def summary(output: Path, protocol: dict) -> dict:
    state = Ledger(output / "ledger.sqlite3").snapshot()
    attempts, sources = state["attempts"], state["sources"]
    attempts_by_source = Counter(item["doc_id"] for item in attempts)
    metrics = []
    reasons = Counter()
    families = {}
    family_by_doc = {row["doc_id"]: row["family"] for row in protocol["sources"]}
    for item in sources:
        family = families.setdefault(family_by_doc[item["doc_id"]], Counter())
        family["selected_originals"] += 1
        family[item["state"]] += 1
        family["originals_with_request_begun"] += item["doc_id"] in attempts_by_source
        reasons[item["reason"] or item["state"]] += 1
        if item["receipt_sha256"]:
            receipt = read_json(output / "outcomes" / f"{item['doc_id']}.json")
            if receipt["metrics"] is not None:
                metrics.append((item["state"], receipt["metrics"]))
                valid_source = item["state"] == "sealed" and receipt["metrics"]["valid_full_coverage"]
                family["valid_full_coverage_originals"] += valid_source
                family["valid_full_text_coverage_originals"] += valid_source and receipt["metrics"]["coverage_scope"] == "complete_extracted_source_text"
                family["valid_full_visual_coverage_originals"] += valid_source and receipt["metrics"]["coverage_scope"] == "complete_source_page_images"
                family["non_null_originals"] += receipt["metrics"]["non_null_fields"] > 0
    valid = sum(source_state == "sealed" and item["valid_full_coverage"] for source_state, item in metrics)
    states = Counter(item["state"] for item in sources)
    tokens = {key: sum(item[key] or 0 for item in attempts) for key in ("prompt_tokens", "completion_tokens")}
    unknown_usage = sum(item["prompt_tokens"] is None or item["completion_tokens"] is None for item in attempts)
    return {
        "protocol_sha256": state["settings"]["protocol_sha256"], "selected_originals": len(sources),
        "source_states": dict(states), "request_begun_attempts": len(attempts),
        "originals_with_request_begun": len(attempts_by_source),
        "known_sdk_attempts": sum(item["sdk_attempts"] or 0 for item in attempts),
        "attempts_with_unknown_sdk_count": sum(item["sdk_attempts"] is None for item in attempts),
        "uncertain_attempts": sum(item["state"] != "replied" for item in attempts),
        "refused_attempts": sum(item["refusal"] is not None and bool(item["refusal"]) for item in attempts),
        "finish_reason_counts": dict(Counter(item["finish_reason"] or "unknown" for item in attempts)),
        "provider_error_category_counts": dict(Counter(item["error_category"] for item in attempts if item["error_category"])),
        "valid_full_coverage_originals": valid,
        "valid_full_text_coverage_originals": sum(source_state == "sealed" and item["valid_full_coverage"] and
            item["coverage_scope"] == "complete_extracted_source_text" for source_state, item in metrics),
        "valid_full_visual_coverage_originals": sum(source_state == "sealed" and item["valid_full_coverage"] and
            item["coverage_scope"] == "complete_source_page_images" for source_state, item in metrics),
        "families": {name: dict(counts) for name, counts in families.items()},
        "prediction_receipt_originals": len(metrics),
        "all_prediction_receipts_sealed": len(metrics) == len(sources) and not states["unstarted"] and not states["started"],
        "strict_parsed_originals": sum(item["strict_parsed"] for _, item in metrics),
        "all_null_originals": sum(item["all_null"] for _, item in metrics),
        "non_null_originals": sum(item["non_null_fields"] > 0 for _, item in metrics),
        "requires_human_review_originals": sum(item["requires_human_review"] for _, item in metrics),
        "scalar_conflict_originals": sum(item["scalar_conflict"] for _, item in metrics),
        "reason_counts": dict(reasons), "known_tokens": tokens, "attempts_with_unknown_usage": unknown_usage,
        "known_provider_latency_ms": sum(item["latency_ms"] or 0 for item in attempts),
        "stop_reason": state["settings"]["stop_reason"] or None,
        "operator_resume_events": state["controls"],
        "operational_gate_passed": valid == len(sources) == protocol["target_distinct_originals"]
        and not states["uncertain"] and len(attempts_by_source) == len(sources) and not state["settings"]["stop_reason"],
        "labels_opened": False, "accuracy_measured": False, "usd_cost": None,
        "coverage_scope": "text: complete extracted text; visual: complete bounded source-page images; neither proves value correctness",
    }


def _checkpoint(output: Path, protocol: dict, label: str) -> dict:
    report = summary(output, protocol)
    folder = output / "checkpoints"
    folder.mkdir(exist_ok=True)
    write_new(folder / f"{time.time_ns()}-{label}.json", report)
    return report


def run_gate(output: Path, sha: str, *, api_key_env: str, resume: bool = False, batches: int | None = None,
             acknowledge_stop: str | None = None) -> dict:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env) or not os.environ.get(api_key_env, "").strip():
        raise ValueError("A configured credential environment variable is required")
    if batches is not None and (type(batches) is not int or batches < 1):
        raise ValueError("batches must be positive")
    if acknowledge_stop is not None and not resume:
        raise ValueError("Only explicit resume can acknowledge a provider stop")
    with exclusive_run_lock(output / "run.lock"):
        # Rehash EVERY original and runtime before creating a provider or
        # launching a process, even when resuming just the last batch.
        protocol = verify_freeze(output, sha)
        ledger = Ledger(output / "ledger.sqlite3")
        snapshot = ledger.snapshot()
        _verify_existing(output, snapshot, protocol, sha)
        if not resume and any(row["state"] != "unstarted" for row in snapshot["sources"]):
            raise ValueError("This gate was started; use resume")
        if resume:
            ledger.recover_interrupted()
        if acknowledge_stop is not None:
            ledger.acknowledge_stop(acknowledge_stop)
        if ledger.snapshot()["settings"]["stop_reason"]:
            return _checkpoint(output, protocol, "stopped")
        available = {row["doc_id"] for row in ledger.snapshot()["sources"] if row["state"] == "unstarted"}
        rows = protocol["sources"]
        workers = protocol["profile"]["workers"]
        worker_protocol = {key: protocol[key] for key in ("profile", "schemas")}
        # Spawn, including on POSIX: no inherited PDFium/OpenMP runtime state.
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
            completed_batches = 0
            for start in range(0, len(rows), 25):
                batch = [row for row in rows[start:start + 25] if row["doc_id"] in available]
                if not batch:
                    continue
                waiting = iter(batch)
                pending = {}
                exhausted = False
                while pending or not exhausted:
                    while not exhausted and len(pending) < workers:
                        row = next(waiting, None)
                        if row is None:
                            exhausted = True
                            break
                        if not ledger.claim(row["doc_id"]):
                            exhausted = True
                            break
                        future = pool.submit(_run_source, str(output), row, worker_protocol, api_key_env)
                        pending[future] = row["doc_id"]
                    if pending:
                        done, _ = wait(pending, return_when=FIRST_COMPLETED)
                        for future in done:
                            pending.pop(future)
                            try:
                                future.result()
                            except Exception:  # noqa: BLE001 - broken process must stop new paid work
                                ledger.stop("worker_process_failed")
                                exhausted = True
                _checkpoint(output, protocol, f"batch-{start // 25:03d}")
                completed_batches += 1
                if ledger.snapshot()["settings"]["stop_reason"] or (batches is not None and completed_batches >= batches):
                    break
        ledger.recover_interrupted()
        result = _checkpoint(output, protocol, "end")
        # A seal lists all terminal outcomes. Incomplete interrupted sources
        # remain explicitly uncertain; the gate does not claim their success.
        if not result["source_states"].get("unstarted"):
            seal = {"summary": result, "sources": ledger.snapshot()["sources"],
                    "attempts": ledger.snapshot()["attempts"], "controls": ledger.snapshot()["controls"]}
            seals = output / "seals"
            seals.mkdir(exist_ok=True)
            write_new(seals / f"{time.time_ns()}.json", seal)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("profile", help="Print the supported initial profile; no calls")
    command = commands.add_parser("freeze", help="Freeze clean code/runtime/schema/source bytes; no OCR/API")
    for flag in ("cohort", "schema-protocol", "profile", "output"):
        command.add_argument(f"--{flag}", type=Path, required=True)
    for name in ("run", "resume"):
        command = commands.add_parser(name)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--protocol-sha256", required=True)
        command.add_argument("--api-key-env", default="ICORE_API_KEY")
        command.add_argument("--batches", type=int, help="Stop safely at this many batch boundaries")
        if name == "resume":
            command.add_argument("--acknowledge-stop", choices=["authentication", "rate_limit", "repeated_transport_failure"],
                                 help="Explicitly allow only unstarted sources after resolving this provider stop")
    args = parser.parse_args()
    if args.command == "profile":
        result = DEFAULT_PROFILE
    elif args.command == "freeze":
        result = {"protocol_sha256": freeze(args.cohort, args.schema_protocol, args.profile, args.output)}
    else:
        result = run_gate(args.output.resolve(), args.protocol_sha256, api_key_env=args.api_key_env,
                          resume=args.command == "resume", batches=args.batches,
                          acknowledge_stop=getattr(args, "acknowledge_stop", None))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Paired local JSON-object versus constrained-schema oracle-value diagnostic.

Research-only: the same frozen 12 public VRDU OCR sidecars and oracle field
IDs/types are used in both arms. Gold values and evidence are never prompted.
No production extraction path imports this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, __version__ as pydantic_version

from idpo.product_auto.workflow import MAX_MODEL_CHARS
from product_eval.contracts import ContractError, load_jsonl
from product_eval.oracle_schema_diagnostic import (
    CHAT_TOKEN_OVERHEAD,
    CONTEXT_TOKENS,
    MAX_COMPLETION_TOKENS,
    MAX_TOTAL_TOKENS,
    MODEL_ID,
    MODEL_SHA256,
    SAMPLING,
    SYSTEM_MESSAGE,
    _local_url,
    _server_base,
    evaluate_document,
    local_prompt_tokens,
    oracle_fields,
    oracle_values_prompt,
    runtime_grounding,
    selected_cohort,
    sha256_file,
    sidecar_inventory,
    verify_completed_sources,
)
from product_eval.scorer import score_records

EXPERIMENT_VERSION = 1
ARMS = ("json_object", "json_schema")
MAX_CALLS_PER_ARM = 12
SERVER_SHA256 = "4fdc1a67a8c1333429ea82186087a77db202fb588c2442dcdfa442b2182d0306"
SERVER_BUILD = "b11425-e117148a4"
LOCK_PATH = Path(__file__).resolve().parent / "fixtures" / "adr0005_qwen_twelve_sources.json"
MAX_REPLY_CHARS = 1_000_000


class _ValueItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field_id: str
    value: Any
    page: int | None = None
    quote: str | None = None


class _ValuesEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    values: list[_ValueItem]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_nonfinite(_: str) -> None:
    raise ValueError("nonfinite_number")


def _has_nonfinite(value: Any) -> bool:
    if type(value) is float:
        return not math.isfinite(value)
    if isinstance(value, list):
        return any(_has_nonfinite(item) for item in value)
    if isinstance(value, dict):
        return any(_has_nonfinite(item) for item in value.values())
    return False


def response_shape_status(text: str, field_ids: list[str]) -> str:
    """Independent structure diagnostic; product grounding still decides status."""
    if not isinstance(text, str) or len(text) > MAX_REPLY_CHARS:
        return "invalid_or_oversized_json"
    try:
        raw = json.loads(text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_nonfinite)
    except (TypeError, ValueError) as exc:
        return "duplicate_json_key" if str(exc) == "duplicate_json_key" else "invalid_json"
    if _has_nonfinite(raw):
        return "nonfinite_number"
    try:
        envelope = _ValuesEnvelope.model_validate(raw, strict=True)
    except ValidationError as exc:
        errors = exc.errors(include_input=False)
        if any(error.get("type") == "missing" and error.get("loc", ())[-1:] == ("value",) for error in errors):
            return "missing_value"
        return "invalid_envelope"
    if len(envelope.values) > len(field_ids):
        return "too_many_values"
    if any(item.field_id not in field_ids for item in envelope.values):
        return "unknown_field_id"
    if len({item.field_id for item in envelope.values}) != len(envelope.values):
        return "duplicate_field_id"
    return "valid"


def response_format(arm: str, field_ids: list[str]) -> dict[str, Any]:
    if arm == "json_object":
        return {"type": "json_object"}
    if arm != "json_schema" or not field_ids or len(field_ids) > 24 or len(set(field_ids)) != len(field_ids):
        raise ValueError("schema arm requires 1-24 unique field IDs")
    # Deliberately limited to the pinned llama.cpp b11425 supported subset.
    return {"type": "json_schema", "schema": {
        "type": "object",
        "properties": {"values": {"type": "array", "maxItems": len(field_ids), "items": {
            "type": "object",
            "properties": {
                "field_id": {"type": "string", "enum": field_ids},
                "value": {},
                "page": {"type": "integer"},
                "quote": {"type": "string"},
            },
            "required": ["field_id", "value"],
            "additionalProperties": False,
        }}},
        "required": ["values"],
        "additionalProperties": False,
    }}


def request_body(prompt: str, output_format: dict[str, Any], *, max_tokens: int = MAX_COMPLETION_TOKENS) -> dict[str, Any]:
    return {
        "model": MODEL_ID,
        "messages": [{"role": "system", "content": SYSTEM_MESSAGE}, {"role": "user", "content": prompt}],
        "response_format": output_format,
        "max_tokens": max_tokens,
        **SAMPLING,
    }


def local_completion(prompt: str, output_format: dict[str, Any], *, url: str, max_tokens: int = MAX_COMPLETION_TOKENS) -> dict[str, Any]:
    body = request_body(prompt, output_format, max_tokens=max_tokens)
    request = urllib.request.Request(
        _local_url(url), data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.load(response)
        choice = payload["choices"][0]
        usage = payload.get("usage") or {}
        return {
            "text": choice["message"].get("content", ""),
            "finish_reason": choice.get("finish_reason"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": None,
        }
    except urllib.error.HTTPError as exc:
        error = f"http_{exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        error = type(exc).__name__
    return {"text": "", "finish_reason": None, "prompt_tokens": None,
            "completion_tokens": None, "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": error}


def check_server_properties(props: dict[str, Any], model_file: Path) -> None:
    settings = props.get("default_generation_settings", {})
    if settings.get("n_ctx") != CONTEXT_TOKENS or props.get("total_slots") != 1:
        raise ContractError("local server context/slot count differs from frozen pilot")
    build = str(props.get("build_info", ""))
    if SERVER_BUILD not in build:
        raise ContractError("local server build differs from pinned b11425")
    served_path = Path(str(props.get("model_path", "")))
    if not served_path.is_absolute() or served_path.resolve() != model_file.resolve():
        raise ContractError("local server model path differs from pinned model file")


def check_local_runtime(*, server_exe: Path, model_file: Path, url: str) -> dict[str, Any]:
    _local_url(url)
    if sha256_file(server_exe) != SERVER_SHA256 or sha256_file(model_file) != MODEL_SHA256:
        raise ContractError("local server or model SHA256 differs from pinned pilot")
    with urllib.request.urlopen(_server_base(url) + "/props", timeout=10) as response:
        props = json.load(response)
    check_server_properties(props, model_file)
    return {"server_build": str(props["build_info"]), "server_sha256": SERVER_SHA256,
            "model_sha256": MODEL_SHA256, "context_tokens": CONTEXT_TOKENS, "slots": 1}


def run_conformance_probe(*, complete: Callable[[str, dict[str, Any], str], dict[str, Any]]) -> dict[str, Any]:
    # Use the exact envelope generator used for the scored arm. A simpler enum
    # probe would miss server-side rejection of the unconstrained `value` node.
    probe_format = response_format("json_schema", ["probe_field"])
    reply = complete(
        'Return {"values":[{"field_id":"wrong_field","value":"test"}]}.',
        probe_format, "probe",
    )
    try:
        parsed = json.loads(reply.get("text", ""), object_pairs_hook=_reject_duplicate_keys,
                            parse_constant=_reject_nonfinite)
    except (TypeError, ValueError):
        parsed = None
    valid_probe = (
        response_shape_status(reply.get("text", ""), ["probe_field"]) == "valid"
        and isinstance(parsed, dict)
        and len(parsed["values"]) == 1
        and parsed["values"][0]["field_id"] == "probe_field"
    )
    if reply.get("error") or reply.get("finish_reason") != "stop" or not valid_probe:
        raise ContractError("pinned server did not pass constrained-output conformance probe")
    return {"status": "passed", "reply_sha256": hashlib.sha256(reply["text"].encode("utf-8")).hexdigest(),
            "latency_ms": reply.get("latency_ms"),
            "prompt_tokens": reply.get("prompt_tokens"), "completion_tokens": reply.get("completion_tokens")}


def load_source_lock(path: Path = LOCK_PATH) -> dict[str, Any]:
    lock = json.loads(path.read_text(encoding="utf-8"))
    sources = lock.get("sources")
    if not isinstance(sources, list) or len(sources) != 12 or len({row["doc_id"] for row in sources}) != 12:
        raise ContractError("source lock must contain twelve distinct document IDs")
    return lock


def check_inventory_lock(inventory: list[dict[str, Any]], sources: list[dict[str, Any]], gold: dict[str, Any]) -> None:
    locked = {row["doc_id"]: row for row in sources}
    if len(inventory) != 12 or {item["cohort"]["doc_id"] for item in inventory} != locked.keys():
        raise ContractError("selected twelve-document cohort differs from source lock")
    if set(gold) != locked.keys():
        raise ContractError("gold document IDs differ from source lock")
    for item in inventory:
        row = item["cohort"]
        expected = locked[row["doc_id"]]
        for key in ("family", "source_sha256"):
            if row[key] != expected[key]:
                raise ContractError(f"frozen source {key} differs for {row['doc_id']}")
        if item["run_dir"] is None or item["run_dir"].name != expected["v5_run_id"]:
            raise ContractError(f"frozen v5 run differs for {row['doc_id']}")
        if item["sidecar_path"] is None or sha256_file(item["sidecar_path"]) != expected["sidecar_sha256"]:
            raise ContractError(f"frozen OCR sidecar differs for {row['doc_id']}")
        sidecar = item["sidecar"]
        assert sidecar is not None
        _, fields, _ = oracle_fields(gold[row["doc_id"]])
        prompt_hash = hashlib.sha256(oracle_values_prompt(sidecar["pages"], fields).encode("utf-8")).hexdigest()
        if item["ocr_chars"] > MAX_MODEL_CHARS:
            if expected["prompt_sha256"] is not None:
                raise ContractError(f"over-limit prompt lock differs for {row['doc_id']}")
        elif prompt_hash != expected["prompt_sha256"]:
            raise ContractError(f"frozen prompt differs for {row['doc_id']}")


def verify_inputs(*, cohort_path: Path, gold_path: Path, runs_root: Path, lock_path: Path = LOCK_PATH) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    lock = load_source_lock(lock_path)
    if sha256_file(cohort_path) != lock["cohort_sha256"] or sha256_file(gold_path) != lock["gold_sha256"]:
        raise ContractError("cohort or gold SHA256 differs from frozen source lock")
    inventory = sidecar_inventory(selected_cohort(cohort_path), runs_root)
    verify_completed_sources(inventory)
    all_gold = load_jsonl(gold_path, kind="gold")
    selected_ids = {item["cohort"]["doc_id"] for item in inventory}
    gold = {doc_id: all_gold[doc_id] for doc_id in selected_ids}
    check_inventory_lock(inventory, lock["sources"], gold)
    return inventory, gold, lock


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")


def evaluate_pairs(
    *, inventory: list[dict[str, Any]], gold: dict[str, Any], output_dir: Path,
    complete: Callable[[str, dict[str, Any], str], dict[str, Any]],
    count_tokens: Callable[[str], int],
) -> dict[str, Any]:
    """Use one attempt per eligible document and arm, retaining all failures."""
    state: dict[str, dict[str, Any]] = {
        arm: {"calls": 0, "reported_tokens": 0, "accounted_tokens": 0,
              "candidates": [], "diagnostics": []} for arm in ARMS
    }
    token_cache: dict[str, int | str] = {}
    for index, item in enumerate(inventory):
        row = item["cohort"]
        doc_id = row["doc_id"]
        sidecar = item["sidecar"]
        assert sidecar is not None
        _, supported, _ = oracle_fields(gold[doc_id])
        ids = [field["field_id"] for field in supported]
        prompt = oracle_values_prompt(sidecar["pages"], supported)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        for arm in ARMS if index % 2 == 0 else ARMS[::-1]:
            arm_state = state[arm]
            shape_status = "not_called"
            output_format = response_format(arm, ids)
            output_format_sha256 = hashlib.sha256(json.dumps(output_format, sort_keys=True).encode("utf-8")).hexdigest()

            def bounded_complete(actual_prompt: str) -> dict[str, Any]:
                nonlocal shape_status
                if actual_prompt != prompt:
                    raise ContractError("paired arms must use the identical frozen prompt")
                if prompt_hash not in token_cache:
                    try:
                        token_cache[prompt_hash] = count_tokens(actual_prompt)
                    except Exception as exc:  # noqa: BLE001 - one failed preflight stays in both score denominators
                        token_cache[prompt_hash] = f"token_preflight_{type(exc).__name__}"
                tokens = token_cache[prompt_hash]
                if type(tokens) is not int or tokens < 0:
                    shape_status = "token_preflight_error"
                    return {"text": "", "error": tokens if isinstance(tokens, str) else "invalid_token_count",
                            "finish_reason": None, "chat_attempted": False, "latency_ms": 0}
                reserved = tokens + CHAT_TOKEN_OVERHEAD + MAX_COMPLETION_TOKENS
                if reserved > CONTEXT_TOKENS:
                    shape_status = "prompt_exceeds_context"
                    return {"text": "", "error": "prompt_exceeds_context", "finish_reason": None,
                            "chat_attempted": False, "preflight_prompt_tokens": tokens, "latency_ms": 0}
                if arm_state["calls"] >= MAX_CALLS_PER_ARM or arm_state["accounted_tokens"] + reserved > MAX_TOTAL_TOKENS:
                    shape_status = "budget_exhausted"
                    return {"text": "", "error": "budget_exhausted", "finish_reason": None,
                            "chat_attempted": False, "preflight_prompt_tokens": tokens, "latency_ms": 0}
                arm_state["calls"] += 1
                try:
                    reply = complete(actual_prompt, output_format, arm)
                    if not isinstance(reply, dict):
                        raise TypeError("model adapter must return a dictionary")
                except Exception as exc:  # noqa: BLE001 - sanitize and score local adapter errors
                    reply = {"text": "", "error": type(exc).__name__, "finish_reason": None,
                             "prompt_tokens": None, "completion_tokens": None, "latency_ms": 0}
                reply["chat_attempted"] = True
                reply["prompt_sha256"] = prompt_hash
                reply["response_format_sha256"] = output_format_sha256
                reply["preflight_prompt_tokens"] = tokens
                reported = reply.get("prompt_tokens"), reply.get("completion_tokens")
                if all(type(value) is int and value >= 0 for value in reported):
                    used = reported[0] + reported[1]
                    arm_state["reported_tokens"] += used
                    arm_state["accounted_tokens"] += used
                else:
                    arm_state["accounted_tokens"] += reserved
                if reply.get("error") is None and reply.get("finish_reason") == "stop":
                    shape_status = response_shape_status(reply.get("text", ""), ids)
                else:
                    shape_status = "provider_error" if reply.get("error") else "truncated"
                _write_json(output_dir / arm / "replies" / f"{doc_id}.json", reply)
                return reply

            candidate, diagnostic = evaluate_document(
                doc_id=doc_id, pages=sidecar["pages"], gold_record=gold[doc_id], complete=bounded_complete,
            )
            call = diagnostic["model_call"]
            candidate["measurements"] = {"latency_ms": call["latency_ms"] if call else 0}
            diagnostic.update({
                "arm": arm, "family": row["family"], "source_sha256": row["source_sha256"],
                "sidecar_sha256": sha256_file(item["sidecar_path"]), "v5_run_id": item["run_dir"].name,
                "prompt_sha256": prompt_hash, "response_format_sha256": output_format_sha256,
                "response_shape_status": shape_status,
                "runtime_grounding": runtime_grounding(candidate, sidecar["pages"]),
            })
            arm_state["candidates"].append(candidate)
            arm_state["diagnostics"].append(diagnostic)
        print(json.dumps({"index": index + 1, "doc_id": doc_id,
                          "calls": {arm: state[arm]["calls"] for arm in ARMS}}), flush=True)
    reports: dict[str, Any] = {}
    for arm in ARMS:
        arm_state = state[arm]
        candidates = arm_state.pop("candidates")
        diagnostics = arm_state.pop("diagnostics")
        if len(candidates) != len(inventory) or len({item["doc_id"] for item in candidates}) != len(inventory):
            raise ContractError("paired arm did not retain every source in its candidate denominator")
        arm_dir = output_dir / arm
        _write_jsonl(arm_dir / "candidates.jsonl", candidates)
        _write_jsonl(arm_dir / "diagnostics.jsonl", diagnostics)
        score = score_records(gold, {item["doc_id"]: item for item in candidates})
        _write_json(arm_dir / "score.json", score)
        by_family = {}
        families = sorted({item["family"] for item in diagnostics})
        for family in families:
            family_ids = {item["doc_id"] for item in diagnostics if item["family"] == family}
            by_family[family] = score_records(
                {doc_id: gold[doc_id] for doc_id in family_ids},
                {item["doc_id"]: item for item in candidates if item["doc_id"] in family_ids},
            )
        reports[arm] = {
            "model_calls": arm_state["calls"], "reported_tokens": arm_state["reported_tokens"],
            "accounted_tokens": arm_state["accounted_tokens"],
            "reasons": dict(Counter(item["reason"] for item in diagnostics)),
            "response_shapes": dict(Counter(item["response_shape_status"] for item in diagnostics)),
            "candidate_sha256": sha256_file(arm_dir / "candidates.jsonl"),
            "diagnostics_sha256": sha256_file(arm_dir / "diagnostics.jsonl"),
            "score_sha256": sha256_file(arm_dir / "score.json"),
            "latency_ms_sum": round(sum(
                (item["model_call"] or {}).get("latency_ms") or 0 for item in diagnostics
            ), 3),
            "score": score, "by_family": by_family,
        }
    return reports


def run_diagnostic(
    *, cohort_path: Path, gold_path: Path, runs_root: Path, model_file: Path,
    server_exe: Path, url: str, output_dir: Path,
) -> dict[str, Any]:
    if output_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError("write raw diagnostic replies outside the repository")
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    inventory, gold, _ = verify_inputs(cohort_path=cohort_path, gold_path=gold_path, runs_root=runs_root)
    runtime = check_local_runtime(server_exe=server_exe, model_file=model_file, url=url)
    output_dir.mkdir(parents=True)
    for arm in ARMS:
        (output_dir / arm / "replies").mkdir(parents=True)
    started = datetime.now(timezone.utc)
    complete = lambda prompt, fmt, arm: local_completion(prompt, fmt, url=url, max_tokens=64 if arm == "probe" else MAX_COMPLETION_TOKENS)
    probe = run_conformance_probe(complete=complete)
    _write_json(output_dir / "conformance-probe.json", probe)
    reports = evaluate_pairs(inventory=inventory, gold=gold, output_dir=output_dir,
                             complete=complete, count_tokens=lambda prompt: local_prompt_tokens(prompt, url=url))
    receipt = {
        "experiment_version": EXPERIMENT_VERSION, "mode": "paired_oracle_schema_output_format_only",
        "started_utc": started.isoformat(), "completed_utc": datetime.now(timezone.utc).isoformat(),
        "selected_docs": 12, "eligible_docs": sum(item["ocr_chars"] <= MAX_MODEL_CHARS for item in inventory),
        "source_selection": "six lowest raw source SHA256 in each of two frozen VRDU families",
        "cohort_sha256": sha256_file(cohort_path), "gold_sha256": sha256_file(gold_path),
        "source_lock_sha256": sha256_file(LOCK_PATH), "runner_sha256": sha256_file(Path(__file__)),
        "product_parser_sha256": sha256_file(Path(__file__).resolve().parents[1] / "idpo" / "product_auto" / "logic.py"),
        "runtime": runtime, "model_id": MODEL_ID, "conformance_probe": probe,
        "pydantic_version": pydantic_version,
        "max_model_calls_per_arm": MAX_CALLS_PER_ARM, "max_total_tokens_per_arm": MAX_TOTAL_TOKENS,
        "max_completion_tokens_per_call": MAX_COMPLETION_TOKENS, "sampling": SAMPLING,
        "response_format_profile": {"json_object": "plain JSON object",
                                    "json_schema": "required-value bounded enum-field envelope; exact per-document hashes in diagnostics"},
        "arms": reports, "cloud_calls": 0, "local_compute_cost_usd": None,
        "human_review_cost_usd": None, "total_cost_usd": None,
        "scope_caveat": "Gold schema IDs/types supplied in both arms. Gold values/evidence only used for scoring. No schema-discovery or production release claim.",
        "complete": True,
    }
    _write_json(output_dir / "run.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="Verify frozen sources and sidecars without model calls")
    parser.add_argument("--run", action="store_true", help="Run paired local inference after the volume gate")
    parser.add_argument("--model-file", type=Path)
    parser.add_argument("--server-exe", type=Path)
    parser.add_argument("--model-url", default="http://127.0.0.1:18081/v1/chat/completions")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.check == args.run:
        parser.error("choose exactly one of --check or --run")
    if args.check:
        inventory, _, _ = verify_inputs(cohort_path=args.cohort, gold_path=args.gold, runs_root=args.runs_root)
        print(json.dumps({"source_lock_valid": True, "selected_docs": len(inventory),
                          "eligible_docs": sum(item["ocr_chars"] <= MAX_MODEL_CHARS for item in inventory)}))
        return 0
    if args.model_file is None or args.server_exe is None or args.output_dir is None:
        parser.error("--run requires --model-file, --server-exe and --output-dir")
    result = run_diagnostic(cohort_path=args.cohort, gold_path=args.gold, runs_root=args.runs_root,
                            model_file=args.model_file, server_exe=args.server_exe,
                            url=args.model_url, output_dir=args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir), "selected_docs": result["selected_docs"],
                      "calls": {arm: result["arms"][arm]["model_calls"] for arm in ARMS}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the frozen six-source ICORE diagnostic through product process_auto.

Raw product runs and full scorer outputs stay outside Git. This runner never
prints a credential, provider response, provider exception message, or OCR text.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

from idpo.product_auto.provider import ModelReply, OpenAICompatibleChat
from idpo.product_auto.workflow import process_auto
from product_eval.contracts import ContractError, load_jsonl
from product_eval.datasets.cord_positive_score import score_cord_positive
from product_eval.icore_capability_diagnostic import BASE_URL, load_credential
from product_eval.icore_real_dev_diagnostic import (
    CORD_COHORT_SHA256,
    CORD_GOLD_SHA256,
    GRAPH_LOCK,
    LOCK_PATH,
    MAX_OUTPUT_TOKENS,
    MAX_PROMPT_CHARS,
    MAX_PROMPT_UTF8_BYTES,
    MAX_REPORTED_TOTAL_TOKENS,
    MAX_REQUESTS,
    MODELS,
    TIMEOUT_SECONDS,
    VRDU_COHORT_SHA256,
    VRDU_GOLD_SHA256,
    VRDU_TWELVE_LOCK,
    selected_sources,
    sha256_file,
    sha256_text,
)
from product_eval.scorer import score_records

LOCK_SHA256 = "a64f14e737ae7fe2bda3a84458d996385db40b253a78175ec161a6175c82cb15"
ALIAS_PATH = Path(__file__).with_name("fixtures") / "graph_schema_aliases_v1.json"
ALIAS_SHA256 = "24950fd476469d5a433ec3ef423d005eba8ecb703e730b44a8f7f538e306bd03"
TESSERACT_SHA256 = "c66f0f12ed76f6aa455dac97684bbc86756d6a732380bee09122454cfda3f420"
ENG_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _pages_hash(pages: list[dict[str, Any]]) -> str:
    return sha256_text(json.dumps(pages, sort_keys=True, ensure_ascii=False))


def verified_inventory(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if sha256_file(args.lock) != LOCK_SHA256:
        raise ContractError("real-development source lock SHA256 differs from committed protocol")
    if sha256_file(ALIAS_PATH) != ALIAS_SHA256:
        raise ContractError("predeclared alias ontology changed")
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    files = (
        (args.vrdu_cohort, VRDU_COHORT_SHA256), (args.vrdu_gold, VRDU_GOLD_SHA256),
        (args.cord_cohort, CORD_COHORT_SHA256), (args.cord_gold, CORD_GOLD_SHA256),
        (args.cord_reserved, lock["dataset_sha256"]["cord_reserved_cohort"]),
        (VRDU_TWELVE_LOCK, lock["prior_selection_sha256"]["vrdu_twelve"]),
        (GRAPH_LOCK, lock["prior_selection_sha256"]["docling_graph_twelve"]),
    )
    for path, expected in files:
        if not path.is_file() or sha256_file(path) != expected:
            raise ContractError(f"pinned input changed: {path.name}")
    vrdu = [json.loads(line) for line in args.vrdu_cohort.read_text(encoding="utf-8").splitlines() if line.strip()]
    cord = [json.loads(line) for line in args.cord_cohort.read_text(encoding="utf-8").splitlines() if line.strip()]
    reserved = [json.loads(line) for line in args.cord_reserved.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(cord) != 60 or len(reserved) != 40:
        raise ContractError("CORD development/reserved split count changed")
    selected = selected_sources(vrdu, cord, reserved)
    by_id = {row["doc_id"]: row for row in vrdu + cord}
    if len(lock["sources"]) != 6 or len(selected) != 6:
        raise ContractError("source lock must contain six distinct documents")
    inventory: list[dict[str, Any]] = []
    for planned, pinned in zip(selected, lock["sources"], strict=True):
        for key in ("family", "selection_rank", "doc_id", "source_sha256", "run_id", "model_arms"):
            if planned[key] != pinned[key]:
                raise ContractError("source/model assignment differs from frozen lock")
        source = Path(by_id[pinned["doc_id"]]["source_path"])
        sidecar_path = args.runs_root / pinned["run_id"] / "docs" / pinned["doc_id"] / "result.json"
        if (
            not source.is_file() or sha256_file(source) != pinned["source_sha256"]
            or source.name != pinned["source_file"] or source.stat().st_size != pinned["source_size_bytes"]
            or not sidecar_path.is_file() or sha256_file(sidecar_path) != pinned["ocr_sidecar_sha256"]
            or not (args.runs_root / pinned["run_id"] / "run.json").is_file()
        ):
            raise ContractError("source or completed OCR sidecar changed after lock")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        if sidecar.get("source_sha256") != pinned["source_sha256"] or _pages_hash(sidecar["pages"]) != pinned["ocr_pages_sha256"]:
            raise ContractError("OCR text or raw-source binding changed after lock")
        inventory.append({**pinned, "source_path": source})
    return lock, inventory


class CallBudget:
    """One process-wide accounting boundary shared by both model adapters."""

    def __init__(self, ledger_path: Path):
        self.ledger_path = ledger_path
        self.attempts = 0
        self.reported_tokens = 0
        self.stop_reason: str | None = None
        self.receipts: list[dict[str, Any]] = []

    def check_before(self, *, system: str, prompt: str) -> str | None:
        if self.stop_reason is not None:
            return self.stop_reason
        if len(prompt) > MAX_PROMPT_CHARS or len(prompt.encode("utf-8")) > MAX_PROMPT_UTF8_BYTES:
            return "prompt_cap"
        if self.attempts >= MAX_REQUESTS:
            self.stop_reason = "attempt_cap"
            return self.stop_reason
        if self.reported_tokens >= MAX_REPORTED_TOTAL_TOKENS:
            self.stop_reason = "reported_token_cap"
            return self.stop_reason
        if not system or not prompt:
            return "empty_prompt"
        return None


class AuditedChat:
    """Product ChatModel wrapper: uses its unchanged no-response-format path."""

    def __init__(self, underlying: OpenAICompatibleChat, budget: CallBudget):
        self.underlying = underlying
        self.budget = budget
        self.model = underlying.model
        self.source_sha256: str | None = None
        self.doc_id: str | None = None
        self.call_index = 0

    def for_source(self, source: dict[str, Any]) -> None:
        self.source_sha256 = source["source_sha256"]
        self.doc_id = source["doc_id"]
        self.call_index = 0

    def complete_json(self, *, system: str, prompt: str) -> ModelReply:
        if self.source_sha256 is None or self.doc_id is None:
            raise RuntimeError("model call has no active source")
        phase = "schema" if self.call_index == 0 else "values"
        self.call_index += 1
        blocked = self.budget.check_before(system=system, prompt=prompt)
        if blocked:
            _append_jsonl(self.budget.ledger_path, {
                "event": "preflight_rejected", "model": self.model, "doc_id": self.doc_id,
                "source_sha256": self.source_sha256, "phase": phase, "reason": blocked,
                "prompt_chars": len(prompt), "prompt_utf8_bytes": len(prompt.encode("utf-8")),
            })
            return ModelReply(text="", latency_ms=0, error=blocked, error_category="local_budget", sdk_attempts=0)
        request = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        attempt = self.budget.attempts + 1
        started = {
            "event": "attempt_started", "attempt": attempt, "model": self.model,
            "doc_id": self.doc_id, "source_sha256": self.source_sha256, "phase": phase,
            "canonical_request_sha256": sha256_text(canonical),
            "canonical_request_bytes": len(canonical.encode("utf-8")),
            "prompt_chars": len(prompt), "prompt_utf8_bytes": len(prompt.encode("utf-8")),
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        }
        self.budget.attempts = attempt
        _append_jsonl(self.budget.ledger_path, started)
        reply = self.underlying.complete_json(system=system, prompt=prompt)
        usage_known = type(reply.prompt_tokens) is int and type(reply.completion_tokens) is int
        receipt = {
            **{key: value for key, value in started.items() if key != "event"},
            "event": "attempt_completed", "latency_ms": round(reply.latency_ms, 3),
            "finish_reason": reply.finish_reason if reply.finish_reason in {"stop", "length", "content_filter"} else "other" if reply.finish_reason else None,
            "error": reply.error, "error_category": reply.error_category,
            "sdk_attempts": reply.sdk_attempts,
            "http_status": 200 if reply.error is None else int(reply.error[5:]) if reply.error.startswith("http_") and reply.error[5:].isdigit() else None,
            "prompt_tokens": reply.prompt_tokens, "completion_tokens": reply.completion_tokens,
            "response_sha256": sha256_text(reply.text), "response_chars": len(reply.text),
            "usage_known": usage_known,
        }
        self.budget.receipts.append(receipt)
        if usage_known:
            self.budget.reported_tokens += int(reply.prompt_tokens) + int(reply.completion_tokens)
        if reply.sdk_attempts != 1:
            self.budget.stop_reason = "sdk_attempt_count_unknown"
        elif reply.error_category and reply.error_category.startswith("transport_"):
            self.budget.stop_reason = "ambiguous_transport"
        elif not usage_known:
            self.budget.stop_reason = "missing_usage"
        elif self.budget.reported_tokens > MAX_REPORTED_TOTAL_TOKENS:
            self.budget.stop_reason = "reported_token_cap_exceeded"
        receipt["reported_tokens_cumulative"] = self.budget.reported_tokens
        receipt["stop_after_call"] = self.budget.stop_reason
        _append_jsonl(self.budget.ledger_path, receipt)
        return reply


def _safe_model_clients(key: str, budget: CallBudget) -> dict[str, AuditedChat]:
    previous = os.environ.get("ICORE_API_KEY")
    os.environ["ICORE_API_KEY"] = key
    try:
        result = {
            model: AuditedChat(OpenAICompatibleChat(
                base_url=BASE_URL, model=model, api_key_env="ICORE_API_KEY",
                timeout_s=TIMEOUT_SECONDS, max_tokens=MAX_OUTPUT_TOKENS,
            ), budget)
            for model in MODELS
        }
    finally:
        if previous is None:
            os.environ.pop("ICORE_API_KEY", None)
        else:
            os.environ["ICORE_API_KEY"] = previous
    return result


def _grounding(candidate: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, int]:
    source_pages = {page["page"]: page["text"] for page in pages}
    counts = Counter()
    for field in candidate["extracted_values"]:
        entries = field["value"] if isinstance(field["value"], list) else [field]
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("status", field["status"]) != "accepted":
                continue
            kind = "linked" if isinstance(field["value"], list) else "scalar"
            counts[f"accepted_{kind}"] += 1
            evidence = entry.get("evidence")
            if not isinstance(evidence, dict):
                continue
            text = source_pages.get(evidence.get("page"), "")
            start, end = evidence.get("start"), evidence.get("end")
            if type(start) is int and type(end) is int and text[start:end] == evidence.get("quote"):
                counts[f"grounded_{kind}"] += 1
    return {key: counts[key] for key in ("accepted_scalar", "grounded_scalar", "accepted_linked", "grounded_linked")}


def _alias_schema(gold: dict[str, Any], candidates: dict[str, dict[str, Any]],
                  family: str, aliases: dict[str, Any]) -> dict[str, Any]:
    definitions = aliases[family]
    alias_to_canonical = {alias: canonical for canonical, rule in definitions.items()
                          for alias in [canonical, *rule["aliases"]]}
    totals = Counter()
    per_document = []
    for doc_id, gold_record in sorted(gold.items()):
        gold_fields = {field["field_id"]: field for field in gold_record["gold_schema"]}
        predicted = candidates.get(doc_id, {}).get("proposed_schema", [])
        matched: dict[str, dict[str, Any]] = {}
        unmatched: list[str] = []
        for field in predicted:
            canonical = alias_to_canonical.get(field["field_id"])
            if canonical in gold_fields and canonical not in matched:
                matched[canonical] = field
            else:
                unmatched.append(field["field_id"])
        linked = [field_id for field_id, field in gold_fields.items() if field["type"] == "array[object]"]
        pairs = list(combinations(linked, 2))
        pair_hits = sum(
            left in matched and right in matched
            and matched[left]["type"] == matched[right]["type"] == "array[object]"
            and bool(matched[left].get("group")) and matched[left].get("group") == matched[right].get("group")
            for left, right in pairs
        )
        totals.update(gold_fields=len(gold_fields), matched=len(matched), unmatched=len(unmatched),
                      linked_pair_total=len(pairs), linked_pair_hits=pair_hits)
        per_document.append({"doc_id": doc_id, "raw_proposed_field_ids": [item["field_id"] for item in predicted],
                             "unmatched_proposed_field_ids": unmatched, "matched_canonical_ids": sorted(matched),
                             "linked_pair_hits": pair_hits, "linked_pair_total": len(pairs)})
    return {
        "matched": totals["matched"], "gold_fields": totals["gold_fields"],
        "unmatched_proposals": totals["unmatched"],
        "recall": totals["matched"] / totals["gold_fields"] if totals["gold_fields"] else None,
        "precision": None if family == "receipt" else totals["matched"] / (totals["matched"] + totals["unmatched"]) if totals["matched"] + totals["unmatched"] else None,
        "linked_pair_hits": totals["linked_pair_hits"], "linked_pair_total": totals["linked_pair_total"],
        "per_document": per_document,
    }


def _write_subset(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def _score_all(args: argparse.Namespace, inventory: list[dict[str, Any]],
               candidate_by_model: dict[str, dict[str, dict[str, Any]]], output_dir: Path) -> dict[str, Any]:
    vrdu_gold = load_jsonl(args.vrdu_gold, kind="gold")
    cord_gold = load_jsonl(args.cord_gold, kind="gold")
    cord_cohort = {row["doc_id"]: row for row in (
        json.loads(line) for line in args.cord_cohort.read_text(encoding="utf-8").splitlines() if line.strip()
    )}
    aliases = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
    score_dir = output_dir / "scores"
    score_dir.mkdir()
    report: dict[str, Any] = {}
    for model in MODELS:
        arm = candidate_by_model[model]
        model_report: dict[str, Any] = {}
        for family in ("registration-form", "ad-buy-form", "receipt"):
            selected = [row for row in inventory if row["family"] == family and model in row["model_arms"]]
            ids = {row["doc_id"] for row in selected}
            gold_all = cord_gold if family == "receipt" else vrdu_gold
            gold = {doc_id: gold_all[doc_id] for doc_id in ids}
            candidates = {doc_id: arm[doc_id] for doc_id in ids if doc_id in arm}
            alias_score = _alias_schema(gold, candidates, family, aliases)
            if family != "receipt":
                exact = score_records(gold, candidates)
                _json(score_dir / f"{model}_{family}_full.json", exact)
                quality = {name: exact[name] for name in (
                    "documents", "schema", "values", "linked_rows", "evidence", "operations",
                )}
            else:
                subset_dir = score_dir / f"{model}_{family}"
                subset_dir.mkdir()
                _write_subset(subset_dir / "cohort.jsonl", [cord_cohort[doc_id] for doc_id in sorted(ids)])
                _write_subset(subset_dir / "gold.jsonl", [gold[doc_id] for doc_id in sorted(ids)])
                _write_subset(subset_dir / "candidates.jsonl", [candidates[doc_id] for doc_id in sorted(candidates)])
                exact = score_cord_positive(subset_dir / "cohort.jsonl", subset_dir / "gold.jsonl",
                                            subset_dir / "candidates.jsonl")
                _json(score_dir / f"{model}_{family}_full.json", exact)
                quality = {name: exact[name] for name in (
                    "source_count", "candidate_count", "missing_candidate_count",
                    "positive_scalars", "positive_linked_cells", "positive_complete_rows",
                    "exact_proposed_scalar_recall", "exact_accepted_scalar_recall",
                    "exact_proposed_cell_recall", "exact_accepted_cell_recall",
                    "exact_proposed_complete_row_recall", "exact_accepted_complete_row_recall",
                )}
            model_report[family] = {"exact": quality, "predeclared_alias_schema": alias_score}
        report[model] = model_report
    return report


def run(args: argparse.Namespace) -> dict[str, Any]:
    _, inventory = verified_inventory(args)
    if sha256_file(args.tesseract) != TESSERACT_SHA256 or sha256_file(args.tessdata_dir / "eng.traineddata") != ENG_SHA256:
        raise ContractError("Tesseract executable or English model differs from pinned local installation")
    output_dir = args.output_dir.resolve()
    if output_dir == REPOSITORY_ROOT or REPOSITORY_ROOT in output_dir.parents:
        raise ContractError("raw pilot output must remain outside the repository")
    if output_dir.exists():
        raise FileExistsError("pilot output already exists; never silently repeat billable calls")
    key = load_credential(args.credential_file)
    output_dir.mkdir(parents=True)
    ledger = CallBudget(output_dir / "calls.jsonl")
    clients = _safe_model_clients(key, ledger)
    previous_tesseract = os.environ.get("TESSERACT_CMD")
    previous_tessdata = os.environ.get("TESSDATA_PREFIX")
    os.environ["TESSERACT_CMD"] = str(args.tesseract.resolve())
    os.environ["TESSDATA_PREFIX"] = str(args.tessdata_dir.resolve())
    _json(output_dir / "preflight.json", {
        "source_lock_sha256": LOCK_SHA256, "source_count": len(inventory),
        "planned_document_model_cells": sum(len(row["model_arms"]) for row in inventory),
        "tesseract_sha256": TESSERACT_SHA256, "eng_traineddata_sha256": ENG_SHA256,
        "max_attempts": MAX_REQUESTS, "max_output_tokens": MAX_OUTPUT_TOKENS,
        "max_prompt_chars": MAX_PROMPT_CHARS, "max_prompt_utf8_bytes": MAX_PROMPT_UTF8_BYTES,
        "max_reported_total_tokens": MAX_REPORTED_TOTAL_TOKENS,
        "sdk_retries": 0, "api_cost_usd": None,
    })
    candidate_by_model: dict[str, dict[str, dict[str, Any]]] = {model: {} for model in MODELS}
    source_results: list[dict[str, Any]] = []
    try:
        for model in MODELS:
            for source in inventory:
                if model not in source["model_arms"] or ledger.stop_reason:
                    continue
                chat = clients[model]
                chat.for_source(source)
                run_id = f"icoredev_{'luna' if model == MODELS[0] else 'sonnet'}_{source['doc_id'][:12]}"
                try:
                    outcome = process_auto(source["source_path"], run_id=run_id, model=chat,
                                           output_root=output_dir / "product_runs")
                    run_dir = Path(outcome["run_dir"])
                    candidate = load_jsonl(run_dir / "candidates.jsonl", kind="candidate")[source["doc_id"]]
                    sidecar = json.loads((run_dir / "docs" / source["doc_id"] / "result.json").read_text(encoding="utf-8"))
                    candidate_by_model[model][source["doc_id"]] = candidate
                    pages = sidecar.get("pages", [])
                    result = {
                        "model": model, "family": source["family"], "doc_id": source["doc_id"],
                        "source_sha256": source["source_sha256"], "run_id": run_id,
                        "document_status": candidate["document_status"], "reason": sidecar.get("reason"),
                        "model_call_count": len(sidecar.get("model_calls", [])),
                        "fresh_ocr_pages_sha256": _pages_hash(pages),
                        "fresh_ocr_matches_prior": _pages_hash(pages) == source["ocr_pages_sha256"],
                        "fresh_ocr_chars": sum(len(page.get("text", "")) for page in pages),
                        "raw_proposed_field_ids": [field["field_id"] for field in candidate["proposed_schema"]],
                        "source_grounding": _grounding(candidate, pages),
                    }
                except Exception as exc:  # noqa: BLE001 - preserve failed document in denominator
                    result = {
                        "model": model, "family": source["family"], "doc_id": source["doc_id"],
                        "source_sha256": source["source_sha256"], "run_id": run_id,
                        "document_status": "no_output", "reason": type(exc).__name__,
                        "model_call_count": chat.call_index,
                    }
                source_results.append(result)
                _append_jsonl(output_dir / "document_results.jsonl", result)
                print(f"{model} {source['family']} {result['document_status']} calls={result['model_call_count']}", flush=True)
                if ledger.stop_reason:
                    print(f"Pilot stopped after ambiguous/budget event: {ledger.stop_reason}", flush=True)
                    break
            if ledger.stop_reason:
                break
    finally:
        if previous_tesseract is None:
            os.environ.pop("TESSERACT_CMD", None)
        else:
            os.environ["TESSERACT_CMD"] = previous_tesseract
        if previous_tessdata is None:
            os.environ.pop("TESSDATA_PREFIX", None)
        else:
            os.environ["TESSDATA_PREFIX"] = previous_tessdata
    scores = _score_all(args, inventory, candidate_by_model, output_dir)
    planned_cells = [
        {"model": model, "family": source["family"], "doc_id": source["doc_id"],
         "source_sha256": source["source_sha256"]}
        for model in MODELS for source in inventory if model in source["model_arms"]
    ]
    completed_ids = {(row["model"], row["doc_id"]) for row in source_results}
    summary = {
        "report_version": 1,
        "source_lock_sha256": LOCK_SHA256,
        "source_count": len(inventory), "planned_document_model_cells": len(planned_cells),
        "completed_document_model_cells": len(source_results),
        "unattempted_cells": [row for row in planned_cells if (row["model"], row["doc_id"]) not in completed_ids],
        "attempted_chat_requests": ledger.attempts, "request_cap": MAX_REQUESTS,
        "reported_total_tokens": ledger.reported_tokens,
        "reported_token_cap": MAX_REPORTED_TOTAL_TOKENS,
        "stop_reason": ledger.stop_reason,
        "api_cost_usd": None, "pricing_verified": False,
        "calls": ledger.receipts, "sources": source_results,
        "scores": scores,
        "raw_output_dir": str(output_dir),
    }
    _json(output_dir / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=LOCK_PATH)
    parser.add_argument("--vrdu-cohort", type=Path, required=True)
    parser.add_argument("--vrdu-gold", type=Path, required=True)
    parser.add_argument("--cord-cohort", type=Path, required=True)
    parser.add_argument("--cord-gold", type=Path, required=True)
    parser.add_argument("--cord-reserved", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--tesseract", type=Path, required=True)
    parser.add_argument("--tessdata-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    print(f"ICORE public pilot: {result['attempted_chat_requests']} attempts, stop={result['stop_reason']}, cost unknown")


if __name__ == "__main__":
    main()

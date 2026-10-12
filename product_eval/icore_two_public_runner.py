"""Bounded two-public-PDF ICORE diagnostic through the unchanged product path.

Raw product artifacts and full scores stay outside Git. This module prints no
credential, prompt, OCR text, model reply, provider message, or document data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from idpo.product_auto.provider import ModelReply, OpenAICompatibleChat
from idpo.product_auto.workflow import process_auto
from product_eval.contracts import ContractError, load_jsonl
from product_eval.icore_capability_diagnostic import BASE_URL, load_credential
from product_eval.icore_real_dev_diagnostic import (
    MAX_OUTPUT_TOKENS,
    MAX_PROMPT_CHARS,
    MAX_PROMPT_UTF8_BYTES,
    MAX_REPORTED_TOTAL_TOKENS,
    TIMEOUT_SECONDS,
    VRDU_COHORT_SHA256,
    VRDU_GOLD_SHA256,
    sha256_file,
)
from product_eval.icore_real_dev_runner import (
    ENG_SHA256,
    TESSERACT_SHA256,
    AuditedChat,
    CallBudget,
    _grounding,
    _json,
    _pages_hash,
)
from product_eval.scorer import score_records

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = Path(__file__).with_name("fixtures") / "icore_two_public_sources_v1.json"
LOCK_SHA256 = "cfda5a748f8f5b914a9fd63558ae89f5645bd03d5490a97a023c32a8d7129556"
PARENT_LOCK = Path(__file__).with_name("fixtures") / "icore_real_dev_six_sources.json"
PARENT_LOCK_SHA256 = "a64f14e737ae7fe2bda3a84458d996385db40b253a78175ec161a6175c82cb15"
MODEL = "innobot-luna-6"
MAX_ATTEMPTS = 4
_SOURCE_FIELDS = (
    "family", "selection_rank", "doc_id", "source_sha256", "source_size_bytes",
    "source_file", "run_id", "ocr_sidecar_sha256", "ocr_pages_sha256",
)
_SCORE_FIELDS = ("documents", "schema", "values", "linked_rows", "evidence", "operations")
_SAFE_REASONS = {
    "unsupported_file_type", "file_too_large", "too_many_pages", "native_limit_exceeded",
    "parse_failed", "no_documents_parsed", "ocr_failed", "no_text_after_ocr",
    "ocr_partial_failure", "invalid_page_numbers", "document_exceeds_auto_limit",
    "too_many_detected_fields", "schema_provider_error", "invalid_schema_model_response",
    "values_provider_error", "invalid_values_model_response", "no_fields_discovered",
    "unapproved_dynamic_schema",
}


def _inside_git(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in (path, *path.parents))


def _safe_reason(reason: object) -> str | None:
    if reason is None:
        return None
    return reason if isinstance(reason, str) and reason in _SAFE_REASONS else "other"


def _canonical_lf_sha256(path: Path) -> str:
    """Hash the frozen fixture's Git text bytes on LF or CRLF checkouts."""
    raw = path.read_bytes()
    if b"\r" in raw.replace(b"\r\n", b""):
        raise ContractError("source lock has an unsupported line ending")
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


class FourCallBudget(CallBudget):
    """Tighten the earlier audited adapter's process-wide 18-call ceiling."""

    def check_before(self, *, system: str, prompt: str) -> str | None:
        if self.attempts >= MAX_ATTEMPTS:
            self.stop_reason = "attempt_cap"
            return self.stop_reason
        blocked = super().check_before(system=system, prompt=prompt)
        if blocked:
            self.stop_reason = blocked
        return blocked


class TwoCallProductChat(AuditedChat):
    """Refuse any product call beyond schema and values for one source."""

    def complete_json(self, *, system: str, prompt: str) -> ModelReply:
        if self.call_index >= 2:
            self.budget.stop_reason = "unexpected_third_product_call"
            return ModelReply(
                text="", latency_ms=0, error=self.budget.stop_reason,
                error_category="local_budget", sdk_attempts=0,
            )
        reply = super().complete_json(system=system, prompt=prompt)
        if reply.finish_reason == "length" and self.budget.stop_reason is None:
            self.budget.stop_reason = "output_truncated"
        elif reply.error is None and reply.finish_reason != "stop" and self.budget.stop_reason is None:
            self.budget.stop_reason = "nonstop_finish_reason"
        return reply


def verified_inventory(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Check all public source, sidecar, OCR, and gold hashes before key read."""
    if _canonical_lf_sha256(LOCK_PATH) != LOCK_SHA256 or sha256_file(PARENT_LOCK) != PARENT_LOCK_SHA256:
        raise ContractError("two-source or parent source lock differs from the frozen protocol")
    if sha256_file(args.vrdu_cohort) != VRDU_COHORT_SHA256 or sha256_file(args.vrdu_gold) != VRDU_GOLD_SHA256:
        raise ContractError("VRDU cohort or derived product gold differs from the frozen protocol")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    parent = json.loads(PARENT_LOCK.read_text(encoding="utf-8"))
    if (lock.get("version") != 1 or lock.get("parent_six_source_lock_sha256") != PARENT_LOCK_SHA256
            or lock.get("vrdu_cohort_sha256") != VRDU_COHORT_SHA256
            or lock.get("vrdu_gold_sha256") != VRDU_GOLD_SHA256
            or lock.get("model") != MODEL or lock.get("max_authenticated_chat_attempts") != MAX_ATTEMPTS):
        raise ContractError("two-source lock metadata differs from the frozen protocol")
    selected = lock.get("sources")
    if not isinstance(selected, list) or len(selected) != 2:
        raise ContractError("exactly two locked public sources are required")
    if [(row.get("family"), row.get("selection_rank")) for row in selected] != [
        ("registration-form", 6), ("ad-buy-form", 6),
    ]:
        raise ContractError("locked selection must contain source rank 6 from each VRDU family")
    prior = {(row["family"], row["selection_rank"]): row for row in parent["sources"]}
    # Cohort rows are metadata, not adjudicated gold; do not parse labels here.
    rows = [json.loads(line) for line in args.vrdu_cohort.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {row["doc_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ContractError("VRDU cohort has duplicate document IDs")
    inventory: list[dict[str, Any]] = []
    for item in selected:
        expected = prior.get((item["family"], item["selection_rank"]))
        if expected is None or any(item.get(key) != expected.get(key) for key in _SOURCE_FIELDS):
            raise ContractError("two-source receipt differs from its pre-existing public lock")
        cohort_row = by_id.get(item["doc_id"])
        if cohort_row is None or cohort_row.get("family") != item["family"]:
            raise ContractError("selected source is absent from its VRDU family")
        source = Path(cohort_row["source_path"])
        sidecar_path = args.runs_root / item["run_id"] / "docs" / item["doc_id"] / "result.json"
        if (not source.is_file() or source.suffix.lower() != ".pdf"
                or source.name != item["source_file"]
                or source.stat().st_size != item["source_size_bytes"]
                or sha256_file(source) != item["source_sha256"]
                or not sidecar_path.is_file()
                or sha256_file(sidecar_path) != item["ocr_sidecar_sha256"]
                or not (args.runs_root / item["run_id"] / "run.json").is_file()):
            raise ContractError("source or completed prior OCR sidecar changed")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        if sidecar.get("source_sha256") != item["source_sha256"] or _pages_hash(sidecar["pages"]) != item["ocr_pages_sha256"]:
            raise ContractError("prior OCR pages are not bound to this raw source")
        inventory.append({**item, "source_path": source})
    if len({row["source_sha256"] for row in inventory}) != 2:
        raise ContractError("the two documents must have distinct raw-source hashes")
    return inventory


def _score_two(gold_path: Path, inventory: list[dict[str, Any]],
               candidates: dict[str, dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    all_gold = load_jsonl(gold_path, kind="gold")
    reports: dict[str, Any] = {}
    for family in ("registration-form", "ad-buy-form"):
        doc_id = next(row["doc_id"] for row in inventory if row["family"] == family)
        score = score_records({doc_id: all_gold[doc_id]}, {doc_id: candidates[doc_id]} if doc_id in candidates else {})
        _json(output_dir / f"{family}_full_score.json", score)
        reports[family] = {field: score[field] for field in _SCORE_FIELDS}
    return reports


def run(args: argparse.Namespace) -> dict[str, Any]:
    inventory = verified_inventory(args)
    if (sha256_file(args.tesseract) != TESSERACT_SHA256
            or sha256_file(args.tessdata_dir / "eng.traineddata") != ENG_SHA256):
        raise ContractError("Tesseract executable or English model differs from the pinned installation")
    output_dir = args.output_dir.resolve()
    if _inside_git(output_dir):
        raise ContractError("raw pilot output must remain outside Git")
    if output_dir.exists():
        raise FileExistsError("pilot output already exists; billable calls are never silently repeated")
    if _inside_git(args.credential_file.resolve()):
        raise ContractError("credential file must remain outside Git")
    key = load_credential(args.credential_file)
    budget = FourCallBudget(output_dir / "calls.jsonl")
    old_key = os.environ.get("ICORE_API_KEY")
    os.environ["ICORE_API_KEY"] = key
    try:
        chat = TwoCallProductChat(OpenAICompatibleChat(
            base_url=BASE_URL, model=MODEL, api_key_env="ICORE_API_KEY",
            timeout_s=TIMEOUT_SECONDS, max_tokens=MAX_OUTPUT_TOKENS,
        ), budget)
    finally:
        if old_key is None:
            os.environ.pop("ICORE_API_KEY", None)
        else:
            os.environ["ICORE_API_KEY"] = old_key
    output_dir.mkdir(parents=True)
    old_tesseract = os.environ.get("TESSERACT_CMD")
    old_tessdata = os.environ.get("TESSDATA_PREFIX")
    os.environ["TESSERACT_CMD"] = str(args.tesseract.resolve())
    os.environ["TESSDATA_PREFIX"] = str(args.tessdata_dir.resolve())
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    preflight = {
        "source_lock_sha256": LOCK_SHA256,
        "parent_lock_sha256": PARENT_LOCK_SHA256,
        "product_git_commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "model": MODEL,
        "source_count": 2,
        "max_authenticated_chat_attempts": MAX_ATTEMPTS,
        "max_output_tokens_per_request": MAX_OUTPUT_TOKENS,
        "max_prompt_chars": MAX_PROMPT_CHARS,
        "max_prompt_utf8_bytes": MAX_PROMPT_UTF8_BYTES,
        "max_reported_total_tokens": MAX_REPORTED_TOTAL_TOKENS,
        "timeout_seconds_per_request": TIMEOUT_SECONDS,
        "sdk_retries": 0,
        "api_cost_usd": None,
        "compute_cost_usd": None,
    }
    _json(output_dir / "preflight.json", preflight)
    candidates: dict[str, dict[str, Any]] = {}
    source_results: list[dict[str, Any]] = []
    try:
        for source in inventory:
            if budget.stop_reason:
                break
            chat.for_source(source)
            run_id = f"icoretwo_{source['family'].replace('-', '_')}_{source['doc_id'][:12]}"
            calls_before = budget.attempts
            try:
                outcome = process_auto(
                    source["source_path"], run_id=run_id, model=chat,
                    ocr_call_timeout_s=30, ocr_page_budget_s=120,
                    output_root=output_dir / "product_runs",
                )
                run_dir = Path(outcome["run_dir"])
                candidate = load_jsonl(run_dir / "candidates.jsonl", kind="candidate")[source["doc_id"]]
                sidecar = json.loads((run_dir / "docs" / source["doc_id"] / "result.json").read_text(encoding="utf-8"))
                candidates[source["doc_id"]] = candidate
                pages = sidecar.get("pages", [])
                result = {
                    "family": source["family"], "doc_id": source["doc_id"],
                    "source_sha256": source["source_sha256"],
                    "document_status": candidate["document_status"],
                    "reason": _safe_reason(sidecar.get("reason")),
                    "authenticated_chat_attempts": budget.attempts - calls_before,
                    "fresh_ocr_pages_sha256": _pages_hash(pages),
                    "fresh_ocr_matches_prior": _pages_hash(pages) == source["ocr_pages_sha256"],
                    "fresh_ocr_chars": sum(len(page.get("text", "")) for page in pages),
                    "grounding_counts": _grounding(candidate, pages),
                }
            except Exception as exc:  # noqa: BLE001 - retain both documents in denominator
                budget.stop_reason = budget.stop_reason or "product_exception"
                result = {
                    "family": source["family"], "doc_id": source["doc_id"],
                    "source_sha256": source["source_sha256"],
                    "document_status": "no_output", "reason": type(exc).__name__,
                    "authenticated_chat_attempts": budget.attempts - calls_before,
                }
            source_results.append(result)
            _json(output_dir / f"{source['family']}_status.json", result)
            print(f"{source['family']} status={result['document_status']} calls={result['authenticated_chat_attempts']}", flush=True)
    finally:
        if old_tesseract is None:
            os.environ.pop("TESSERACT_CMD", None)
        else:
            os.environ["TESSERACT_CMD"] = old_tesseract
        if old_tessdata is None:
            os.environ.pop("TESSDATA_PREFIX", None)
        else:
            os.environ["TESSDATA_PREFIX"] = old_tessdata
    scores = _score_two(args.vrdu_gold, inventory, candidates, output_dir)
    attempted_ids = {row["doc_id"] for row in source_results}
    summary = {
        "report_version": 1,
        "source_lock_sha256": LOCK_SHA256,
        "model": MODEL,
        "source_count": 2,
        "attempted_documents": len(source_results),
        "unattempted_documents": [
            {"family": row["family"], "doc_id": row["doc_id"], "source_sha256": row["source_sha256"]}
            for row in inventory if row["doc_id"] not in attempted_ids
        ],
        "attempted_chat_requests": budget.attempts,
        "request_cap": MAX_ATTEMPTS,
        "reported_total_tokens": budget.reported_tokens,
        "stop_reason": budget.stop_reason,
        "api_cost_usd": None,
        "compute_cost_usd": None,
        "pricing_verified": False,
        "calls": budget.receipts,
        "sources": source_results,
        "scores": scores,
    }
    _json(output_dir / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--vrdu-cohort", type=Path, required=True)
    parser.add_argument("--vrdu-gold", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--tesseract", type=Path, required=True)
    parser.add_argument("--tessdata-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    print(f"ICORE two-public-PDF pilot: {result['attempted_chat_requests']} attempts; stop={result['stop_reason']}; USD unknown")


if __name__ == "__main__":
    main()

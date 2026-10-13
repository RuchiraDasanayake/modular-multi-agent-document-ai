"""Read-only verification of a terminal operational campaign; never load labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from product_eval import final_model_gate as gate
from product_eval.execution import verify_result_receipts, verify_run
from product_eval.final_gate_freeze import (
    DOC_ID,
    FAMILY_COUNTS,
    SHA,
    TARGET_SOURCES,
    digest_file,
    digest_json,
    read_json,
    validate_profile,
    write_new,
)
from product_eval.quality_scoring_verification import (
    _attempts,
    _newline_receipt,
    require,
    sealed_path,
)

FROZEN_MODULES = (
    "product_eval/final_model_gate.py", "product_eval/execution.py", "product_eval/contracts.py",
    "idpo/product_auto/confirmed_schema.py", "idpo/product_auto/strict_output.py",
    "idpo/product_auto/visual_output.py", "idpo/product_auto/logic.py",
    "idpo/product_auto/long_document.py", "idpo/product_auto/segments.py",
)
ROOT = Path(__file__).resolve().parents[1]


def _plain(path: Path) -> Path:
    require(path.is_absolute(), "Absolute path required")
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            require(not part.is_symlink() and not getattr(part.lstat(), "st_file_attributes", 0) & 0x400,
                    "Reparse points are unsupported")
    return path


def _artifact(root: Path, name: str, expected: str, verified: dict) -> Path:
    require(isinstance(expected, str) and bool(SHA.fullmatch(expected)), "Invalid artifact hash")
    path = _plain(sealed_path(root, name))
    require(digest_file(path) == expected, "Artifact SHA mismatch")
    verified[name] = expected
    return path


def _code_receipts(protocol: dict) -> dict:
    receipts = {}
    commit = protocol["code"]["commit"]
    require(bool(re.fullmatch(r"[a-f0-9]{40}", commit)), "Invalid frozen commit")
    for name in FROZEN_MODULES:
        raw = (ROOT / name).read_bytes()
        expected = protocol["code"]["python_source_sha256"][name]
        actual = hashlib.sha256(raw).hexdigest()
        receipt = {"frozen_raw_sha256": expected, "analysis_raw_sha256": actual, "comparison": "exact_bytes"}
        if actual != expected:
            blob = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=ROOT,
                                           stderr=subprocess.DEVNULL)
            receipt.update(_newline_receipt(raw, expected, blob))
        receipts[name] = receipt
    return receipts


def _terminal_protocol(root: Path, protocol_sha: str, seal_name: str, seal_sha: str, verified: dict):
    """Finish this gate before opening sources, outcomes, requests or replies."""
    require(bool(re.fullmatch(r"seals/[0-9]+\.json", seal_name)), "Select an explicit final seal")
    seal = read_json(_artifact(root, seal_name, seal_sha, verified))
    protocol = read_json(_artifact(root, "protocol.json", protocol_sha, verified))
    require(protocol["version"] == 1 and protocol["mode"] == "model2000_original_operational"
            and protocol["labels_opened"] is False, "Unknown operational protocol")
    require(protocol["target_distinct_originals"] == TARGET_SOURCES
            and len(protocol["sources"]) == TARGET_SOURCES, "Incomplete original inventory")
    validate_profile(protocol["profile"])
    rows = protocol["sources"]
    ids = [row["doc_id"] for row in rows]
    hashes = [row["source_sha256"] for row in rows]
    require(all(isinstance(value, str) and DOC_ID.fullmatch(value) for value in ids)
            and len(set(ids)) == len(ids), "Invalid or repeated original identity")
    require(all(isinstance(value, str) and SHA.fullmatch(value) for value in hashes)
            and len(set(hashes)) == len(hashes), "Original bytes are not distinct")
    require(dict(Counter(row["family"] for row in rows)) == FAMILY_COUNTS, "Family inventory differs")
    require(seal["summary"]["protocol_sha256"] == protocol_sha
            and [row["doc_id"] for row in seal["sources"]] == ids
            and [row["ordinal"] for row in seal["sources"]] == list(range(len(ids))), "Seal inventory differs")
    require(all(row["state"] in {"sealed", "uncertain"} for row in seal["sources"]),
            "Campaign is not terminal")
    attempts = seal["attempts"]
    require(len(attempts) <= protocol["profile"]["max_calls"]
            and [row["attempt_id"] for row in attempts] == list(range(1, len(attempts) + 1)),
            "Attempt identities or global budget differ")
    require(all(row["doc_id"] in ids and row["state"] in {"replied", "uncertain"} for row in attempts),
            "Unknown or pending attempt")
    return protocol, seal


def _check_attempt_states(rows: list[dict], replies: list[dict]) -> None:
    supplied = iter(replies)
    for row in rows:
        for key in ("prompt_tokens", "completion_tokens", "sdk_attempts"):
            require(row[key] is None or type(row[key]) is int and row[key] >= 0, "Invalid attempt accounting")
        latency = row["latency_ms"]
        require(latency is None or type(latency) in (int, float) and math.isfinite(latency) and latency >= 0,
                "Invalid attempt latency")
        if row["reply_sha256"] is None:
            require(row["state"] == "uncertain" and all(row[key] is None for key in (
                "prompt_tokens", "completion_tokens", "latency_ms", "finish_reason", "refusal", "error_category", "sdk_attempts")),
                "Unreplied attempt contains invented accounting")
            continue
        reply = next(supplied)
        category = reply.get("error_category")
        uncertain = reply.get("sdk_attempts") != 1 or bool(reply.get("error") and not category) or bool(
            category and (category.startswith("transport_") or category in {
                "provider_server", "provider_other", "provider_unknown", "unknown"}))
        require(row["state"] == ("uncertain" if uncertain else "replied"), "Attempt certainty differs from reply")


def _counts(documents: list[dict], attempts: list[dict]) -> dict:
    metrics = [row for row in documents if row["metrics"] is not None]
    valid = [row for row in documents if row["valid_full_coverage"]]
    result = {
        "selected_originals": len(documents),
        "source_states": dict(Counter(row["state"] for row in documents)),
        "request_begun_attempts": len(attempts),
        "originals_with_request_begun": len({row["doc_id"] for row in attempts}),
        "known_sdk_attempts": sum(row["sdk_attempts"] or 0 for row in attempts),
        "attempts_with_unknown_sdk_count": sum(row["sdk_attempts"] is None for row in attempts),
        "uncertain_attempts": sum(row["state"] != "replied" for row in attempts),
        "refused_attempts": sum(bool(row["refusal"]) for row in attempts),
        "finish_reason_counts": dict(Counter(row["finish_reason"] or "unknown" for row in attempts)),
        "provider_error_category_counts": dict(Counter(row["error_category"] for row in attempts if row["error_category"])),
        "valid_full_coverage_originals": len(valid),
        "valid_full_text_coverage_originals": sum(row["metrics"]["coverage_scope"] == "complete_extracted_source_text" for row in valid),
        "valid_full_visual_coverage_originals": sum(row["metrics"]["coverage_scope"] == "complete_source_page_images" for row in valid),
        "prediction_receipt_originals": len(metrics),
        "all_prediction_receipts_sealed": len(metrics) == len(documents),
        "strict_parsed_originals": sum(row["metrics"]["strict_parsed"] for row in metrics),
        "all_null_originals": sum(row["metrics"]["all_null"] for row in metrics),
        "non_null_originals": sum(row["metrics"]["non_null_fields"] > 0 for row in metrics),
        "requires_human_review_originals": sum(row["metrics"]["requires_human_review"] for row in metrics),
        "scalar_conflict_originals": sum(row["metrics"]["scalar_conflict"] for row in metrics),
        "reason_counts": dict(Counter(row["reason"] for row in documents)),
        "known_tokens": {key: sum(row[key] or 0 for row in attempts) for key in ("prompt_tokens", "completion_tokens")},
        "attempts_with_unknown_usage": sum(row["prompt_tokens"] is None or row["completion_tokens"] is None for row in attempts),
        "known_provider_latency_ms": sum(row["latency_ms"] or 0 for row in attempts),
    }
    return result


def _extra_counts(documents: list[dict], attempts: list[dict]) -> dict:
    return {
        "outcome_receipt_originals": sum(row["has_outcome_receipt"] for row in documents),
        "originals_without_request_begun": sum(not row["request_count"] for row in documents),
        "sealed_pre_model_rejections": sum(not row["request_count"] and row["state"] == "sealed" for row in documents),
        "uncertain_before_model": sum(not row["request_count"] and row["state"] == "uncertain" for row in documents),
        "originals_with_known_sdk_attempt": sum(row["known_sdk_attempts"] > 0 for row in documents),
        "valid_strict_reply_attempts": sum(row["valid_strict_reply_attempts"] for row in documents),
        "replied_attempts": sum(row["reply_sha256"] is not None for row in attempts),
        "attempts_with_unknown_latency": sum(row["latency_ms"] is None for row in attempts),
        "valid_non_null_originals": sum(row["valid_full_coverage"] and not row["metrics"]["all_null"] for row in documents),
        "valid_all_null_originals": sum(row["valid_full_coverage"] and row["metrics"]["all_null"] for row in documents),
        "machine_accepted_non_null_fields": sum(row["metrics"]["accepted_non_null_fields"] for row in documents if row["metrics"]),
        "machine_accepted_linked_cells": sum(row["metrics"]["accepted_linked_cells"] for row in documents if row["metrics"]),
        "known_sum_document_duration_ms": round(sum(row["duration_ms"] or 0 for row in documents), 3),
        "originals_with_unknown_duration": sum(row["duration_ms"] is None for row in documents),
    }


def verify_completed(root: Path, protocol_sha: str, seal_name: str, seal_sha: str) -> dict:
    """No SQLite access, inference, OCR, network, label loading or campaign writes."""
    root = _plain(root.absolute())
    verified: dict[str, str] = {}
    protocol, seal = _terminal_protocol(root, protocol_sha, seal_name, seal_sha, verified)
    code = _code_receipts(protocol)
    schemas = {}
    for family, item in protocol["schemas"].items():
        require(family in FAMILY_COUNTS and item["path"] == f"schemas/{family}.json", "Unexpected family schema")
        schemas[family] = load_confirmed_schema(_artifact(root, item["path"], item["sha256"], verified), item["sha256"])
    require(set(schemas) == set(FAMILY_COUNTS), "Missing family schema")
    by_source = defaultdict(list)
    for attempt in seal["attempts"]:
        by_source[attempt["doc_id"]].append(attempt)
        _artifact(root, f"requests/{attempt['doc_id']}/{attempt['request_sha256']}.json", attempt["request_sha256"], verified)
        if attempt["reply_sha256"] is not None:
            _artifact(root, f"replies/{attempt['attempt_id']:06d}.json", attempt["reply_sha256"], verified)
    documents = []
    for source, slot in zip(protocol["sources"], seal["sources"], strict=True):
        doc_id = source["doc_id"]
        source_path = _plain(Path(source["source_path"]))
        require(source_path.is_file() and source_path.stat().st_size == source["source_size_bytes"]
                and digest_file(source_path) == source["source_sha256"], "Original source bytes changed")
        outcome = sidecar = metrics = None
        rows = by_source[doc_id]
        if slot["receipt_sha256"] is not None:
            outcome = read_json(_artifact(root, f"outcomes/{doc_id}.json", slot["receipt_sha256"], verified))
            require(outcome["doc_id"] == doc_id and outcome["source_sha256"] == source["source_sha256"]
                    and outcome["reason"] == slot["reason"], "Outcome identity differs")
            require(type(outcome["duration_ms"]) in (int, float) and math.isfinite(outcome["duration_ms"])
                    and outcome["duration_ms"] >= 0, "Invalid document duration")
            prefix = f"product_runs/model2000_{doc_id}/"
            for name, sha in outcome["output_files"].items():
                require(name.startswith(prefix), "Outcome points outside its product run")
                _artifact(root, name, sha, verified)
            if outcome["metrics"] is not None:
                run = root / prefix
                required = {prefix + name for name in ("run.json", "candidates.jsonl", "manifest.jsonl",
                                                       f"docs/{doc_id}/result.json")}
                require(required <= set(outcome["output_files"]), "Unsealed product result")
                require(verify_run(run, verify_sources=False)["documents"] == 1
                        and verify_result_receipts([run]) == 1, "Product receipt differs")
                manifest = read_json(run / "manifest.jsonl")
                require(manifest["doc_id"] == doc_id and manifest["source_sha256"] == source["source_sha256"]
                        and manifest["source_path"] == source["source_path"]
                        and manifest["source_hash_kind"] == "raw_file", "Product source identity differs")
                sidecar = read_json(run / "docs" / doc_id / "result.json")
                require(sidecar["source_container_sha256"] == source["source_sha256"], "Sidecar source differs")
        require(slot["state"] != "sealed" or outcome is not None, "Sealed source lacks outcome")
        replies, requests, valid_replies = _attempts(root, rows, schemas[source["family"]], protocol["profile"], sidecar)
        _check_attempt_states(rows, replies)
        require(slot["state"] != "sealed" or all(row["state"] == "replied" for row in rows),
                "Uncertain attempt counted as sealed source")
        if sidecar is not None:
            require(manifest["model_call_count"] == len(replies) == len(sidecar["model_calls"]), "Product call count differs")
            metrics = gate.source_metrics(sidecar, replies, schemas[source["family"]], requests=requests)
            require(metrics == outcome["metrics"], "Recomputed operational metrics differ")
        reason = slot["reason"] or slot["state"]
        require(bool(re.fullmatch(r"[A-Za-z0-9_]{1,128}", reason)), "Unsafe outcome reason")
        documents.append({"doc_id": doc_id, "source_sha256": source["source_sha256"], "family": source["family"],
                          "state": slot["state"], "reason": reason, "has_outcome_receipt": outcome is not None,
                          "request_count": len(rows), "known_sdk_attempts": sum(row["sdk_attempts"] or 0 for row in rows),
                          "valid_strict_reply_attempts": valid_replies, "metrics": metrics,
                          "valid_full_coverage": bool(slot["state"] == "sealed" and metrics and metrics["valid_full_coverage"]),
                          "duration_ms": outcome["duration_ms"] if outcome else None})
    # Reuse the runner's hash-chain check with the sealed snapshot, never its live Ledger.summary.
    gate._verify_existing(root, {**seal, "settings": {"protocol_sha256": protocol_sha,
                          "max_calls": str(protocol["profile"]["max_calls"])}}, protocol, protocol_sha)
    counts = _counts(documents, seal["attempts"])
    for key, value in counts.items():
        require(seal["summary"].get(key) == value, "Final summary differs from independently verified evidence")
    counts.update(_extra_counts(documents, seal["attempts"]))
    families = {}
    recorded_families = {}
    for family in FAMILY_COUNTS:
        selected = [row for row in documents if row["family"] == family]
        ids = {row["doc_id"] for row in selected}
        attempts = [row for row in seal["attempts"] if row["doc_id"] in ids]
        families[family] = {**_counts(selected, attempts), **_extra_counts(selected, attempts)}
        values = families[family]
        recorded_families[family] = {key: values[key] for key in ("selected_originals", "originals_with_request_begun")}
        recorded_families[family].update(values["source_states"])
        if any(row["metrics"] is not None for row in selected):
            recorded_families[family].update({key: values[key] for key in (
                "valid_full_coverage_originals", "valid_full_text_coverage_originals",
                "valid_full_visual_coverage_originals", "non_null_originals")})
    require(recorded_families == seal["summary"]["families"], "Family summary differs from evidence")
    expected_pass = counts["valid_full_coverage_originals"] == TARGET_SOURCES and not counts["source_states"].get("uncertain") \
        and counts["originals_with_request_begun"] == TARGET_SOURCES and not seal["summary"]["stop_reason"]
    require(seal["summary"]["operational_gate_passed"] == expected_pass, "Operational gate outcome differs")
    require(seal["summary"]["operator_resume_events"] == seal["controls"], "Control receipt differs")
    require(seal["summary"]["labels_opened"] is False and seal["summary"]["accuracy_measured"] is False
            and seal["summary"]["usd_cost"] is None, "Seal overclaims evaluation scope")
    # Hash unreferenced partial/debug/checkpoint files without trusting them for any denominator.
    extras = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        for name in directories:
            _plain(Path(current) / name)
        for name in filenames:
            path = _plain(Path(current) / name)
            relative = path.relative_to(root).as_posix()
            if relative in verified or ".sqlite3" in name or name.endswith(".lock"):
                continue
            extras.append({"relative_name_sha256": hashlib.sha256(relative.encode()).hexdigest(),
                           "sha256": digest_file(path), "bytes": path.stat().st_size})
    # Detect ordinary concurrent changes before publishing an external verification receipt.
    for name, sha in verified.items():
        require(digest_file(_plain(sealed_path(root, name))) == sha, "Artifact changed during verification")
    for source in protocol["sources"]:
        require(digest_file(_plain(Path(source["source_path"]))) == source["source_sha256"],
                "Original changed during verification")
    return {"version": 1, "kind": "final_operational_verification", "status": "verified",
            "protocol_sha256": protocol_sha, "final_seal_sha256": seal_sha, "frozen_code_commit": protocol["code"]["commit"],
            "profile": {key: protocol["profile"][key] for key in (
                "model", "ocr_engine", "response_format_profile", "long_document_profile", "visual_document_profile",
                "max_tokens", "timeout_s", "workers", "max_calls", "max_calls_per_source")},
            "counts": counts, "families": families, "documents": documents, "operational_gate_passed": expected_pass,
            "verified_artifact_hashes": verified, "unreferenced_artifacts": extras, "frozen_module_receipts": code,
            "runtime_receipt_sha256": digest_json(protocol["runtime"]),
            "runtime_reexecuted": False, "live_ledger_opened": False, "labels_opened": False,
            "accuracy_measured": False, "human_release_measured": False, "usd_cost": None,
            "limitations": ["Request-begun markers do not prove delivery or billing; unknown SDK/usage remains unknown.",
                            "Valid coverage includes valid all-null output; it does not establish value correctness.",
                            "Machine accepted fields are not human-reviewed releases.",
                            "Frozen runtime is an attestation in the pinned protocol, not a reconstructed execution environment.",
                            "Final seal is a snapshot, not a permanent execution lock; run offline after the campaign exits.",
                            "Unreferenced artifacts are hashed separately and never count as model extraction evidence."]}


def write_report(output: Path, report: dict) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    sha = write_new(output / "verification.json", report)
    counts = report["counts"]
    lines = ["# Verified operational extraction campaign", "", f"Protocol: `{report['protocol_sha256']}`",
             f"Final seal: `{report['final_seal_sha256']}`", "", "| Measure | Originals / attempts |", "|---|---:|"]
    for label, key in (("Selected distinct originals", "selected_originals"),
                       ("Originals with request begun", "originals_with_request_begun"),
                       ("Valid complete coverage", "valid_full_coverage_originals"),
                       ("Valid non-null output", "valid_non_null_originals"),
                       ("Valid all-null output", "valid_all_null_originals"),
                       ("Sealed before model request", "sealed_pre_model_rejections"),
                       ("Uncertain attempts", "uncertain_attempts"), ("Known SDK attempts", "known_sdk_attempts"),
                       ("Attempts missing token usage", "attempts_with_unknown_usage")):
        lines.append(f"| {label} | {counts[key]} |")
    lines.extend(["", (f"Known tokens: {counts['known_tokens']['prompt_tokens']} input + "
                      f"{counts['known_tokens']['completion_tokens']} output. USD cost unavailable."), "",
                  (f"Known summed provider latency: {counts['known_provider_latency_ms'] / 1000:.3f} seconds; "
                   f"{counts['attempts_with_unknown_latency']} attempts have unknown latency. This is not wall-clock duration."), "",
                  "| Family | Selected | Request begun | Valid coverage |", "|---|---:|---:|---:|"])
    for family, values in report["families"].items():
        lines.append(f"| {family} | {values['selected_originals']} | {values['originals_with_request_begun']} | {values['valid_full_coverage_originals']} |")
    lines.extend(["", "Operational gate: " + ("passed" if report["operational_gate_passed"] else "not passed"),
                  "", "Accuracy, visual correctness and human-reviewed release are not measured.", ""])
    lines.extend(f"- {limit}" for limit in report["limitations"])
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    receipt = {"version": 1, "verification_sha256": sha, "report_sha256": digest_file(output / "report.md"),
               "verifier_sha256": digest_file(Path(__file__)),
               "request_verifier_sha256": digest_file(ROOT / "product_eval/quality_scoring_verification.py")}
    write_new(output / "receipt.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--seal", required=True, help="Explicit run-relative seals/<timestamp>.json")
    parser.add_argument("--seal-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True, help="New external report directory")
    args = parser.parse_args()
    try:
        root, output = _plain(args.run.absolute()), _plain(args.output.absolute())
        require(root != output and root not in output.parents and output not in root.parents and not output.exists(),
                "Report output must be new and outside the campaign")
        report = verify_completed(root, args.protocol_sha256, args.seal, args.seal_sha256)
        receipt = write_report(output, report)
        print(json.dumps({"status": "verified", **receipt}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.SubprocessError):
        print(json.dumps({"status": "refused", "message": "Offline verification failed; no source or provider text was logged."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

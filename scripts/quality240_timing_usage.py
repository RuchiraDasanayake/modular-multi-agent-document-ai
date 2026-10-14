"""Receipt-bound timing and usage reporting after isolated quality240 scoring.

Scope: research_evidence / keep. This helper opens no labels or model clients.
Run only after the isolated verifier and scorer have succeeded; retain their
receipt hashes independently. Request percentiles include known failed-attempt
latencies. Missing observations and unstarted sources never become zero times.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SHA = re.compile(r"[a-f0-9]{64}\Z")
ARMS = ("text", "candidate")
PROTOCOL_SHA256 = "3cf41aac59be90d610a4479d1d9876bbf77894e9d55162983a8713b510594075"
PLAN_SHA256 = "68ba30cb8831a5805c49b0b340a83e88429720de249a2986f92efc4ea676974e"
PREREGISTRATION_SHA256 = "7d267e6bc129c62e9c19c1323ac71da358a659132b213dc232e5af6c0d77ad30"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sealed_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    require(bool(name) and not relative.is_absolute() and relative.as_posix() == name
            and not {".", ".."}.intersection(relative.parts) and ":" not in name and "\\" not in name,
            "Unsafe sealed artifact path")
    path = root.joinpath(*relative.parts)
    require(path.is_file() and not any(part.is_symlink() for part in (path, *path.parents)),
            "Missing or symlinked artifact")
    return path


def pinned_json(path: Path, expected: str) -> dict:
    require(isinstance(expected, str) and bool(SHA.fullmatch(expected)) and digest(path) == expected,
            "Input hash differs")
    return read_json(path)


def distribution(values: list[float]) -> dict:
    """Linear order-statistic interpolation, equivalent to NumPy linear quantile."""
    require(all(type(value) in {int, float} and math.isfinite(value) and value >= 0 for value in values),
            "Invalid timing observation")
    ordered = sorted(values)

    def quantile(probability: float) -> float | None:
        if not ordered:
            return None
        index = (len(ordered) - 1) * probability
        low, high = math.floor(index), math.ceil(index)
        return ordered[low] + (ordered[high] - ordered[low]) * (index - low)

    return {"measured_count": len(ordered), "known_sum_ms": sum(ordered),
            "p50_ms": quantile(0.5), "p95_ms": quantile(0.95)}


def summarize(rows: list[dict]) -> dict:
    attempts = [attempt for row in rows for attempt in row["attempts"]]
    result = {"selected_sources": len(rows), "source_states": dict(Counter(row["state"] for row in rows)),
              "source_reason_counts": dict(Counter(row["reason"] for row in rows)),
              "started_sources": sum(row["state"] != "unstarted" for row in rows),
              "originals_with_attempts": sum(bool(row["attempts"]) for row in rows),
              "request_begun_attempts": len(attempts),
              "uncertain_attempts": sum(row["state"] != "replied" for row in attempts),
              "attempt_state_counts": dict(Counter(row["state"] for row in attempts)),
              "error_category_counts": dict(Counter(row["error_category"] or "none" for row in attempts))}
    for key in ("prompt_tokens", "completion_tokens", "sdk_attempts"):
        values = [row[key] for row in attempts if row[key] is not None]
        require(all(type(value) is int and value >= 0 for value in values), "Invalid usage observation")
        result[f"known_{key}"] = sum(values)
        result[f"attempts_with_unknown_{key}"] = len(attempts) - len(values)
    complete = [row for row in attempts if row["prompt_tokens"] is not None and row["completion_tokens"] is not None]
    result.update(complete_usage_attempts=len(complete), attempts_with_any_unknown_tokens=len(attempts) - len(complete),
                  known_prompt_plus_completion_components=result["known_prompt_tokens"] + result["known_completion_tokens"],
                  complete_usage_token_total=sum(row["prompt_tokens"] + row["completion_tokens"] for row in complete))
    request = distribution([row["latency_ms"] for row in attempts if row["latency_ms"] is not None])
    request.update(attempted_requests=len(attempts), missing_latency_requests=len(attempts) - request["measured_count"],
                   measured_attempt_states=dict(Counter(row["state"] for row in attempts if row["latency_ms"] is not None)))
    source = distribution([row["duration_ms"] for row in rows if row["duration_ms"] is not None])
    source.update(started_sources=result["started_sources"],
                  missing_duration_started_sources=result["started_sources"] - source["measured_count"],
                  measured_source_states=dict(Counter(row["state"] for row in rows if row["duration_ms"] is not None)))
    model_source = distribution([row["duration_ms"] for row in rows if row["attempts"] and row["duration_ms"] is not None])
    model_source.update(originals_with_attempts=result["originals_with_attempts"],
                        missing_duration_model_attempted_sources=result["originals_with_attempts"] - model_source["measured_count"])
    result.update(request_latency_ms=request, source_execution_duration_ms=source,
                  model_attempted_source_duration_ms=model_source, usd_cost=None)
    return result


def assemble(protocol: dict, snapshots: dict, documents: dict, events: list[dict], scored: dict) -> dict:
    """Summarize verified metadata without inspecting reference or predicted values."""
    sources = {row["doc_id"]: row for row in protocol["sources"]}
    require(len(sources) == len(protocol["sources"]), "Repeated source ID")
    all_rows, reports, closing_times = [], {}, []
    for arm in ARMS:
        snapshot = snapshots[arm]
        require([row["doc_id"] for row in snapshot["sources"]] == list(sources), "Source denominator differs")
        outcomes = {row["doc_id"]: row for row in documents[arm]}
        require(len(outcomes) == len(documents[arm]) and set(outcomes) == set(sources), "Document denominator differs")
        require(all(row["doc_id"] in sources and row["state"] in {"replied", "uncertain"}
                    for row in snapshot["attempts"]), "Unknown or unfinished request")
        rows = []
        for slot in snapshot["sources"]:
            doc_id = slot["doc_id"]
            document = outcomes[doc_id]
            require(slot["state"] in {"sealed", "uncertain", "unstarted"}
                    and document["state"] == slot["state"] and document["family"] == sources[doc_id]["family"],
                    "Unknown, unfinished or inconsistent source")
            outcome = document["outcome"]
            attempts = [row for row in snapshot["attempts"] if row["doc_id"] == doc_id]
            require(slot["state"] != "unstarted" or not attempts and outcome is None, "Unstarted source contains work")
            duration = outcome["duration_ms"] if outcome else None
            if slot["state"] != "unstarted":
                require(type(slot["updated"]) in {int, float} and math.isfinite(slot["updated"]) and slot["updated"] > 0,
                        "Invalid source close timestamp")
                closing_times.append(slot["updated"])
            rows.append({"doc_id": doc_id, "family": sources[doc_id]["family"], "state": slot["state"], "reason": document["reason"],
                         "duration_ms": duration, "attempts": attempts})
        families = {}
        for family in sorted({row["family"] for row in sources.values()}):
            members = [row for row in rows if row["family"] == family]
            summary = summarize(members)
            original = scored["families"][arm][family]
            require(original["documents"] == len(members), "Scored source denominator differs")
            for key in ("request_begun_attempts", "originals_with_attempts", "uncertain_attempts",
                        "known_prompt_tokens", "known_completion_tokens", "known_sdk_attempts",
                        "attempts_with_unknown_prompt_tokens", "attempts_with_unknown_completion_tokens",
                        "attempts_with_unknown_sdk_attempts", "source_states"):
                require(original["operational_usage"][key] == summary[key], "Scored usage accounting differs")
            usage = original["operational_usage"]
            require(math.isclose(usage["known_latency_ms"], summary["request_latency_ms"]["known_sum_ms"], abs_tol=1e-6)
                    and usage["attempts_with_unknown_latency_ms"] == summary["request_latency_ms"]["missing_latency_requests"]
                    and math.isclose(usage["known_product_duration_ms"], summary["source_execution_duration_ms"]["known_sum_ms"], abs_tol=1e-6)
                    and usage["originals_without_duration"] == len(members) - summary["source_execution_duration_ms"]["measured_count"],
                    "Scored timing accounting differs")
            families[family] = summary
        reports[arm] = {"overall": summarize(rows), "families": families,
                        "sources": [{"doc_id": row["doc_id"], "family": row["family"], "state": row["state"], "reason": row["reason"],
                                     "source_duration_ms": row["duration_ms"], "usage": summarize([row])} for row in rows]}
        all_rows += rows
    starts = [row["time_ns"] for row in events if row["event"] == "start"]
    require(len(starts) == 1 and type(starts[0]) is int and starts[0] > 0, "Original campaign start is unavailable")
    start = starts[0] / 1_000_000_000
    finish = max(closing_times) if closing_times else None
    require(finish is None or finish >= start, "Source closed before campaign start")
    return {"arms": reports, "overall_source_arm_slots": summarize(all_rows),
            "campaign_execution_span": {"start_event_time_ns": starts[0],
                "start_utc": datetime.fromtimestamp(start, timezone.utc).isoformat(),
                "last_source_close_utc": datetime.fromtimestamp(finish, timezone.utc).isoformat() if finish else None,
                "elapsed_ms": (finish - start) * 1000 if finish else None,
                "includes_provider_and_operator_pauses": True, "excludes_sealing_and_analysis": True,
                "process_active_campaign_duration_ms": None,
                "started_source_arm_slots": len(closing_times),
                "unstarted_source_arm_slots": sum(row["state"] == "unstarted" for row in all_rows),
                "control_event_counts": dict(Counter(row["event"] for row in events))}}


def run_report(run: Path, seal_sha: str, verification_receipt: Path, verification_sha: str,
               scored_output: Path, scoring_sha: str, output: Path) -> dict:
    """Bind existing full verification/scoring receipts, then report metadata."""
    require(not output.exists() and not output.resolve().is_relative_to(run.resolve())
            and not output.resolve().is_relative_to(scored_output.resolve()), "New external output required")
    independent = pinned_json(verification_receipt, verification_sha)
    require(independent.get("version") == 1 and independent.get("type") == "quality240_independent_prediction_verification"
            and independent.get("labels_opened") is False and independent["context"]["prediction_seal_sha256"] == seal_sha,
            "Independent prediction verification is required")
    verified = independent["verification"]
    require(verified["prediction_seal_sha256"] == seal_sha and verified["protocol_sha256"] == PROTOCOL_SHA256
            and verified["analysis_plan_sha256"] == PLAN_SHA256 and verified["preregistration_sha256"] == PREREGISTRATION_SHA256
            and verified["labels_opened_before_verification"] is False, "Verified registration differs")
    scoring = pinned_json(scored_output / "scoring-receipt.json", scoring_sha)
    require(all(scoring.get(key) == value for key, value in verified.items())
            and scoring.get("no_inference_or_ocr") is True and scoring.get("no_reference_repairs") is True,
            "Scoring receipt is not bound to the independent verification")
    before = pinned_json(scored_output / "verified-before-labels.json", scoring["files"]["verified-before-labels.json"])
    require(before == verified, "Scoring did not retain the same pre-label verification")
    scored_sha = scoring["files"]["quality-results.json"]
    scored = pinned_json(scored_output / "quality-results.json", scored_sha)
    require(scored.get("all_sources_retained") is True, "Scored result omitted sources")
    seal = pinned_json(run / "prediction-seal.json", seal_sha)
    require(seal.get("all_slots_accounted") is True and seal.get("labels_opened") is False, "Incomplete prediction seal")
    for name, expected in seal["files"].items():
        require(bool(SHA.fullmatch(expected)) and digest(sealed_path(run, name)) == expected, "Sealed artifact hash differs")
    actual = set()
    for path in run.rglob("*"):
        require(not path.is_symlink(), "Campaign symlink is unsupported")
        if path.is_file() and path.name != "prediction-seal.json" and ".sqlite3" not in path.name and path.suffix != ".lock":
            actual.add(path.relative_to(run).as_posix())
    require(actual == set(seal["files"]), "Unsealed or missing campaign artifact")
    for name, expected in (("protocol.json", PROTOCOL_SHA256), ("analysis-plan.json", PLAN_SHA256),
                           ("analysis-preregistration.json", PREREGISTRATION_SHA256)):
        require(seal["files"].get(name) == expected, "Sealed registration differs")
    require("seal-started.json" in seal["files"], "Execution is not permanently closed")
    protocol = read_json(run / "protocol.json")
    snapshots = {arm: read_json(run / "arms" / arm / "ledger-snapshot.json") for arm in ARMS}
    documents = {arm: read_json(run / "arms" / arm / "documents.json") for arm in ARMS}
    events = [read_json(run / name) for name in sorted(seal["files"]) if re.fullmatch(r"controls/[0-9]{6}\.json", name)]
    result = assemble(protocol, snapshots, documents, events, scored)
    result.update(version=1, type="quality240_post_score_timing_usage",
                  inputs_sha256={"prediction_seal": seal_sha, "independent_verification": verification_sha,
                                 "scoring_receipt": scoring_sha, "quality_results": scored_sha,
                                 "helper": digest(Path(__file__))},
                  model_calls=0, reference_files_opened_by_helper=False, usd_cost=None,
                  methods={"request_latency": "Known latency_ms of every request_begun attempt, including failed and uncertain replies; missing times remain missing.",
                           "source_duration": "Worker monotonic duration from source verification through product verification; includes OCR and provider calls, excludes outcome persistence. Started pre-model failures are included when measured.",
                           "quantiles": "Linear interpolation at (n-1)*p on sorted measured observations, p=0.50 and 0.95.",
                           "campaign_span": "Original control start timestamp to last source closure; includes pauses and excludes later sealing/analysis. Exact process-active wall time was not recorded.",
                           "tokens": "Known component sums retain failed attempts. Missing token usage is unknown and is not zero cost; no monetary inference."})
    # Check the metadata again before publishing; no moving ledger/receipt can
    # silently acquire the retained evidence hashes.
    require(digest(run / "prediction-seal.json") == seal_sha and digest(verification_receipt) == verification_sha
            and digest(scored_output / "scoring-receipt.json") == scoring_sha
            and digest(scored_output / "quality-results.json") == scored_sha, "Input changed during reporting")
    for name in ("protocol.json", *(f"arms/{arm}/{file}" for arm in ARMS for file in ("ledger-snapshot.json", "documents.json")),
                 *(name for name in seal["files"] if name.startswith("controls/"))):
        require(digest(sealed_path(run, name)) == seal["files"][name], "Timing metadata changed during reporting")
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {"output_sha256": hashlib.sha256(raw).hexdigest(), "model_calls": 0, "reference_files_opened_by_helper": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "verification-receipt", "scored-output", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("prediction-seal-sha256", "verification-sha256", "scoring-receipt-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    print(json.dumps(run_report(args.run, args.prediction_seal_sha256, args.verification_receipt,
        args.verification_sha256, args.scored_output, args.scoring_receipt_sha256, args.output), indent=2))


if __name__ == "__main__":
    main()

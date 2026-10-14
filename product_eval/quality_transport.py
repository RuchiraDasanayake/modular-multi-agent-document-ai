"""Append-only endpoint amendment for an already frozen paired campaign.

The original execution protocol and product implementation remain intact. An
amendment binds the old ledger prefix and permits only its unstarted slots to use
the project endpoint. This is a disclosed transport change, not evidence that
the provider serves identical model weights through both routes.
"""
from __future__ import annotations

import multiprocessing
import os
import re
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from product_eval import quality_comparison as quality
from product_eval.final_gate_freeze import digest_file, read_json, write_new, write_new_bytes
from product_eval.final_gate_ledger import Ledger, exclusive_run_lock
from product_eval.product_candidate_dev import configured_environment

OLD_BASE = "https://icore.innobothealth.us/innobot-api/v1"
PROJECT_BASE = "https://icore.innobothealth.us/innobot-project-api/v1"
FOLDER = "transport-amendment"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _open_for_execution(output: Path) -> None:
    require(not (output / "seal-started.json").exists() and not (output / "prediction-seal.json").exists(),
            "Sealing began; paid execution is permanently closed")


def _environment(output: Path):
    config = read_json(output / "protocol.json")["runtime"]["ocr_config"]
    return configured_environment(Path(config["python"]), Path(config["work_dir"]))


def prepare(output: Path, protocol_sha: str, *, stop_sha: str, access_receipt: Path) -> str:
    """Record the boundary before dispatch; creates no provider client."""
    with exclusive_run_lock(output / "run.lock"), _environment(output):
        _open_for_execution(output)
        protocol = quality.verify_freeze(output, protocol_sha)
        stop = quality.current_stop(output)
        require(stop is not None and stop["sha256"] == stop_sha and stop["resumable"],
                "Exact resumable stop required before endpoint amendment")
        require(all(p["base_url"] == OLD_BASE and p["model"] == "innobot-luna-6"
                    for p in protocol["profiles"].values()), "Unsupported original transport")
        access = read_json(access_receipt)
        require(access["base_url"] == PROJECT_BASE and access["document_content_sent"] is False
                and all(access[name]["status"] == 200 for name in ("models", "capabilities", "chat")),
                "Verified project endpoint access required")
        require(access["chat"]["body"]["model"] == "openai.gpt-6-luna", "Luna 6 access required")
        snapshots = {arm: Ledger(output / "arms" / arm / "ledger.sqlite3").snapshot() for arm in quality.ARMS}
        require(all(row["state"] != "started" for state in snapshots.values() for row in state["sources"]),
                "Interrupted sources must be resolved before amendment")
        folder = output / FOLDER
        folder.mkdir(exist_ok=False)
        baseline = {arm: write_new(folder / f"baseline-{arm}.json", state) for arm, state in snapshots.items()}
        implementation_sha = write_new_bytes(folder / "implementation.py", Path(__file__).read_bytes())
        access_sha = write_new_bytes(folder / "access-verification.json", access_receipt.read_bytes())
        amendment = {"version": 1, "type": "icore_project_endpoint", "protocol_sha256": protocol_sha,
            "created_utc": datetime.now(timezone.utc).isoformat(), "prior_stop_sha256": stop_sha,
            "old_base_url": OLD_BASE, "new_base_url": PROJECT_BASE, "model": "innobot-luna-6",
            "implementation_sha256": implementation_sha, "access_receipt_sha256": access_sha,
            "baseline_sha256": baseline, "labels_opened": False, "replay_allowed": False,
            "analysis_files_sha256": {name: digest_file(output / name) for name in (
                "analysis-plan.json", "analysis-preregistration.json")},
            "reason": "User supplied a project-scoped key requiring the dedicated project endpoint after a provider rate-limit stop.",
            "interpretation": "Endpoint/authentication changed mid-campaign. Provider weight equivalence is unverified. Preserve all original slots and report transport-stratified counts; no outcome-driven exclusions."}
        return write_new(folder / "amendment.json", amendment)


def dispatch_record(amendment_sha: str, arm: str, row: dict, profile: dict) -> dict:
    return {"amendment_sha256": amendment_sha, "arm": arm, "doc_id": row["doc_id"],
            "source_sha256": row["source_sha256"], "profile": {**profile, "base_url": PROJECT_BASE}}


def verify_amendment(output: Path, protocol: dict, expected_sha: str, *, sealed: bool = False) -> dict:
    """Check original ledger prefixes and every amended dispatch, without labels."""
    folder = output / FOLDER
    require(bool(re.fullmatch(r"[a-f0-9]{64}", expected_sha))
            and digest_file(folder / "amendment.json") == expected_sha, "Endpoint amendment hash differs")
    amendment = read_json(folder / "amendment.json")
    require(amendment["version"] == 1 and amendment["type"] == "icore_project_endpoint"
            and amendment["old_base_url"] == OLD_BASE and amendment["new_base_url"] == PROJECT_BASE
            and amendment["model"] == "innobot-luna-6" and amendment["labels_opened"] is False
            and amendment["replay_allowed"] is False, "Unsupported endpoint amendment")
    require(digest_file(output / "protocol.json") == amendment["protocol_sha256"], "Original protocol changed")
    require(digest_file(Path(__file__)) == digest_file(folder / "implementation.py") == amendment["implementation_sha256"],
            "Amendment implementation changed")
    require(digest_file(folder / "access-verification.json") == amendment["access_receipt_sha256"],
            "Access verification changed")
    for name, expected in amendment["analysis_files_sha256"].items():
        require(name in {"analysis-plan.json", "analysis-preregistration.json"}
                and digest_file(output / name) == expected, "Analysis registration changed")
    require(set(amendment["analysis_files_sha256"]) == {"analysis-plan.json", "analysis-preregistration.json"},
            "Incomplete analysis binding")
    require(any(event["sha256"] == amendment["prior_stop_sha256"] and event["event"] == "stop"
                for event in quality.journal(output)[0]), "Original stop receipt changed")
    sources = {row["doc_id"]: row for row in protocol["sources"]}
    cohorts, attempts, expected_files = {}, {}, {"amendment.json", "implementation.py", "access-verification.json"}
    for arm in quality.ARMS:
        baseline_path = folder / f"baseline-{arm}.json"
        expected_files.add(baseline_path.name)
        require(digest_file(baseline_path) == amendment["baseline_sha256"][arm], "Original ledger snapshot changed")
        baseline = read_json(baseline_path)
        directory = output / "arms" / arm
        current = (read_json(directory / "ledger-snapshot.json") if sealed else Ledger(directory / "ledger.sqlite3").snapshot())
        require(current["attempts"][:len(baseline["attempts"])] == baseline["attempts"], "Original paid attempts changed")
        require([row["doc_id"] for row in current["sources"]] == [row["doc_id"] for row in baseline["sources"]]
                == list(sources), "Amendment source inventory changed")
        require(baseline["settings"]["protocol_sha256"] == current["settings"]["protocol_sha256"]
                == amendment["protocol_sha256"]
                and baseline["settings"]["max_calls"] == current["settings"]["max_calls"], "Ledger binding changed")
        eligible = {row["doc_id"] for row in baseline["sources"] if row["state"] == "unstarted"}
        for before, now in zip(baseline["sources"], current["sources"], strict=True):
            if before["state"] != "unstarted":
                require(before == now, "Previously attempted source was changed or replayed")
            elif now["state"] != "unstarted":
                require((folder / "dispatches" / arm / f"{now['doc_id']}.json").is_file(),
                        "Amended source lacks a transport dispatch receipt")
        for path in (folder / "dispatches" / arm).glob("*.json"):
            require(path.stem in eligible, "Amended dispatch targets an already attempted source")
            require(read_json(path) == dispatch_record(expected_sha, arm, sources[path.stem], protocol["profiles"][arm]),
                    "Amended dispatch profile changed")
            expected_files.add(path.relative_to(folder).as_posix())
        later = current["attempts"][len(baseline["attempts"]):]
        require(all(row["doc_id"] in eligible and (folder / "dispatches" / arm / f"{row['doc_id']}.json").is_file()
                    for row in later), "Unrecorded post-amendment paid attempt")
        cohorts[arm] = {row["doc_id"]: "project" if row["doc_id"] in eligible else "personal"
                        for row in baseline["sources"]}
        attempts[arm] = {"personal": len(baseline["attempts"]), "project": len(later)}
    actual_files = set()
    for path in folder.rglob("*"):
        require(not path.is_symlink(), "Amendment symlink is not supported")
        if path.is_file():
            actual_files.add(path.relative_to(folder).as_posix())
    require(actual_files == expected_files, "Unexpected amendment artifact")
    return {"amendment_sha256": expected_sha, "source_arm_transport_cohorts": cohorts,
            "request_begun_attempts_by_transport": attempts, "labels_opened": False,
            "provider_weight_equivalence_verified": False}


def run(output: Path, protocol_sha: str, amendment_sha: str, *, api_key_env: str,
        batches: int, acknowledge: str | None = None) -> dict:
    require(bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env)) and bool(os.environ.get(api_key_env, "").strip()),
            "Credential environment variable required")
    require(type(batches) is int and batches >= 1, "Positive checkpoint limit required")
    with exclusive_run_lock(output / "run.lock"), _environment(output):
        _open_for_execution(output)
        protocol = quality.verify_freeze(output, protocol_sha)
        verify_amendment(output, protocol, amendment_sha)
        for arm in quality.ARMS:
            Ledger(output / "arms" / arm / "ledger.sqlite3").recover_interrupted()
        quality.current_stop(output)
        if acknowledge:
            quality.acknowledge_stop(output, acknowledge)
        if quality.current_stop(output):
            return quality.checkpoint(output, protocol)
        rows = {row["doc_id"]: row for row in protocol["sources"]}
        with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
            completed = 0
            width = 2 * quality.BATCH_ORIGINALS
            for start in range(0, len(protocol["schedule"]), width):
                dispatched = False
                for slot in protocol["schedule"][start:start + width]:
                    if quality.current_stop(output):
                        break
                    arm, doc_id = slot["arm"], slot["doc_id"]
                    directory = output / "arms" / arm
                    ledger = Ledger(directory / "ledger.sqlite3")
                    state = next(row for row in ledger.snapshot()["sources"] if row["doc_id"] == doc_id)
                    if state["state"] != "unstarted":
                        continue
                    record = dispatch_record(amendment_sha, arm, rows[doc_id], protocol["profiles"][arm])
                    path = output / FOLDER / "dispatches" / arm / f"{doc_id}.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists():
                        require(read_json(path) == record, "Existing dispatch receipt differs")
                    else:
                        write_new(path, record)
                    if not ledger.claim(doc_id):
                        continue
                    dispatched = True
                    worker_protocol = {**quality.arm_protocol(protocol, arm), "profile": record["profile"]}
                    try:
                        pool.submit(quality.gate._run_source, str(directory), rows[doc_id], worker_protocol, api_key_env).result()
                    except Exception:  # noqa: BLE001 - preserve paid uncertainty, never print worker diagnostics
                        ledger.stop("worker_process_failed")
                        ledger.recover_interrupted()
                    if quality.current_stop(output):
                        break
                if dispatched:
                    quality.checkpoint(output, protocol)
                    completed += 1
                if quality.current_stop(output) or completed >= batches:
                    break
        for arm in quality.ARMS:
            Ledger(output / "arms" / arm / "ledger.sqlite3").recover_interrupted()
        verify_amendment(output, protocol, amendment_sha)
        report = quality.checkpoint(output, protocol)
        if not any(arm["source_states"].get("unstarted") for arm in report["arms"].values()):
            quality.verify_freeze(output, protocol_sha)
            return quality._seal(output, protocol)
        return report

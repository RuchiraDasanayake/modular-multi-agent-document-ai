"""Source-only freeze and resumable paired quality240 execution; never loads labels."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import re
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.workflow import _doc_id
from product_eval import final_gate_freeze as freeze_helpers
from product_eval import final_model_gate as gate
from product_eval.final_gate_freeze import (
    digest_file,
    digest_json,
    encoded,
    read_json,
    write_new,
    write_new_bytes,
)
from product_eval.final_gate_ledger import Ledger, exclusive_run_lock
from product_eval.product_candidate_dev import (
    _placeholder,
    configured_environment,
    outside_git,
)

INVENTORY_SHA256 = "214def43738fd2bafb3102d80b4f26287e5b405140206abc767c361521e135ab"
BASELINE_SHA256 = "2900c5d167825d1924e2b90ee225f8e16007cfdc370d57d01b8be7d2404d83fa"
SCHEMA_SHA256 = {
    "registration-form": "36c53ff90a098d05e1c2b8d2a7d35ebb3c29e6915f354658a03671d8d9a9dcfd",
    "ad-buy-form": "3fd04649edb13e920915d5e326522587a57af4abfd8499f8ae0d8f501dc73675",
    "receipt": "0ebeb253954b8726d9e46a3b24fbedfb30cb5b5f9957cde98580deee948f80b7",
}
FAMILIES = {"registration-form": 100, "ad-buy-form": 100, "receipt": 40}
ARMS = {"text": "disabled", "candidate": "bounded_visual_selective_v2"}
ARM_MAX_CALLS, GLOBAL_MAX_CALLS, BATCH_ORIGINALS = 960, 1920, 25
_RESUMABLE_LEDGER_STOPS = {"authentication", "rate_limit", "repeated_transport_failure"}


def arm_profile(arm: str) -> dict:
    # Reuse the product-profile contract without changing mixed2000's admission
    # minimum. The quality ledger separately narrows only its paid-attempt cap.
    base = {**freeze_helpers.DEFAULT_PROFILE, "visual_document_profile": ARMS[arm],
            "max_tokens": 8192, "timeout_s": 180, "workers": 1, "parallel_validation": None}
    checked = freeze_helpers.validate_profile(base)
    freeze_helpers.require_interfaces(checked)
    return {**checked, "max_calls": ARM_MAX_CALLS}


def source_rows(inventory: dict) -> list[dict]:
    rows = []
    for row in inventory["sources"]:
        path = Path(row["source_path"])
        rows.append({key: row[key] for key in ("family", "source_path", "source_sha256", "source_size_bytes", "dataset_id")}
                    | {"doc_id": _doc_id(path.name, row["source_sha256"], 0)})
    if Counter(row["family"] for row in rows) != FAMILIES:
        raise ValueError("Exact quality240 family allocation required")
    if len({row["doc_id"] for row in rows}) != len(rows) or len({row["source_sha256"] for row in rows}) != len(rows):
        raise ValueError("Distinct source hashes and product IDs required")
    return rows


def verify_sources(rows: list[dict]) -> None:
    for row in rows:
        path = Path(row["source_path"])
        if (not path.is_absolute() or path.is_symlink() or path.suffix.lower() not in {".pdf", ".png"}
                or not freeze_helpers.SHA.fullmatch(row["source_sha256"])
                or type(row["source_size_bytes"]) is not int or not 0 < row["source_size_bytes"] <= 20 * 1024 * 1024
                or path.stat().st_size != row["source_size_bytes"] or digest_file(path) != row["source_sha256"]
                or _doc_id(path.name, row["source_sha256"], 0) != row["doc_id"]):
            raise ValueError("Original source identity changed or unsupported")


def schedule(rows: list[dict]) -> list[dict]:
    families = {family: [row for row in rows if row["family"] == family] for family in FAMILIES}
    result, pair = [], 0
    for ordinal in range(max(FAMILIES.values())):
        for members in families.values():
            if ordinal >= len(members):
                continue
            for arm in (("text", "candidate") if ordinal % 2 == 0 else ("candidate", "text")):
                result.append({"pair_index": pair, "family_ordinal": ordinal, "arm": arm, "doc_id": members[ordinal]["doc_id"]})
            pair += 1
    return result


def prepare(inventory: Path, baseline: Path, output: Path, *, rapidocr_python: Path, scratch: Path) -> str:
    output = output.resolve()
    outside_git(output)
    if output.exists():
        raise ValueError("Choose a new output directory")
    if digest_file(inventory) != INVENTORY_SHA256 or digest_file(baseline) != BASELINE_SHA256:
        raise ValueError("Required source inventory or schema baseline changed")
    rows = source_rows(read_json(inventory))
    verify_sources(rows)
    schemas = read_json(baseline)["schemas"]
    if {family: item["sha256"] for family, item in schemas.items()} != SCHEMA_SHA256:
        raise ValueError("Required three schema hashes changed")
    for item in schemas.values():
        load_confirmed_schema(Path(item["path"]), item["sha256"])
    profiles = {arm: arm_profile(arm) for arm in ARMS}
    code = freeze_helpers.code_receipt()
    with configured_environment(rapidocr_python, scratch):
        runtime = freeze_helpers.runtime_receipt()
    protocol = {
        "version": 1, "mode": "paired_quality240", "labels_opened": False,
        "inventory_sha256": INVENTORY_SHA256, "schema_baseline_sha256": BASELINE_SHA256,
        "code": code, "runtime": runtime, "sources": rows, "schedule": schedule(rows),
        "profiles": profiles, "schemas": {family: {"path": f"schemas/{family}.json", "sha256": item["sha256"]}
                                           for family, item in schemas.items()},
        "target_distinct_originals": len(rows), "global_max_calls": GLOBAL_MAX_CALLS,
        "arm_max_calls": ARM_MAX_CALLS, "batch_originals": BATCH_ORIGINALS,
        "fresh_original_intake_and_ocr_per_arm": True, "cached_ocr_allowed": False,
        "scope": "paired confirmed-schema product proposals; quality is assessed separately after prediction seal",
    }
    output.mkdir(parents=True, exist_ok=False)
    write_new_bytes(output / "source-inventory.json", inventory.read_bytes())
    sha = write_new(output / "protocol.json", protocol)
    for arm in ARMS:
        directory = output / "arms" / arm
        (directory / "schemas").mkdir(parents=True)
        for family, item in schemas.items():
            path = directory / protocol["schemas"][family]["path"]
            write_new_bytes(path, Path(item["path"]).read_bytes())
            load_confirmed_schema(path, item["sha256"])
        Ledger(directory / "ledger.sqlite3").initialize(rows, sha, ARM_MAX_CALLS)
    return sha


def arm_protocol(protocol: dict, arm: str) -> dict:
    return {"profile": protocol["profiles"][arm], "schemas": protocol["schemas"],
            "sources": protocol["sources"], "target_distinct_originals": protocol["target_distinct_originals"]}


def verify_freeze(output: Path, expected_sha: str) -> dict:
    if not freeze_helpers.SHA.fullmatch(expected_sha) or digest_file(output / "protocol.json") != expected_sha:
        raise ValueError("Protocol hash changed")
    protocol = read_json(output / "protocol.json")
    if protocol.get("mode") != "paired_quality240" or protocol.get("version") != 1 or protocol.get("labels_opened") is not False:
        raise ValueError("Unknown quality protocol")
    if (protocol["inventory_sha256"] != INVENTORY_SHA256 or protocol["schema_baseline_sha256"] != BASELINE_SHA256
            or digest_file(output / "source-inventory.json") != INVENTORY_SHA256
            or protocol["sources"] != source_rows(read_json(output / "source-inventory.json"))
            or protocol["schedule"] != schedule(protocol["sources"])
            or protocol["profiles"] != {arm: arm_profile(arm) for arm in ARMS}
            or protocol["global_max_calls"] != GLOBAL_MAX_CALLS or protocol["arm_max_calls"] != ARM_MAX_CALLS
            or protocol["target_distinct_originals"] != sum(FAMILIES.values()) or protocol["batch_originals"] != BATCH_ORIGINALS):
        raise ValueError("Frozen campaign contract changed")
    if {family: item["sha256"] for family, item in protocol["schemas"].items()} != SCHEMA_SHA256:
        raise ValueError("Frozen family schemas changed")
    if freeze_helpers.code_receipt() != protocol["code"] or freeze_helpers.runtime_receipt() != protocol["runtime"]:
        raise ValueError("Code or runtime changed")
    verify_sources(protocol["sources"])
    for arm in ARMS:
        directory = output / "arms" / arm
        for family, item in protocol["schemas"].items():
            if item["path"] != f"schemas/{family}.json":
                raise ValueError("Unsafe schema path")
            load_confirmed_schema(directory / item["path"], item["sha256"])
        gate._verify_existing(directory, Ledger(directory / "ledger.sqlite3").snapshot(), arm_protocol(protocol, arm), expected_sha)
    return protocol


def journal(output: Path) -> tuple[list[dict], str | None]:
    events, previous = [], None
    for index, path in enumerate(sorted((output / "controls").glob("*.json")), 1):
        item = read_json(path)
        if path.name != f"{index:06d}.json" or item["previous_sha256"] != previous:
            raise ValueError("Campaign control journal changed")
        previous = digest_file(path)
        events.append({**item, "sha256": previous})
    return events, previous


def append_event(output: Path, value: dict) -> str:
    events, previous = journal(output)
    (output / "controls").mkdir(exist_ok=True)
    return write_new(output / "controls" / f"{len(events) + 1:06d}.json",
                     {**value, "previous_sha256": previous, "time_ns": time.time_ns()})


def pending_signals(output: Path) -> dict:
    events, _ = journal(output)
    acknowledged = {key for event in events if event["event"] == "acknowledge_stop" for key in event["signal_ids"]}
    signals, attempts = {}, 0

    def add(arm, identity, reason, resumable):
        key = digest_json({"arm": arm, "identity": identity, "reason": reason})
        if key not in acknowledged:
            signals[key] = {"arm": arm, "reason": reason, "resumable": resumable}

    for arm in ARMS:
        snapshot = Ledger(output / "arms" / arm / "ledger.sqlite3").snapshot()
        attempts += len(snapshot["attempts"])
        stop = snapshot["settings"]["stop_reason"]
        if stop:
            add(arm, ["ledger", len(snapshot["attempts"]), len(snapshot["controls"])], stop, stop in _RESUMABLE_LEDGER_STOPS)
        for attempt in snapshot["attempts"]:
            category = attempt["error_category"]
            if category or attempt["state"] != "replied":
                reason = category or "uncertain_attempt"
                resumable = reason in {"authentication", "rate_limit", "uncertain_attempt", "provider_server", "provider_other", "provider_unknown"} or reason.startswith("transport_")
                add(arm, ["attempt", attempt["attempt_id"], attempt["state"], attempt["sdk_attempts"]], reason, resumable)
        for source in snapshot["sources"]:
            if source["state"] == "uncertain":
                add(arm, ["source", source["doc_id"]], "uncertain_source", True)
    if attempts > GLOBAL_MAX_CALLS:
        add("both", "global_budget", "global_call_budget_violation", False)
    return signals


def current_stop(output: Path) -> dict | None:
    events, _ = journal(output)
    if events and events[-1]["event"] == "stop":
        return events[-1]
    signals = pending_signals(output)
    if signals:
        append_event(output, {"event": "stop", "signals": signals, "resumable": all(s["resumable"] for s in signals.values())})
        return journal(output)[0][-1]
    return None


def acknowledge_stop(output: Path, expected_sha: str) -> None:
    stop = current_stop(output)
    if not stop or stop["sha256"] != expected_sha or not stop["resumable"]:
        raise ValueError("Exact resumable stop receipt required")
    # Acknowledging lets untouched sources proceed; uncertain attempts and their
    # source states remain unchanged and are never dispatched again.
    signal_ids = set(stop["signals"]) | set(pending_signals(output))
    for arm in ARMS:
        ledger = Ledger(output / "arms" / arm / "ledger.sqlite3")
        reason = ledger.snapshot()["settings"]["stop_reason"]
        if reason:
            ledger.acknowledge_stop(reason)
    append_event(output, {"event": "acknowledge_stop", "stop_sha256": expected_sha, "signal_ids": sorted(signal_ids)})


def comparison_summary(output: Path, protocol: dict) -> dict:
    arms = {}
    for arm in ARMS:
        report = gate.summary(output / "arms" / arm, arm_protocol(protocol, arm))
        report["all_sources_have_valid_model_coverage"] = report.pop("operational_gate_passed")
        arms[arm] = report
    stop = current_stop(output)
    return {"selected_originals": protocol["target_distinct_originals"], "selected_source_arm_slots": 2 * protocol["target_distinct_originals"],
            "arms": arms, "request_begun_attempts": sum(item["request_begun_attempts"] for item in arms.values()),
            "global_max_calls": GLOBAL_MAX_CALLS, "stop_receipt_sha256": stop["sha256"] if stop else None,
            "stop": stop, "labels_opened": False, "accuracy_measured": False, "usd_cost": None}


def checkpoint(output: Path, protocol: dict) -> dict:
    report = comparison_summary(output, protocol)
    directory = output / "checkpoints"
    directory.mkdir(exist_ok=True)
    write_new(directory / f"{time.time_ns()}.json", report)
    return report


def _seal(output: Path, protocol: dict, *, include_unattempted: bool = False) -> dict:
    for arm in ARMS:
        states = Ledger(output / "arms" / arm / "ledger.sqlite3").snapshot()["sources"]
        if any(row["state"] == "started" or row["state"] == "unstarted" and not include_unattempted for row in states):
            raise ValueError("Unfinished slots remain; explicit include-unattempted seal is required")
    # Publish intent first: interruption while exporting/sealing can never cause
    # a later invocation to send more paid requests into this campaign.
    if not (output / "seal-started.json").exists():
        write_new(output / "seal-started.json", {"include_unattempted": include_unattempted})
    for arm in ARMS:
        directory = output / "arms" / arm
        snapshot = Ledger(directory / "ledger.sqlite3").snapshot()
        candidates, documents = [], []
        rows = {row["doc_id"]: row for row in protocol["sources"]}
        for item in snapshot["sources"]:
            source = rows[item["doc_id"]]
            outcome = read_json(directory / "outcomes" / f"{item['doc_id']}.json") if item["receipt_sha256"] else None
            run_dir = directory / "product_runs" / f"model2000_{item['doc_id']}"
            candidate_path = run_dir / "candidates.jsonl"
            if item["state"] == "sealed" and outcome and outcome["metrics"] is not None and candidate_path.exists():
                candidate = read_json(candidate_path)
            else:
                candidate, _ = _placeholder(source, item["reason"] or item["state"])
            candidates.append(candidate)
            documents.append({"doc_id": item["doc_id"], "family": source["family"], "source_sha256": source["source_sha256"],
                              "state": item["state"], "reason": item["reason"] or item["state"], "outcome": outcome})
        artifacts = {"documents.json": encoded(documents), "ledger-snapshot.json": encoded(snapshot),
                     "candidates.jsonl": b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8") for row in candidates)}
        for name, payload in artifacts.items():
            path = directory / name
            if path.exists():
                if path.read_bytes() != payload:
                    raise ValueError("Previously published seal artifact changed")
            else:
                write_new_bytes(path, payload)
    report = comparison_summary(output, protocol)
    summary_path = output / "sealed-summary.json"
    if summary_path.exists():
        if read_json(summary_path) != report:
            raise ValueError("Previously published summary changed")
    else:
        write_new(summary_path, report)
    files = {}
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "prediction-seal.json" and ".sqlite3" not in path.name and path.suffix != ".lock":
            files[path.relative_to(output).as_posix()] = digest_file(path)
    sha = write_new(output / "prediction-seal.json", {"files": files, "all_slots_accounted": True,
                                                     "includes_unattempted": include_unattempted, "labels_opened": False})
    return {"prediction_seal_sha256": sha, "summary": report}


def run(output: Path, sha: str, *, api_key_env: str, resume: bool = False, batches: int | None = None,
        acknowledge: str | None = None) -> dict:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env) or not os.environ.get(api_key_env, "").strip():
        raise ValueError("Credential environment variable required")
    if batches is not None and (type(batches) is not int or batches < 1):
        raise ValueError("Positive batch limit required")
    if acknowledge and not resume:
        raise ValueError("Only explicit resume may acknowledge a stop")
    with exclusive_run_lock(output / "run.lock"):
        if (output / "seal-started.json").exists() or (output / "prediction-seal.json").exists():
            raise ValueError("Sealing began; paid execution is permanently closed")
        raw = read_json(output / "protocol.json")
        config = raw["runtime"]["ocr_config"]
        with configured_environment(Path(config["python"]), Path(config["work_dir"])):
            protocol = verify_freeze(output, sha)
            if journal(output)[0] and not resume:
                raise ValueError("Campaign already started; use resume")
            if resume:
                for arm in ARMS:
                    Ledger(output / "arms" / arm / "ledger.sqlite3").recover_interrupted()
            else:
                append_event(output, {"event": "start", "protocol_sha256": sha})
            current_stop(output)
            if acknowledge:
                acknowledge_stop(output, acknowledge)
            if current_stop(output):
                return checkpoint(output, protocol)
            rows = {row["doc_id"]: row for row in protocol["sources"]}
            with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
                completed_batches = 0
                width = 2 * BATCH_ORIGINALS
                for start in range(0, len(protocol["schedule"]), width):
                    dispatched = False
                    for slot in protocol["schedule"][start:start + width]:
                        if current_stop(output):
                            break
                        arm, doc_id = slot["arm"], slot["doc_id"]
                        directory = output / "arms" / arm
                        ledger = Ledger(directory / "ledger.sqlite3")
                        if not ledger.claim(doc_id):
                            continue
                        dispatched = True
                        try:
                            pool.submit(gate._run_source, str(directory), rows[doc_id], arm_protocol(protocol, arm), api_key_env).result()
                        except Exception:  # noqa: BLE001 - redact worker exception, stop both arms
                            ledger.stop("worker_process_failed")
                            ledger.recover_interrupted()
                        if current_stop(output):
                            break
                    if dispatched:
                        checkpoint(output, protocol)
                        completed_batches += 1
                    if current_stop(output) or (batches is not None and completed_batches >= batches):
                        break
            for arm in ARMS:
                Ledger(output / "arms" / arm / "ledger.sqlite3").recover_interrupted()
            report = checkpoint(output, protocol)
            if not any(arm["source_states"].get("unstarted") for arm in report["arms"].values()):
                verify_freeze(output, sha)
                return _seal(output, protocol)
            return report


def seal(output: Path, sha: str, *, include_unattempted: bool = False) -> dict:
    with exclusive_run_lock(output / "run.lock"):
        if (output / "prediction-seal.json").exists():
            raise ValueError("Prediction seal already exists")
        config = read_json(output / "protocol.json")["runtime"]["ocr_config"]
        with configured_environment(Path(config["python"]), Path(config["work_dir"])):
            protocol = verify_freeze(output, sha)
            for arm in ARMS:
                Ledger(output / "arms" / arm / "ledger.sqlite3").recover_interrupted()
            return _seal(output, protocol, include_unattempted=include_unattempted)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    for name in ("inventory", "baseline", "output", "rapidocr-python", "scratch"):
        prepare_parser.add_argument("--" + name, type=Path, required=True)
    for command in ("run", "resume", "seal"):
        child = commands.add_parser(command)
        child.add_argument("--output", type=Path, required=True)
        child.add_argument("--protocol-sha256", required=True)
        if command == "seal":
            child.add_argument("--include-unattempted", action="store_true")
        else:
            child.add_argument("--api-key-env", default="ICORE_API_KEY")
            child.add_argument("--batches", type=int)
            if command == "resume":
                child.add_argument("--acknowledge-stop", help="Exact resumable stop receipt SHA; never retries an uncertain slot")
    args = parser.parse_args()
    if args.command == "prepare":
        result = {"protocol_sha256": prepare(args.inventory, args.baseline, args.output,
                                             rapidocr_python=args.rapidocr_python, scratch=args.scratch)}
    elif args.command == "seal":
        result = seal(args.output, args.protocol_sha256, include_unattempted=args.include_unattempted)
    else:
        result = run(args.output, args.protocol_sha256, api_key_env=args.api_key_env, resume=args.command == "resume",
                     batches=args.batches, acknowledge=getattr(args, "acknowledge_stop", None))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

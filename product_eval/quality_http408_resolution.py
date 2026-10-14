"""Explicit HTTP 408 stop correction, without changing frozen predictions or code.

Scope: research_evidence / keep. Preparation makes an append-only proof bundle;
application requires its exact hash. Only the two coordinator signals arising
from one sealed HTTP 408 reply can be acknowledged. No source is retried and
the original request_rejected classification remains in all outcome metrics.
"""
from __future__ import annotations

import math
import time
from pathlib import Path, PurePosixPath

from product_eval import quality_comparison as quality
from product_eval.final_gate_freeze import SHA, digest_file, digest_json, encoded, read_json, write_new_bytes
from product_eval.final_gate_ledger import Ledger, exclusive_run_lock
from product_eval.product_candidate_dev import configured_environment

FOLDER = "http408-resolutions"
EVENT = "http408_resolution"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    require(bool(name) and not relative.is_absolute() and relative.as_posix() == name
            and not {".", ".."}.intersection(relative.parts) and ":" not in name and "\\" not in name,
            "Unsafe resolution proof path")
    path = root.joinpath(*relative.parts)
    require(not any(part.is_symlink() for part in (path, *path.parents)) and path.is_file(),
            "Missing or symlinked resolution proof")
    return path


def _snapshots(output: Path, *, sealed: bool = False) -> dict:
    return {arm: read_json(output / "arms" / arm / "ledger-snapshot.json") if sealed
            else Ledger(output / "arms" / arm / "ledger.sqlite3").snapshot() for arm in quality.ARMS}


def _open(output: Path) -> None:
    require(not (output / "seal-started.json").exists() and not (output / "prediction-seal.json").exists(),
            "Sealing began; execution resolution is closed")


def _environment(output: Path):
    config = read_json(output / "protocol.json")["runtime"]["ocr_config"]
    return configured_environment(Path(config["python"]), Path(config["work_dir"]))


def _incident(output: Path, snapshots: dict, stop: dict) -> dict:
    """Derive the only allowable signal set from immutable request/reply evidence."""
    require(stop["event"] == "stop" and stop["resumable"] is False and len(stop["signals"]) == 2,
            "Only an isolated nonresumable HTTP408 incident can be resolved")
    affected = [arm for arm, state in snapshots.items() if state["settings"]["stop_reason"]]
    require(len(affected) == 1, "Mixed ledger stops cannot be resolved")
    arm = affected[0]
    state = snapshots[arm]
    require(state["settings"]["stop_reason"] == "request_rejected" and state["attempts"],
            "Exact request_rejected ledger stop required")
    require(all(row["state"] != "started" for value in snapshots.values() for row in value["sources"])
            and all(row["state"] != "request_begun" for value in snapshots.values() for row in value["attempts"]),
            "Pending calls or sources cannot be resolved")
    attempt = state["attempts"][-1]
    require(attempt["state"] == "replied" and attempt["error_category"] == "request_rejected"
            and attempt["sdk_attempts"] == 1, "Exact terminal rejected attempt required")
    expected = {}
    for identity in (["ledger", len(state["attempts"]), len(state["controls"])],
                     ["attempt", attempt["attempt_id"], "replied", 1]):
        key = digest_json({"arm": arm, "identity": identity, "reason": "request_rejected"})
        expected[key] = {"arm": arm, "reason": "request_rejected", "resumable": False}
    require(stop["signals"] == expected, "Mixed or unknown stop signals cannot be resolved")
    reply_path = _path(output, f"arms/{arm}/replies/{attempt['attempt_id']:06d}.json")
    require(digest_file(reply_path) == attempt["reply_sha256"], "Incident reply hash differs")
    reply = read_json(reply_path)
    require(reply.get("error") == "http_408" and reply.get("error_category") == "request_rejected"
            and reply.get("sdk_attempts") == 1 and reply.get("text") == ""
            and reply.get("finish_reason") is None and not reply.get("refusal")
            and reply.get("prompt_tokens") is None and reply.get("completion_tokens") is None
            and isinstance(reply.get("latency_ms"), (float, int)) and math.isfinite(reply["latency_ms"])
            and reply["latency_ms"] >= 0, "Only a sealed HTTP408 reply with unknown usage qualifies")
    require(all(reply.get(key) == attempt[key] for key in (
        "prompt_tokens", "completion_tokens", "latency_ms", "finish_reason", "refusal", "error_category", "sdk_attempts")),
        "Incident reply accounting differs")
    source = next(row for row in state["sources"] if row["doc_id"] == attempt["doc_id"])
    require(source["state"] == "sealed" and bool(source["receipt_sha256"]), "Incident source must remain sealed")
    outcome_path = _path(output, f"arms/{arm}/outcomes/{source['doc_id']}.json")
    require(digest_file(outcome_path) == source["receipt_sha256"], "Incident outcome hash differs")
    outcome = read_json(outcome_path)
    require(outcome["metrics"] is not None and outcome["metrics"]["valid_full_coverage"] is False
            and outcome["metrics"]["provider_finished"] is False and outcome["failure_stage"] is None,
            "Incident outcome must remain an invalid provider result")
    return {"arm": arm, "doc_id": source["doc_id"], "attempt_id": attempt["attempt_id"],
            "request_sha256": attempt["request_sha256"], "reply_sha256": attempt["reply_sha256"],
            "outcome_sha256": source["receipt_sha256"], "signal_ids": sorted(expected)}


def _publish(path: Path, raw: bytes) -> str:
    # A crash during preparation is recoverable only when the existing bytes
    # match exactly. A partial write fails closed and is never overwritten.
    if path.exists():
        require(path.read_bytes() == raw, "Existing resolution proof differs")
        return digest_file(path)
    return write_new_bytes(path, raw)


def prepare(output: Path, protocol_sha: str, *, stop_sha: str, transport_amendment_sha256: str,
            prior_resolution_sha256: list[str] | tuple[str, ...] = ()) -> str:
    """Pin evidence without clearing the stop or constructing a model client."""
    with exclusive_run_lock(output / "run.lock"), _environment(output):
        _open(output)
        quality.verify_freeze(output, protocol_sha)
        require(bool(SHA.fullmatch(stop_sha)) and bool(SHA.fullmatch(transport_amendment_sha256))
                and digest_file(output / "transport-amendment/amendment.json") == transport_amendment_sha256,
                "Exact stop and transport amendment hashes required")
        events, last = quality.journal(output)
        require(bool(events) and last == stop_sha, "Exact latest stop hash required")
        snapshots = _snapshots(output)
        incident = _incident(output, snapshots, events[-1])
        require(quality.pending_signals(output) == events[-1]["signals"], "Pending signals differ from reviewed stop")
        verify_all(output, prior_resolution_sha256, _preparing_stop=stop_sha)
        folder = output / FOLDER / stop_sha
        folder.mkdir(parents=True, exist_ok=True)
        baselines = {arm: _publish(folder / f"baseline-{arm}.json", encoded(state)) for arm, state in snapshots.items()}
        implementation_sha = _publish(folder / "implementation.py", Path(__file__).read_bytes())
        proofs = {}
        for path in sorted(output.rglob("*")):
            require(not path.is_symlink(), "Campaign symlink is not supported")
            name = path.relative_to(output).as_posix()
            if path.is_file() and not name.startswith(FOLDER + "/") and ".sqlite3" not in path.name and path.suffix != ".lock":
                proofs[name] = digest_file(path)
        receipt = {"version": 1, "type": "http408_stop_classification_resolution", "protocol_sha256": protocol_sha,
            "stop_sha256": stop_sha, "transport_amendment_sha256": transport_amendment_sha256,
            "prior_resolution_sha256": sorted(prior_resolution_sha256),
            "baseline_sha256": baselines, "implementation_sha256": implementation_sha,
            "proof_files": proofs, "incident": incident, "labels_opened": False, "replay_allowed": False,
            "original_classification": "request_rejected", "execution_interpretation": "provider_http_timeout",
            "metrics_reclassified": False, "usage_unknown": True,
            "scope": "Acknowledge only the recorded HTTP408 stop; retain its failed source and all denominators; permit untouched slots only."}
        return _publish(folder / "resolution.json", encoded(receipt))


def _read(output: Path, expected_sha: str) -> tuple[dict, dict, dict]:
    require(bool(SHA.fullmatch(expected_sha)), "Explicit resolution SHA required")
    matches = [path for path in (output / FOLDER).glob("*/resolution.json") if digest_file(path) == expected_sha]
    require(len(matches) == 1, "Resolution receipt hash differs or is missing")
    path = matches[0]
    receipt = read_json(path)
    require(receipt["version"] == 1 and receipt["type"] == "http408_stop_classification_resolution"
            and receipt["stop_sha256"] == path.parent.name and receipt["labels_opened"] is False
            and receipt["replay_allowed"] is False and receipt["metrics_reclassified"] is False
            and receipt["usage_unknown"] is True and receipt["original_classification"] == "request_rejected"
            and receipt["execution_interpretation"] == "provider_http_timeout", "Unsupported HTTP408 resolution")
    require(digest_file(output / "protocol.json") == receipt["protocol_sha256"]
            and digest_file(output / "transport-amendment/amendment.json") == receipt["transport_amendment_sha256"],
            "Resolution protocol or transport binding differs")
    require(digest_file(_path(path.parent, "implementation.py")) == digest_file(Path(__file__))
            == receipt["implementation_sha256"], "Resolution implementation changed")
    require(set(p.name for p in path.parent.iterdir()) == {"resolution.json", "implementation.py", "baseline-text.json", "baseline-candidate.json"},
            "Unexpected resolution artifact")
    baseline = {}
    for arm in quality.ARMS:
        target = _path(path.parent, f"baseline-{arm}.json")
        require(digest_file(target) == receipt["baseline_sha256"][arm], "Resolution baseline changed")
        baseline[arm] = read_json(target)
    for name, sha in receipt["proof_files"].items():
        require(bool(SHA.fullmatch(sha)) and digest_file(_path(output, name)) == sha, "Prior campaign artifact changed")
    events, _ = quality.journal(output)
    stops = [event for event in events if event["sha256"] == receipt["stop_sha256"]]
    require(len(stops) == 1 and _incident(output, baseline, stops[0]) == receipt["incident"], "Incident proof differs")
    return receipt, baseline, stops[0]


def _acknowledgement(receipt: dict, sha: str) -> dict:
    return {"event": "acknowledge_stop", "stop_sha256": receipt["stop_sha256"],
            "signal_ids": receipt["incident"]["signal_ids"], "http408_resolution_sha256": sha}


def _check_prefix(baseline: dict, current: dict) -> None:
    for arm in quality.ARMS:
        before, now = baseline[arm], current[arm]
        require(now["attempts"][:len(before["attempts"])] == before["attempts"], "Prior paid attempts changed")
        require(now["controls"][:len(before["controls"])] == before["controls"], "Prior ledger controls changed")
        require([row["doc_id"] for row in now["sources"]] == [row["doc_id"] for row in before["sources"]],
                "Source denominators changed")
        for old, new in zip(before["sources"], now["sources"], strict=True):
            require(old["state"] == "unstarted" or old == new, "Previously attempted source changed or replayed")
        eligible = {row["doc_id"] for row in before["sources"] if row["state"] == "unstarted"}
        require(all(row["doc_id"] in eligible for row in now["attempts"][len(before["attempts"]):]),
                "Attempted source was replayed")
        require(all(now["settings"][key] == before["settings"][key] for key in ("protocol_sha256", "max_calls")),
                "Ledger protocol or budget changed")


def verify_all(output: Path, expected_shas: list[str] | tuple[str, ...], *, sealed: bool = False,
               _preparing_stop: str | None = None) -> list[dict]:
    """Require explicit hashes and application proofs before execution or labels."""
    require(len(set(expected_shas)) == len(expected_shas), "Duplicate resolution hash")
    # During prepare/apply only the current stopped incident may have an
    # unfinished proof bundle. Every earlier resolution still requires a pin.
    paths = [path for path in (output / FOLDER).glob("*/resolution.json") if path.parent.name != _preparing_stop]
    folders = [path for path in (output / FOLDER).iterdir() if path.name != _preparing_stop] if (output / FOLDER).exists() else []
    require({digest_file(path) for path in paths} == set(expected_shas)
            and len(folders) == len(paths),
            "Explicit complete HTTP408 resolution hashes required")
    current = _snapshots(output, sealed=sealed)
    events, _ = quality.journal(output)
    result, receipts, applied_controls = [], {}, set()
    for sha in expected_shas:
        receipt, baseline, stop = _read(output, sha)
        receipts[sha] = receipt
        _check_prefix(baseline, current)
        arm = receipt["incident"]["arm"]
        controls = current[arm]["controls"]
        index = len(baseline[arm]["controls"])
        require(len(controls) > index and controls[index]["event"] == EVENT and controls[index]["reason"] == sha,
                "HTTP408 resolution ledger transaction is absent")
        applied_controls.add((arm, controls[index]["event_id"], sha))
        event_index = next(index for index, item in enumerate(events) if item["sha256"] == stop["sha256"]) + 1
        require(len(events) > event_index and all(events[event_index].get(key) == value
                for key, value in _acknowledgement(receipt, sha).items()), "HTTP408 resolution journal acknowledgement is absent")
        result.append({"resolution_sha256": sha, "stop_sha256": stop["sha256"], **receipt["incident"],
                       "original_classification": "request_rejected", "execution_interpretation": "provider_http_timeout",
                       "metrics_reclassified": False, "usage_unknown": True, "replay_allowed": False})
    pending_sha = None
    if _preparing_stop and (output / FOLDER / _preparing_stop / "resolution.json").is_file():
        pending_sha = digest_file(output / FOLDER / _preparing_stop / "resolution.json")
    require(all((arm, row["event_id"], row["reason"]) in applied_controls or row["reason"] == pending_sha
                for arm, state in current.items() for row in state["controls"] if row["event"] == EVENT),
            "Unpinned HTTP408 ledger resolution")
    encountered = set()
    for event in events:
        if event["event"] == "acknowledge_stop":
            stopped = next((item for item in events if item["sha256"] == event["stop_sha256"]), None)
            if stopped and stopped.get("resumable") is False:
                sha = event.get("http408_resolution_sha256")
                require(sha in receipts,
                        "Unpinned nonresumable stop acknowledgement")
                require(sha not in encountered and all(event.get(key) == value for key, value in _acknowledgement(receipts[sha], sha).items())
                        and receipts[sha]["prior_resolution_sha256"] == sorted(encountered),
                        "Duplicated or out-of-order HTTP408 acknowledgement")
                encountered.add(sha)
    return result


def apply(output: Path, expected_sha: str, *, prior_resolution_sha256: list[str] | tuple[str, ...] = ()) -> dict:
    """Clear only a reviewed isolated stop; repeat safely after a process death."""
    with exclusive_run_lock(output / "run.lock"), _environment(output):
        _open(output)
        receipt, baseline, stop = _read(output, expected_sha)
        require(receipt["prior_resolution_sha256"] == sorted(prior_resolution_sha256), "Explicit prior resolution hashes required")
        quality.verify_freeze(output, receipt["protocol_sha256"])
        current = _snapshots(output)
        _check_prefix(baseline, current)
        arm = receipt["incident"]["arm"]
        events, last = quality.journal(output)
        if any(event.get("http408_resolution_sha256") == expected_sha for event in events):
            verify_all(output, [*prior_resolution_sha256, expected_sha])
            return {"resolution_sha256": expected_sha, "already_applied": True, "model_calls": 0, "labels_opened": False}
        verify_all(output, prior_resolution_sha256, _preparing_stop=receipt["stop_sha256"])
        require(last == stop["sha256"], "Journal advanced before resolution application")
        require(all(current[name] == baseline[name] for name in quality.ARMS if name != arm), "Other arm changed before resolution")
        before, now = baseline[arm], current[arm]
        require(now["sources"] == before["sources"] and now["attempts"] == before["attempts"],
                "Attempt ledger advanced before resolution")
        ledger = Ledger(output / "arms" / arm / "ledger.sqlite3")
        if now["controls"] == before["controls"]:
            require(now == before and quality.pending_signals(output) == stop["signals"], "Stop changed before resolution")
            with ledger.transaction() as db:
                require(dict(db.execute("SELECT key, value FROM settings")) == before["settings"], "Ledger changed before transaction")
                db.execute("INSERT INTO controls(event, reason, updated) VALUES (?, ?, ?)", (EVENT, expected_sha, time.time()))
                db.execute("UPDATE settings SET value='' WHERE key='stop_reason'")
                db.execute("UPDATE settings SET value='0' WHERE key='consecutive_transport_failures'")
        else:
            require(len(now["controls"]) == len(before["controls"]) + 1
                    and now["controls"][-1]["event"] == EVENT and now["controls"][-1]["reason"] == expected_sha
                    and now["settings"] == {**before["settings"], "stop_reason": "", "consecutive_transport_failures": "0"},
                    "Interrupted resolution state differs")
        # The old stop remains the journal head until this append succeeds. A
        # crash after the transaction therefore cannot silently resume dispatch.
        quality.append_event(output, _acknowledgement(receipt, expected_sha))
        return {"resolution_sha256": expected_sha, "already_applied": False, "model_calls": 0, "labels_opened": False}

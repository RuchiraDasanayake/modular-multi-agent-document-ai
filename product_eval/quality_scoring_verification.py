"""Offline quality240 prediction verification; this module never opens labels."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.strict_output import (
    compile_confirmed_values_response_format,
    parse_confirmed_strict_values_reply,
)
from idpo.product_auto.visual_output import (
    compile_visual_response_format,
    parse_visual_values_reply,
)
from product_eval import final_model_gate as gate
from product_eval import quality_comparison as quality
from product_eval.contracts import load_jsonl
from product_eval.execution import verify_result_receipts, verify_run
from product_eval.final_gate_freeze import SHA, digest_file, read_json

PROTOCOL_SHA256 = "3cf41aac59be90d610a4479d1d9876bbf77894e9d55162983a8713b510594075"
ANALYSIS_SHA256 = "68ba30cb8831a5805c49b0b340a83e88429720de249a2986f92efc4ea676974e"
PREREGISTRATION_SHA256 = "7d267e6bc129c62e9c19c1323ac71da358a659132b213dc232e5af6c0d77ad30"
FROZEN_MODULES = (
    "product_eval/scorer.py", "product_eval/scoped_assessment.py", "product_eval/linked_rows.py",
    "product_eval/contracts.py", "product_eval/datasets/vrdu.py", "product_eval/execution.py",
    "product_eval/final_model_gate.py", "product_eval/quality_comparison.py",
    "idpo/product_auto/confirmed_schema.py", "idpo/product_auto/strict_output.py",
    "idpo/product_auto/visual_output.py", "idpo/product_auto/logic.py",
    "idpo/product_auto/long_document.py", "idpo/product_auto/segments.py",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sealed_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    require(bool(name) and not relative.is_absolute() and relative.as_posix() == name
            and not {".", ".."}.intersection(relative.parts) and ":" not in name and "\\" not in name,
            "Unsafe sealed artifact path")
    path = root.joinpath(*relative.parts)
    require(not any(part.is_symlink() for part in (path, *path.parents)), "Sealed symlink is not supported")
    require(path.resolve().is_relative_to(root.resolve()) and path.is_file(), "Missing sealed artifact")
    return path


def verify_files(root: Path, seal_sha256: str) -> dict:
    require(bool(SHA.fullmatch(seal_sha256)) and digest_file(root / "prediction-seal.json") == seal_sha256,
            "Prediction seal SHA mismatch")
    seal = read_json(root / "prediction-seal.json")
    require(seal.get("all_slots_accounted") is True and seal.get("labels_opened") is False
            and isinstance(seal.get("files"), dict), "Prediction seal is incomplete")
    for name, expected in seal["files"].items():
        require(isinstance(expected, str) and bool(SHA.fullmatch(expected))
                and digest_file(sealed_path(root, name)) == expected, "Sealed artifact SHA mismatch")
    actual = set()
    for path in root.rglob("*"):
        require(not path.is_symlink(), "Campaign symlink is not supported")
        if path.is_file() and path.name != "prediction-seal.json" and ".sqlite3" not in path.name and path.suffix != ".lock":
            actual.add(path.relative_to(root).as_posix())
    require(actual == set(seal["files"]), "Unsealed or missing campaign artifact")
    require("seal-started.json" in actual, "Paid execution is not permanently closed")
    return seal


def verify_frozen_modules(protocol: dict) -> dict:
    root = Path(__file__).resolve().parents[1]
    receipts = {}
    for name in FROZEN_MODULES:
        raw = (root / name).read_bytes()
        expected = protocol["code"]["python_source_sha256"].get(name)
        actual = hashlib.sha256(raw).hexdigest()
        receipt = {"frozen_raw_sha256": expected, "analysis_raw_sha256": actual, "comparison": "exact_bytes"}
        if actual != expected:
            commit = protocol["code"].get("commit", "")
            require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "Frozen Git commit is invalid")
            blob = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=root, stderr=subprocess.DEVNULL)
            receipt.update(_newline_receipt(raw, expected, blob))
            receipt["frozen_git_commit"] = commit
        receipts[name] = receipt
    return receipts


def _newline_receipt(raw: bytes, expected: str, registered_blob: bytes) -> dict:
    """Accept only checkout newline conversion anchored to the frozen Git object."""
    canonical = registered_blob.replace(b"\r\n", b"\n")
    canonical_sha = hashlib.sha256(canonical).hexdigest()
    require(expected == canonical_sha and raw.replace(b"\r\n", b"\n") == canonical,
            "Frozen scoring or receipt-verification implementation changed")
    return {"comparison": "crlf_to_lf_only", "registered_git_blob_sha256": hashlib.sha256(registered_blob).hexdigest(),
            "canonical_source_sha256": canonical_sha}


def _wire_request(path: Path, schema, profile: dict, sidecar: dict | None, index: int) -> tuple[dict, dict]:
    body = read_json(path)
    require(body["model"] == profile["model"] and body["max_tokens"] == profile["max_tokens"],
            "Request model profile differs")
    content = body["messages"][1]["content"]
    visual = isinstance(content, list)
    prompt = content[0]["text"] if visual else content
    # Strict/segmented text prompts append fixed instructions after this JSON.
    data, _ = json.JSONDecoder().raw_decode(prompt.split("Document data: ", 1)[1])
    require(data["fields"] == list(schema.fields) and data.get("user_intent", "") == schema.intent,
            "Request differs from frozen family schema")
    compiler = compile_visual_response_format if visual else compile_confirmed_values_response_format
    require(body["response_format"] == compiler(schema.candidate_fields), "Request strict format differs")
    receipt = {"kind": "visual" if visual else "text", "request_sha256": digest_file(path)}
    if sidecar is not None and not visual:
        from idpo.product_auto.long_document import segment_pages
        from idpo.product_auto.segments import plan_segments

        expected = sidecar["pages"]
        if sidecar.get("long_document_plan") is not None:
            plan = plan_segments(expected, max_chars=24_000)
            require(plan.supported and index < len(plan.segments), "Request segment is not in the source plan")
            expected = segment_pages(plan.segments[index])
        require(data["pages"] == expected, "Request text differs from exact source segment")
    if sidecar is not None and visual:
        recorded = sidecar["visual_document"]["requests"][index]
        helper = {key: value for key, value in recorded.items() if key not in {"outcome", "model_call_index", "usage"}}
        require(helper["request_sha256"] == receipt["request_sha256"] and helper["request_bytes"] == path.stat().st_size,
                "Visual request receipt differs from wire bytes")
        images = [part["image_url"]["url"] for part in content if part["type"] == "image_url"]
        require(len(images) == len(data["pages"]) == len(helper["pages"]), "Visual payload page count differs")
        for url, page, item in zip(images, data["pages"], helper["pages"], strict=True):
            require(url.startswith("data:image/png;base64,"), "Unexpected visual payload format")
            png = base64.b64decode(url.split(",", 1)[1], validate=True)
            require(hashlib.sha256(png).hexdigest() == item["payload_png_sha256"] and len(png) == item["payload_bytes"]
                    and page["page"] == item["page"]
                    and hashlib.sha256(page["text"].encode()).hexdigest() == item["ocr_text_sha256"],
                    "Visual page payload differs from receipt")
            require(any(value["page"] == page["page"] and value["text"] == page["text"] for value in sidecar["pages"]),
                    "Visual request text differs from source page")
        receipt["receipt"] = helper
    return receipt, data


def _attempts(directory: Path, rows: list[dict], schema, profile: dict, sidecar: dict | None) -> tuple[list, list, int]:
    replies, requests, valid = [], [], 0
    require([row["ordinal"] for row in rows] == list(range(1, len(rows) + 1)) and len(rows) <= 4,
            "Per-source request sequence differs")
    for index, row in enumerate(rows):
        path = directory / "requests" / row["doc_id"] / f"{row['request_sha256']}.json"
        request, data = _wire_request(path, schema, profile, sidecar, index)
        requests.append(request)
        if row["reply_sha256"] is None:
            require(row["state"] != "replied", "Completed attempt lacks reply")
            continue
        reply = read_json(directory / "replies" / f"{row['attempt_id']:06d}.json")
        require(all(reply.get(key) == row[key] for key in (
            "prompt_tokens", "completion_tokens", "latency_ms", "finish_reason", "refusal", "error_category", "sdk_attempts")),
            "Ledger reply accounting differs")
        replies.append(reply)
        parse = parse_visual_values_reply if request["kind"] == "visual" else parse_confirmed_strict_values_reply
        valid += bool(row["state"] == "replied" and not reply.get("error") and not reply.get("refusal")
                      and reply.get("finish_reason") == "stop" and reply.get("sdk_attempts") == 1
                      and parse(reply["text"], schema.candidate_fields, data["pages"]) is not None)
    return replies, requests, valid


def verify_campaign(root: Path, seal_sha256: str, *, transport_amendment_sha256: str | None = None) -> dict:
    """Complete all source/artifact checks before returning anything usable for scoring."""
    root = root.resolve()
    seal = verify_files(root, seal_sha256)
    for name, sha in (("protocol.json", PROTOCOL_SHA256), ("analysis-plan.json", ANALYSIS_SHA256),
                      ("analysis-preregistration.json", PREREGISTRATION_SHA256)):
        require(seal["files"].get(name) == sha, "Preregistered protocol or analysis plan differs")
    protocol, plan, prereg = (read_json(root / name) for name in (
        "protocol.json", "analysis-plan.json", "analysis-preregistration.json"))
    require(protocol["mode"] == "paired_quality240" and protocol["labels_opened"] is False,
            "Unknown quality campaign")
    require(plan["frozen_execution_protocol_sha256"] == prereg["protocol_sha256"] == PROTOCOL_SHA256
            and prereg["analysis_plan_sha256"] == ANALYSIS_SHA256
            and prereg["arm_model_attempts"] == {arm: 0 for arm in quality.ARMS}, "Analysis binding differs")
    require(digest_file(root / "source-inventory.json") == quality.INVENTORY_SHA256
            and protocol["sources"] == quality.source_rows(read_json(root / "source-inventory.json"))
            and protocol["schedule"] == quality.schedule(protocol["sources"]), "Frozen source inventory differs")
    require({key: value["sha256"] for key, value in protocol["schemas"].items()} == quality.SCHEMA_SHA256,
            "Family schemas differ")
    module_hashes = verify_frozen_modules(protocol)
    quality.verify_sources(protocol["sources"])
    transport = None
    if (root / "transport-amendment").exists() or transport_amendment_sha256 is not None:
        from product_eval.quality_transport import verify_amendment

        require(transport_amendment_sha256 is not None, "Explicit endpoint amendment SHA required")
        transport = verify_amendment(root, protocol, transport_amendment_sha256, sealed=True)
    sources = {row["doc_id"]: row for row in protocol["sources"]}
    arms, product_receipts, attempts_total = {}, 0, 0
    for arm in quality.ARMS:
        directory = root / "arms" / arm
        profile = protocol["profiles"][arm]
        require(profile["visual_document_profile"] == quality.ARMS[arm] and profile["max_calls"] == quality.ARM_MAX_CALLS,
                "Frozen arm profile differs")
        schemas = {family: load_confirmed_schema(directory / item["path"], item["sha256"])
                   for family, item in protocol["schemas"].items()}
        state = read_json(directory / "ledger-snapshot.json")
        gate._verify_existing(directory, state, quality.arm_protocol(protocol, arm), PROTOCOL_SHA256)
        require(len(state["attempts"]) <= quality.ARM_MAX_CALLS, "Arm call budget exceeded")
        require([row["attempt_id"] for row in state["attempts"]] == list(range(1, len(state["attempts"]) + 1)),
                "Attempt identities differ")
        require(all(row["doc_id"] in sources for row in state["attempts"]), "Unknown attempted original")
        attempts_total += len(state["attempts"])
        documents = read_json(directory / "documents.json")
        candidates = load_jsonl(directory / "candidates.jsonl", kind="candidate")
        require([row["doc_id"] for row in documents] == list(sources) and set(candidates) == set(sources),
                "Both arms must include every frozen source")
        results = {}
        for document, slot in zip(documents, state["sources"], strict=True):
            doc_id = slot["doc_id"]
            source, candidate = sources[doc_id], candidates[doc_id]
            require(slot["state"] in {"sealed", "uncertain", "unstarted"}, "Unclosed source remains")
            outcome = read_json(directory / "outcomes" / f"{doc_id}.json") if slot["receipt_sha256"] else None
            require(document == {"doc_id": doc_id, "family": source["family"], "source_sha256": source["source_sha256"],
                                 "state": slot["state"], "reason": slot["reason"] or slot["state"], "outcome": outcome},
                    "Document export differs from sealed ledger")
            sidecar, pages, metrics = None, None, None
            if outcome and outcome["metrics"] is not None:
                run_dir = directory / "product_runs" / f"model2000_{doc_id}"
                require(verify_run(run_dir, min_unique=1, verify_sources=False)["documents"] == 1
                        and verify_result_receipts([run_dir]) == 1, "Product result receipt differs")
                manifest = read_json(run_dir / "manifest.jsonl")
                require(manifest["doc_id"] == doc_id and manifest["source_sha256"] == source["source_sha256"]
                        and manifest["source_path"] == source["source_path"]
                        and manifest["source_hash_kind"] == "raw_file", "Product original identity differs")
                sidecar = read_json(run_dir / "docs" / doc_id / "result.json")
                pages = sidecar["pages"]
                product_receipts += 1
            rows = [row for row in state["attempts"] if row["doc_id"] == doc_id]
            replies, requests, valid_replies = _attempts(directory, rows, schemas[source["family"]], profile, sidecar)
            if sidecar is not None:
                require(manifest["model_call_count"] == len(replies) == len(sidecar["model_calls"]),
                        "Product and ledger call counts differ")
                metrics = gate.source_metrics(sidecar, replies, schemas[source["family"]], requests=requests)
                require(metrics == outcome["metrics"], "Operational metric receipt differs on recomputation")
                require(sidecar["source_container_sha256"] == source["source_sha256"], "Sidecar source differs")
            if slot["state"] == "sealed" and metrics is not None:
                require(candidate == sidecar["candidate"], "Exported candidate differs from product result")
            else:
                require(candidate == quality._placeholder(source, document["reason"])[0], "Uncertain/unstarted slot is not empty")
            eligible = bool(slot["state"] == "sealed" and metrics and metrics["valid_full_coverage"])
            visual = sidecar.get("visual_document", {}) if sidecar else {}
            results[doc_id] = {"candidate": candidate, "pages": pages, "metrics": metrics, "eligible": eligible,
                               "state": slot["state"], "reason": document["reason"], "attempts": rows,
                               "request_kinds": [item["kind"] for item in requests],
                               "visual_coverage": {key: visual.get(key) for key in (
                                   "route", "source_pages", "planned_pages", "attempted_pages", "valid_pages",
                                   "planned_requests", "attempted_requests", "valid_requests", "full_source_covered")},
                               "valid_strict_replies": valid_replies,
                               "duration_ms": outcome["duration_ms"] if outcome else None}
        arms[arm] = results
    require(attempts_total <= quality.GLOBAL_MAX_CALLS, "Global call budget exceeded")
    return {"protocol": protocol, "analysis_plan": plan, "sources": sources, "arms": arms,
            "transport_amendment": transport,
            "receipt": {"prediction_seal_sha256": seal_sha256, "protocol_sha256": PROTOCOL_SHA256,
                        "transport_amendment": transport,
                        "analysis_plan_sha256": ANALYSIS_SHA256, "preregistration_sha256": PREREGISTRATION_SHA256,
                        "verified_sealed_files": len(seal["files"]), "verified_originals": len(sources),
                        "verified_product_results": product_receipts, "verified_request_attempts": attempts_total,
                        "frozen_module_sha256": module_hashes, "labels_opened_before_verification": False,
                        "source_family_counts": dict(Counter(row["family"] for row in sources.values()))}}

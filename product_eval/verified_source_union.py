"""Account for distinct originals using completed, externally pinned study reports only.

Never opens source files, predictions, labels, provider replies or a live ledger.
Prior independent verification is an input attestation, not rerun here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from collections import Counter
from pathlib import Path

SHA = re.compile(r"[a-f0-9]{64}")
EXPECTED_FAMILIES = {
    "operational": {"registration-form": 897, "ad-buy-form": 305, "receipt": 798},
    "quality_candidate": {"registration-form": 100, "ad-buy-form": 100, "receipt": 40},
}
INFERENCE_PROFILE = {
    "model": "innobot-luna-6", "ocr_engine": "rapidocr",
    "response_format_profile": "strict_confirmed_values_v1",
    "long_document_profile": "bounded_text_segments_v1",
    "visual_document_profile": "bounded_visual_selective_v2",
    "max_tokens": 8192, "timeout_s": 180, "max_calls_per_source": 4,
}
STAGES = ("selected", "request_begun", "valid_full_coverage", "non_null_full_coverage")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _hash(value: object) -> str:
    require(isinstance(value, str) and bool(SHA.fullmatch(value)), "Invalid SHA-256 pin")
    return value


def _integer(value: object) -> int:
    require(type(value) is int and value >= 0, "Invalid nonnegative count")
    return value


def _boolean(value: object) -> bool:
    require(type(value) is bool, "Invalid execution flag")
    return value


def _read(path: Path, sha: str, inputs: dict[Path, str]) -> dict:
    _hash(sha)
    for part in (path, *path.parents):
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode)
                and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "Reparse input is not supported")
    require(path.is_file() and path.stat().st_size <= 32 * 1024 * 1024, "Missing or oversized report")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == sha, "Pinned report SHA differs")
    value = json.loads(raw)
    require(isinstance(value, dict), "Invalid report object")
    inputs[path] = sha
    return value


def _row(doc_id: str, sha: str, family: str, state: str, requests: int, strict_replies: int,
         valid: bool, non_null: int | None, all_null: bool | None, strict: bool) -> dict:
    require(isinstance(doc_id, str) and bool(doc_id), "Missing original identity")
    _hash(sha)
    require(state in {"sealed", "uncertain", "unstarted"}, "Nonterminal source state")
    _integer(requests)
    _integer(strict_replies)
    _boolean(valid)
    _boolean(strict)
    require(strict_replies <= requests <= 4, "Per-source call counts differ")
    require(state != "unstarted" or requests == 0, "Unstarted original has a model request")
    if non_null is not None:
        _integer(non_null)
        require(type(all_null) is bool and all_null == (non_null == 0), "Null-output metrics differ")
    require(not valid or (state == "sealed" and strict and requests > 0 and strict_replies == requests
                         and non_null is not None), "Full coverage lacks complete strict inference")
    return {"doc_id": doc_id, "source_sha256": sha, "family": family, "state": state,
            "request_count": requests, "valid_strict_replies": strict_replies,
            "selected": True, "request_begun": requests > 0, "valid_full_coverage": valid,
            "non_null_full_coverage": bool(valid and non_null > 0)}


def _cohort(rows: list[dict], name: str) -> dict:
    require(dict(Counter(row["family"] for row in rows)) == EXPECTED_FAMILIES[name], "Study denominator differs")
    require(len({row["doc_id"] for row in rows}) == len(rows)
            and len({row["source_sha256"] for row in rows}) == len(rows), "Duplicate original within study")
    return {stage: sum(row[stage] for row in rows) for stage in STAGES} | {
        "source_states": dict(Counter(row["state"] for row in rows)),
        "request_begun_attempts": sum(row["request_count"] for row in rows),
        "valid_strict_reply_attempts": sum(row["valid_strict_replies"] for row in rows),
        "sealed_pre_model_rejections": sum(row["state"] == "sealed" and not row["request_begun"] for row in rows),
        "uncertain_before_model": sum(row["state"] == "uncertain" and not row["request_begun"] for row in rows),
        "valid_all_null_originals": sum(row["valid_full_coverage"] and not row["non_null_full_coverage"] for row in rows),
    }


def _operational(report: dict) -> tuple[list[dict], dict]:
    require(report.get("version") == 1 and report.get("kind") == "final_operational_verification"
            and report.get("status") == "verified" and report.get("accuracy_measured") is False
            and report.get("human_release_measured") is False, "Completed operational verification required")
    rows = []
    for item in report["documents"]:
        require(item["state"] in {"sealed", "uncertain"}, "Operational original is not terminal")
        metrics = item["metrics"] or {}
        rows.append(_row(item["doc_id"], item["source_sha256"], item["family"], item["state"],
                         item["request_count"], item["valid_strict_reply_attempts"], item["valid_full_coverage"],
                         metrics.get("non_null_fields"), metrics.get("all_null"), metrics.get("strict_parsed", False)))
    counts = _cohort(rows, "operational")
    mapping = {"selected": "selected_originals", "request_begun": "originals_with_request_begun",
               "valid_full_coverage": "valid_full_coverage_originals", "non_null_full_coverage": "valid_non_null_originals"}
    for subset, expected in [(rows, report["counts"]), *[
        ([row for row in rows if row["family"] == family], report["families"][family])
        for family in EXPECTED_FAMILIES["operational"]]]:
        for stage, key in mapping.items():
            require(sum(row[stage] for row in subset) == expected[key], "Operational summary differs")
        require(dict(Counter(row["state"] for row in subset)) == expected["source_states"]
                and sum(row["request_count"] for row in subset) == expected["request_begun_attempts"]
                and sum(row["valid_strict_replies"] for row in subset) == expected["valid_strict_reply_attempts"],
                "Operational attempt summary differs")
    counts["attempt_accounting"] = {key: report["counts"][key] for key in (
        "known_sdk_attempts", "attempts_with_unknown_sdk_count", "uncertain_attempts", "attempts_with_unknown_usage")}
    for key, value in counts["attempt_accounting"].items():
        _integer(value)
        require(key == "known_sdk_attempts" or value <= counts["request_begun_attempts"], "Invalid operational unknown count")
    return rows, counts


def _quality(result: dict, protocol: dict, receipt: dict) -> tuple[list[dict], dict]:
    require(result.get("all_sources_retained") is True and result.get("human_release_measured") is False
            and result.get("whole_document_visual_truth_established") is False,
            "Complete quality accounting required")
    sources = protocol["sources"]
    by_id = {row["doc_id"]: row for row in sources}
    pairs = result["paired_sources"]
    require(len(by_id) == len(sources) == len(pairs) == receipt["verified_originals"]
            and {row["doc_id"] for row in pairs} == set(by_id), "Quality original inventory differs")
    rows = []
    for pair in pairs:
        source = by_id[pair["doc_id"]]
        require(pair["family"] == source["family"] and pair["candidate"]["doc_id"] == pair["doc_id"],
                "Quality candidate identity differs")
        item = pair["candidate"]["operational"]
        require(item["eligible_prediction"] == item["valid_full_coverage"]
                and all(kind in {"text", "visual"} for kind in item["request_kinds"]), "Quality coverage metrics differ")
        require(not item["valid_full_coverage"] or item["source_coverage"] is True, "Missing source coverage")
        rows.append(_row(pair["doc_id"], source["source_sha256"], pair["family"], item["state"],
                         len(item["request_kinds"]), item["valid_strict_replies"], item["valid_full_coverage"],
                         item["non_null_fields"], item["all_null"], item["strict_parsed"]))
    counts = _cohort(rows, "quality_candidate")
    require(_integer(receipt["verified_request_attempts"]) >= counts["request_begun_attempts"],
            "Quality candidate exceeds verified paired attempts")
    require(receipt["source_family_counts"] == EXPECTED_FAMILIES["quality_candidate"], "Quality family receipt differs")
    accounting = Counter()
    for family, expected_count in EXPECTED_FAMILIES["quality_candidate"].items():
        subset = [row for row in rows if row["family"] == family]
        family_result = result["families"]["candidate"][family]
        usage = family_result["operational_usage"]
        require(family_result["documents"] == expected_count
                and usage["source_states"] == dict(Counter(row["state"] for row in subset))
                and usage["originals_with_attempts"] == sum(row["request_begun"] for row in subset)
                and usage["request_begun_attempts"] == sum(row["request_count"] for row in subset)
                and usage["valid_strict_replies"] == sum(row["valid_strict_replies"] for row in subset),
                "Quality candidate summary differs")
        for key in ("known_sdk_attempts", "attempts_with_unknown_sdk_attempts", "uncertain_attempts",
                    "attempts_with_unknown_prompt_tokens", "attempts_with_unknown_completion_tokens"):
            value = _integer(usage[key])
            require(key == "known_sdk_attempts" or value <= usage["request_begun_attempts"], "Invalid quality unknown count")
            accounting[key] += value
    counts["attempt_accounting"] = dict(accounting)
    return rows, counts


def assemble(operational_dir: Path, operational_receipt_sha: str, operational_report_sha: str,
             quality_dir: Path, quality_receipt_sha: str, quality_result_sha: str,
             operational_run: Path, quality_run: Path) -> dict:
    inputs: dict[Path, str] = {}
    op_receipt = _read(operational_dir / "receipt.json", operational_receipt_sha, inputs)
    q_receipt = _read(quality_dir / "scoring-receipt.json", quality_receipt_sha, inputs)
    require(op_receipt.get("version") == 1 and op_receipt["verification_sha256"] == operational_report_sha,
            "Operational receipt binding differs")
    require(q_receipt.get("no_inference_or_ocr") is True and q_receipt.get("no_reference_repairs") is True
            and q_receipt.get("labels_opened_before_verification") is False
            and q_receipt["files"]["quality-results.json"] == quality_result_sha,
            "Completed quality scoring receipt required")
    op = _read(operational_dir / "verification.json", operational_report_sha, inputs)
    op_rows, op_counts = _operational(op)
    op_protocol = _read(operational_run / "protocol.json", op["protocol_sha256"], inputs)
    require(op_protocol["mode"] == "model2000_original_operational"
            and all(op_protocol["profile"][key] == value for key, value in op["profile"].items()),
            "Operational protocol/profile binding differs")
    q_verified = _read(quality_dir / "verified-before-labels.json", q_receipt["files"]["verified-before-labels.json"], inputs)
    require({"prediction_seal_sha256", "protocol_sha256", "verified_originals", "source_family_counts",
             "verified_request_attempts", "labels_opened_before_verification"} <= set(q_verified)
            and all(q_receipt.get(key) == value for key, value in q_verified.items()),
            "Quality verification receipt differs")
    # Only seal/protocol metadata is read from the campaign. No prediction, label or source bytes.
    seal = _read(quality_run / "prediction-seal.json", q_receipt["prediction_seal_sha256"], inputs)
    require(seal.get("all_slots_accounted") is True and seal.get("labels_opened") is False
            and "seal-started.json" in seal["files"] and seal["files"]["protocol.json"] == q_receipt["protocol_sha256"],
            "Quality campaign lacks a complete pinned seal")
    protocol = _read(quality_run / "protocol.json", q_receipt["protocol_sha256"], inputs)
    require(protocol["mode"] == "paired_quality240" and protocol["labels_opened"] is False
            and set(protocol["profiles"]) == {"text", "candidate"}
            and protocol["profiles"]["text"]["visual_document_profile"] == "disabled", "Wrong quality study")
    for profile in (op["profile"], protocol["profiles"]["candidate"]):
        require(all(profile[key] == value for key, value in INFERENCE_PROFILE.items()), "Inference profile differs")
    require(set(protocol["schemas"]) == set(EXPECTED_FAMILIES["quality_candidate"]), "Quality schemas are incomplete")
    for family, schema in protocol["schemas"].items():
        require(op["verified_artifact_hashes"][f"schemas/{family}.json"] == schema["sha256"], "Study schemas differ")
    q = _read(quality_dir / "quality-results.json", quality_result_sha, inputs)
    q_rows, q_counts = _quality(q, protocol, q_receipt)
    require([(row["doc_id"], row["source_sha256"], row["family"]) for row in op_protocol["sources"]]
            == [(row["doc_id"], row["source_sha256"], row["family"]) for row in op_rows],
            "Operational original inventory differs")
    sets = {name: {stage: {row["source_sha256"] for row in rows if row[stage]} for stage in STAGES}
            for name, rows in (("operational", op_rows), ("quality_candidate", q_rows))}
    families = {}
    for row in op_rows + q_rows:
        require(families.get(row["source_sha256"], row["family"]) == row["family"], "Shared bytes have different families")
        families[row["source_sha256"]] = row["family"]
    union = {stage: len(sets["operational"][stage] | sets["quality_candidate"][stage]) for stage in STAGES}
    overlap = {stage: len(sets["operational"][stage] & sets["quality_candidate"][stage]) for stage in STAGES}
    for path, sha in inputs.items():
        _read(path, sha, {})
    return {"version": 1, "kind": "verified_source_union", "status": "accounted",
            "inputs": {"operational_receipt_sha256": operational_receipt_sha, "operational_report_sha256": operational_report_sha,
                       "quality_receipt_sha256": quality_receipt_sha, "quality_result_sha256": quality_result_sha,
                       "operational_protocol_sha256": _hash(op["protocol_sha256"]),
                       "operational_seal_sha256": _hash(op["final_seal_sha256"]),
                       "quality_protocol_sha256": q_receipt["protocol_sha256"],
                       "quality_seal_sha256": q_receipt["prediction_seal_sha256"]},
            "inference_profile": INFERENCE_PROFILE,
            "registered_profiles_sha256": {name: hashlib.sha256(json.dumps(profile, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode()).hexdigest() for name, profile in (
                    ("operational", op_protocol["profile"]), ("quality_candidate", protocol["profiles"]["candidate"]))},
            "execution_profiles": {name: {key: profile[key] for key in ("workers", "max_calls", "max_calls_per_source", "batch_size")}
                                   for name, profile in (("operational", op_protocol["profile"]),
                                                         ("quality_candidate", protocol["profiles"]["candidate"]))},
            "studies": {"operational": op_counts, "quality_candidate": q_counts},
            "distinct_union": union, "shared_originals": overlap, "source_disjoint": overlap["selected"] == 0,
            "families": {family: {stage: len({sha for sha in sets["operational"][stage] | sets["quality_candidate"][stage]
                                               if families[sha] == family}) for stage in STAGES}
                         for family in sorted(set(families.values()))},
            "originals": {"operational": op_rows, "quality_candidate": q_rows},
            "at_least_2000": {stage: union[stage] >= 2000 for stage in STAGES},
            "baseline_arm_counted": False, "predictions_opened": False, "labels_opened": False,
            "accuracy_measured": False, "human_release_measured": False, "usd_cost": None,
            "limitations": ["Consumes externally pinned independent verification/scoring attestations; does not rerun them.",
                            "Request begun does not prove delivery, billing, completion or correctness; unknown attempts remain unknown.",
                            "Full coverage uses the current verifier's strict parsed reply and source-coverage criteria, not semantic correctness.",
                            "Non-null full coverage means at least one non-null field, not a correct or complete semantic extraction.",
                            "Each study retains its own denominator. Shared source bytes count once; two partial results cannot form a success.",
                            "The text baseline contributes no sources or results. Human review and release were not measured."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("operational-dir", "quality-dir", "operational-run", "quality-run", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("operational-receipt-sha256", "operational-report-sha256", "quality-receipt-sha256", "quality-result-sha256"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        require(not output.exists() and all(not output.is_relative_to(directory.resolve())
                for directory in (args.operational_dir, args.quality_dir, args.operational_run, args.quality_run)),
                "New external output directory required")
        report = assemble(args.operational_dir, args.operational_receipt_sha256, args.operational_report_sha256,
                          args.quality_dir, args.quality_receipt_sha256, args.quality_result_sha256,
                          args.operational_run, args.quality_run)
        output.mkdir(parents=True, exist_ok=False)
        raw = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        (output / "union.json").write_bytes(raw)
        lines = ["# Distinct-original accounting", "", "| Stage | Operational | Quality candidate | Shared | Distinct union |", "|---|---:|---:|---:|---:|"]
        for stage in STAGES:
            lines.append(f"| {stage} | {report['studies']['operational'][stage]} | {report['studies']['quality_candidate'][stage]} | "
                         f"{report['shared_originals'][stage]} | {report['distinct_union'][stage]} |")
        lines.extend(["", "Separate study denominators are preserved. Baseline results are excluded.", ""])
        lines.extend(f"- {limit}" for limit in report["limitations"])
        markdown = ("\n".join(lines) + "\n").encode()
        (output / "report.md").write_bytes(markdown)
        receipt = {"version": 1, "union_sha256": hashlib.sha256(raw).hexdigest(),
                   "report_sha256": hashlib.sha256(markdown).hexdigest(),
                   "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "accounted", **receipt}, sort_keys=True))
        return 0
    except (KeyError, TypeError, ValueError, OSError):
        print(json.dumps({"status": "refused", "reason": "invalid_or_incomplete_pinned_evidence"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

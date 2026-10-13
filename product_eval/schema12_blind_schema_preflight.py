"""Read-only admission check for a future local blind-schema comparison.

The scorer's source-lock, gold and alias JSON are validated by the scorer
itself. Separate rights, human-anchor and runtime receipts must bind their
exact hashes to the same versioned cohort. This module makes no model call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from product_eval.schema_only_scorer import (
    SchemaContractError,
    read_json,
    validate_aliases,
    validate_gold,
    validate_source_lock,
)

HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class PreflightError(ValueError):
    """The versioned admission evidence is missing or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_locked_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    if not HASH_PATTERN.fullmatch(expected_sha256):
        raise PreflightError("expected SHA-256 must be 64 lowercase hex characters")
    if not path.is_file():
        raise PreflightError(f"lock file is missing: {path.name}")
    try:
        value, actual_sha256 = read_json(path)
    except (OSError, SchemaContractError) as exc:
        raise PreflightError(f"invalid lock JSON: {path.name}: {exc}") from exc
    if actual_sha256 != expected_sha256:
        raise PreflightError(f"lock SHA-256 differs: {path.name}")
    if not isinstance(value, dict):
        raise PreflightError(f"lock must be a JSON object: {path.name}")
    return value


def _cohort_sources(source_root: Path, manifest: dict[str, Any], eligibility: dict[str, Any],
                    manifest_sha256: str, cap: int, expected_count: int) -> dict[str, Any]:
    if manifest.get("candidate_denominator") != expected_count or manifest.get("model_inference") is not False:
        raise PreflightError("cohort denominator or staged-only status differs")
    if eligibility.get("source_manifest_sha256") != manifest_sha256:
        raise PreflightError("eligibility belongs to a different source manifest")
    manifest_rows = manifest.get("sources")
    eligibility_rows = eligibility.get("sources")
    if not isinstance(manifest_rows, list) or len(manifest_rows) != expected_count:
        raise PreflightError("manifest does not contain the declared source count")
    if not isinstance(eligibility_rows, list) or len(eligibility_rows) != expected_count:
        raise PreflightError("eligibility does not contain the declared source count")
    raw_root = (source_root / "raw").resolve(strict=True)
    ids: set[str] = set()
    source_hashes: set[str] = set()
    formats: Counter[str] = Counter()
    for row in manifest_rows:
        if not isinstance(row, dict):
            raise PreflightError("source entry is not an object")
        source_id, relative, claimed_hash = row.get("id"), row.get("relative_path"), row.get("sha256")
        if not isinstance(source_id, str) or not source_id.strip() or source_id in ids:
            raise PreflightError("source IDs must be unique and nonempty")
        if not isinstance(relative, str) or not isinstance(claimed_hash, str) or not HASH_PATTERN.fullmatch(claimed_hash):
            raise PreflightError(f"source path or hash is invalid: {source_id}")
        relative_posix = PurePosixPath(relative)
        if (relative_posix.is_absolute() or len(relative_posix.parts) != 2 or relative_posix.parts[0] != "raw"
                or any(part in {"", ".", ".."} for part in relative_posix.parts)):
            raise PreflightError(f"source path escapes raw directory: {source_id}")
        source_path = (source_root / Path(*relative_posix.parts)).resolve(strict=True)
        if not source_path.is_relative_to(raw_root) or not source_path.is_file():
            raise PreflightError(f"source path is not a regular raw file: {source_id}")
        if source_path.stat().st_size != row.get("byte_size") or sha256_file(source_path) != claimed_hash:
            raise PreflightError(f"source bytes differ: {source_id}")
        if claimed_hash in source_hashes:
            raise PreflightError("cohort contains duplicate original bytes")
        ids.add(source_id)
        source_hashes.add(claimed_hash)
        formats[str(row.get("kind"))] += 1
    if set(formats) - {"pdf", "html", "xlsx"}:
        raise PreflightError("unsupported source format in cohort")
    eligibility_by_id: dict[str, dict[str, Any]] = {}
    for row in eligibility_rows:
        if not isinstance(row, dict) or not isinstance(row.get("source_id"), str):
            raise PreflightError("eligibility source ID is invalid")
        source_id = row["source_id"]
        if source_id in eligibility_by_id:
            raise PreflightError("duplicate eligibility source ID")
        eligibility_by_id[source_id] = row
    if set(eligibility_by_id) != ids:
        raise PreflightError("eligibility and manifest source IDs differ")
    eligible = 0
    over_limit: list[str] = []
    for source in manifest_rows:
        row = eligibility_by_id[source["id"]]
        chars = row.get("character_count")
        if (row.get("source_sha256") != source["sha256"] or row.get("format") != source["kind"]
                or row.get("status") != "parsed" or type(chars) is not int or chars < 0
                or row.get("model_context_cap_chars") != cap
                or row.get("meets_model_context_limit") is not (chars <= cap)):
            raise PreflightError(f"eligibility mismatch: {source['id']}")
        if chars <= cap:
            eligible += 1
        else:
            over_limit.append(source["id"])
    return {"source_count": len(ids), "unique_source_hashes": len(source_hashes),
            "formats": dict(formats), "eligible_under_character_cap": eligible,
            "over_limit_source_ids": over_limit, "source_ids": sorted(ids)}


def _try_lock(path: Path | None, digest: str | None, label: str) -> tuple[dict[str, Any] | None, str | None]:
    if path is None or digest is None:
        return None, f"{label} is not supplied with an expected SHA-256"
    try:
        return _read_locked_json(path, digest), None
    except (OSError, ValueError) as exc:
        return None, f"{label} failed: {exc}"


def _validate_rights(value: dict[str, Any], *, manifest_sha256: str, source_lock_sha256: str,
                     planned: dict[str, str]) -> None:
    if (value.get("version") != 1 or value.get("source_manifest_sha256") != manifest_sha256
            or value.get("source_lock_sha256") != source_lock_sha256
            or value.get("status") != "cleared_for_local_ai_inference" or not value.get("reviewed_by")):
        raise PreflightError("rights receipt is not cleared and bound to this cohort")
    rows = value.get("sources")
    if not isinstance(rows, list) or len(rows) != len(planned):
        raise PreflightError("rights receipt must cover every original source")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PreflightError("rights source entry is invalid")
        doc_id = row.get("doc_id")
        if (doc_id not in planned or doc_id in seen or row.get("source_sha256") != planned[doc_id]
                or row.get("local_ai_inference_permitted") is not True or not row.get("basis")):
            raise PreflightError("rights clearance is incomplete or misbound")
        seen.add(doc_id)
    if seen != set(planned):
        raise PreflightError("rights receipt omitted a source")


def _validate_human(value: dict[str, Any], *, manifest_sha256: str, eligibility_sha256: str,
                    source_lock_sha256: str, gold_sha256: str, aliases_sha256: str,
                    planned: dict[str, str], gold_docs: dict[str, dict[str, Any]]) -> None:
    if (value.get("version") != 1 or value.get("source_manifest_sha256") != manifest_sha256
            or value.get("source_lock_sha256") != source_lock_sha256
            or value.get("eligibility_sha256") != eligibility_sha256
            or value.get("gold_sha256") != gold_sha256
            or value.get("aliases_sha256") != aliases_sha256
            or value.get("status") != "adjudicated_source_only"):
        raise PreflightError("human receipt is not adjudicated and bound to exact scorer inputs")
    annotators = value.get("annotators")
    if (not isinstance(annotators, list) or len(annotators) < 2
            or any(not isinstance(person, str) or not person.strip() for person in annotators)
            or len(set(annotators)) < 2 or not value.get("adjudicator")):
        raise PreflightError("human receipt lacks independent annotation and adjudication")
    rows = value.get("sources")
    if not isinstance(rows, list) or len(rows) != len(planned):
        raise PreflightError("human receipt must cover all planned sources")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PreflightError("human source entry is invalid")
        doc_id = row.get("doc_id")
        if (doc_id not in planned or doc_id in seen or row.get("source_sha256") != planned[doc_id]
                or row.get("full_source_pass") is not True):
            raise PreflightError("human source pass is incomplete or misbound")
        fields = row.get("fields")
        if not isinstance(fields, list) or len(fields) != len(gold_docs[doc_id]["fields"]):
            raise PreflightError("human field anchors do not cover scorer gold")
        field_ids: set[str] = set()
        for field in fields:
            if not isinstance(field, dict):
                raise PreflightError("human field anchor entry is invalid")
            field_id = field.get("field_id")
            anchors = field.get("anchors")
            if (field_id not in gold_docs[doc_id]["fields"] or field_id in field_ids
                    or not isinstance(anchors, list) or not anchors
                    or any(not isinstance(anchor, dict) or not anchor.get("locator") or
                           not anchor.get("quote") for anchor in anchors)):
                raise PreflightError("human field lacks a source locator and quote")
            field_ids.add(field_id)
        if field_ids != set(gold_docs[doc_id]["fields"]):
            raise PreflightError("human anchor fields differ from scorer gold")
        seen.add(doc_id)
    if seen != set(planned):
        raise PreflightError("human receipt omitted a source")


def _validate_runtime(value: dict[str, Any], *, manifest_sha256: str, source_lock_sha256: str,
                      profile_sha256: str, model_profiles: dict[str, Any]) -> None:
    if (value.get("version") != 1 or value.get("source_manifest_sha256") != manifest_sha256
            or value.get("source_lock_sha256") != source_lock_sha256
            or value.get("protocol_profile_sha256") != profile_sha256
            or value.get("status") != "source_free_verified"):
        raise PreflightError("runtime receipt is not source-free verified for this cohort/profile")
    arms = value.get("model_arms")
    if not isinstance(arms, dict) or set(arms) != set(model_profiles):
        raise PreflightError("runtime receipt lacks both model arms")
    for name, profile in model_profiles.items():
        arm = arms[name]
        if (not isinstance(arm, dict) or arm.get("loaded") is not True
                or arm.get("source_free_smoke") is not True
                or arm.get("weight_sha256") != profile["weight_sha256"]):
            raise PreflightError("runtime model load, smoke or weight differs")


def _model_assets(args: argparse.Namespace, profile: dict[str, Any]) -> tuple[bool, list[str]]:
    if not args.hash_model_assets:
        return False, ["model byte verification was not requested"]
    models = profile["model_profiles"]
    expected = [
        (args.nuextract_weight, models["nuextract3_q4"]["weight_sha256"], "NuExtract Q4 weight"),
        (args.nuextract_mmproj, models["nuextract3_q4"]["vision_projector_sha256"], "NuExtract vision projector"),
        (args.nuextract_server, models["nuextract3_q4"]["llama_server_sha256"], "llama.cpp server"),
        (args.qwen_weight, models["qwen35_2b_bf16"]["weight_sha256"], "Qwen BF16 weight"),
    ]
    issues: list[str] = []
    for path, digest, label in expected:
        if path is None or not path.is_file():
            issues.append(f"{label} is absent")
        elif sha256_file(path) != digest:
            issues.append(f"{label} hash differs")
    return not issues, issues


def inspect(args: argparse.Namespace) -> dict[str, Any]:
    profile = _read_locked_json(args.profile, args.profile_sha256)
    if profile.get("protocol_version") != 1 or profile.get("cohort_size") != 12:
        raise PreflightError("protocol profile is incompatible")
    limits = profile["limits"]
    c_free = shutil.disk_usage("C:\\" if sys.platform == "win32" else "/").free
    if c_free < limits["minimum_c_free_bytes_for_source_check"]:
        raise PreflightError("C: free space is below the 4 GiB source-check guard")
    manifest = _read_locked_json(args.source_root / "manifest-final.json", args.manifest_sha256)
    eligibility = _read_locked_json(args.source_root / "eligibility.json", args.eligibility_sha256)
    cohort = _cohort_sources(args.source_root, manifest, eligibility, args.manifest_sha256,
                             profile["eligible_source_character_cap"], profile["cohort_size"])
    expected_sources = {row["id"]: row["sha256"] for row in manifest["sources"]}
    gates: dict[str, bool] = {"source_bytes": True}
    blockers: list[str] = []

    source_lock, issue = _try_lock(args.source_lock, args.source_lock_sha256, "scorer source lock")
    planned: dict[str, str] | None = None
    if source_lock is not None:
        try:
            planned = validate_source_lock(source_lock)
            if planned != expected_sources:
                raise PreflightError("scorer source lock ID-to-original-hash mapping differs from cohort")
        except (SchemaContractError, PreflightError) as exc:
            issue = str(exc)
            planned = None
    gates["source_lock"] = planned is not None
    if issue:
        blockers.append(issue)

    gold_docs: dict[str, dict[str, Any]] | None = None
    gold, issue = _try_lock(args.gold, args.gold_sha256, "scorer gold")
    if gold is not None and planned is not None:
        try:
            gold_docs = validate_gold(gold, planned, args.source_lock_sha256)
            if any(not doc["gold_complete"] for doc in gold_docs.values()):
                raise PreflightError("scorer gold has an incomplete full-document annotation")
        except (SchemaContractError, PreflightError) as exc:
            issue = str(exc)
            gold_docs = None
    elif gold is not None:
        issue = "scorer gold cannot be admitted before its source lock"
    gates["gold"] = gold_docs is not None
    if issue:
        blockers.append(issue)

    aliases, issue = _try_lock(args.aliases, args.aliases_sha256, "scorer aliases")
    aliases_ok = False
    if aliases is not None and gold_docs is not None:
        try:
            validate_aliases(aliases, gold_docs)
            aliases_ok = True
        except SchemaContractError as exc:
            issue = str(exc)
    elif aliases is not None:
        issue = "scorer aliases cannot be admitted before adjudicated gold"
    gates["aliases"] = aliases_ok
    if issue:
        blockers.append(issue)

    rights, issue = _try_lock(args.rights_receipt, args.rights_sha256, "rights receipt")
    rights_ok = False
    if rights is not None and planned is not None:
        try:
            _validate_rights(rights, manifest_sha256=args.manifest_sha256,
                             source_lock_sha256=args.source_lock_sha256, planned=planned)
            rights_ok = True
        except PreflightError as exc:
            issue = str(exc)
    elif rights is not None:
        issue = "rights receipt cannot be admitted before its source lock"
    gates["rights"] = rights_ok
    if issue:
        blockers.append(issue)

    human, issue = _try_lock(args.human_receipt, args.human_sha256, "human adjudication receipt")
    human_ok = False
    if human is not None and planned is not None and gold_docs is not None and aliases_ok:
        try:
            _validate_human(human, manifest_sha256=args.manifest_sha256,
                            eligibility_sha256=args.eligibility_sha256,
                            source_lock_sha256=args.source_lock_sha256,
                            gold_sha256=args.gold_sha256, aliases_sha256=args.aliases_sha256,
                            planned=planned, gold_docs=gold_docs)
            human_ok = True
        except PreflightError as exc:
            issue = str(exc)
    elif human is not None:
        issue = "human receipt cannot be admitted before scorer source/gold/alias locks"
    gates["human_adjudication"] = human_ok
    if issue:
        blockers.append(issue)

    runtime, issue = _try_lock(args.runtime_receipt, args.runtime_sha256, "runtime receipt")
    runtime_ok = False
    if runtime is not None and planned is not None:
        try:
            _validate_runtime(runtime, manifest_sha256=args.manifest_sha256,
                              source_lock_sha256=args.source_lock_sha256,
                              profile_sha256=args.profile_sha256,
                              model_profiles=profile["model_profiles"])
            runtime_ok = True
        except PreflightError as exc:
            issue = str(exc)
    elif runtime is not None:
        issue = "runtime receipt cannot be admitted before its source lock"
    gates["runtime"] = runtime_ok
    if issue:
        blockers.append(issue)

    gates["model_assets"], asset_issues = _model_assets(args, profile)
    blockers.extend(asset_issues)
    gates["model_run_c_headroom"] = c_free >= limits["minimum_c_free_bytes_for_model_run"]
    if not gates["model_run_c_headroom"]:
        blockers.append("C: free space is below the 7 GiB model-run headroom gate")
    if cohort["eligible_under_character_cap"] < cohort["source_count"]:
        blockers.append("over-limit sources remain in the 12-source denominator and receive no model call")
    return {"ready_for_inference": all(gates.values()), "gates": gates, "blockers": blockers,
            "cohort": cohort, "manifest_sha256": args.manifest_sha256,
            "eligibility_sha256": args.eligibility_sha256, "source_lock_sha256": args.source_lock_sha256,
            "profile_sha256": args.profile_sha256, "c_free_bytes_at_check": c_free,
            "model_calls_made": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--eligibility-sha256", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--profile-sha256", required=True)
    parser.add_argument("--source-lock", type=Path)
    parser.add_argument("--source-lock-sha256")
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--gold-sha256")
    parser.add_argument("--aliases", type=Path)
    parser.add_argument("--aliases-sha256")
    for kind in ("rights", "human", "runtime"):
        parser.add_argument(f"--{kind}-receipt", type=Path)
        parser.add_argument(f"--{kind}-sha256")
    parser.add_argument("--hash-model-assets", action="store_true")
    parser.add_argument("--nuextract-weight", type=Path)
    parser.add_argument("--nuextract-mmproj", type=Path)
    parser.add_argument("--nuextract-server", type=Path)
    parser.add_argument("--qwen-weight", type=Path)
    parser.add_argument("--require-ready", action="store_true",
                        help="Return exit 2 when any pre-inference gate is not met")
    args = parser.parse_args(argv)
    try:
        result = inspect(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"ready_for_inference": False, "blockers": [str(exc)], "model_calls_made": 0}
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 2 if args.require_ready and not result["ready_for_inference"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

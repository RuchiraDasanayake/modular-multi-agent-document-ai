"""Read-only admission check for a future local blind-schema comparison.

This module never opens a model, creates a prompt, or invokes inference. A
versioned cohort is supplied explicitly, so replacing a rights-blocked source
cannot silently inherit an earlier source lock.
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


HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FIELD_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
ALLOWED_FIELD_TYPES = {"verbatim-string", "string", "integer", "number", "date-time", "currency", "email"}
ALLOWED_CARDINALITIES = {"scalar", "list", "repeated"}


class PreflightError(ValueError):
    """The versioned admission evidence is missing or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PreflightError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise PreflightError(f"invalid JSON constant: {value}")


def _read_locked_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    if not HASH_PATTERN.fullmatch(expected_sha256):
        raise PreflightError("expected SHA-256 must be 64 lowercase hex characters")
    if not path.is_file():
        raise PreflightError(f"lock file is missing: {path.name}")
    if sha256_file(path) != expected_sha256:
        raise PreflightError(f"lock SHA-256 differs: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys,
                           parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"invalid lock JSON: {path.name}") from exc
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
        if not isinstance(source_id, str) or not FIELD_ID_PATTERN.fullmatch(source_id) or source_id in ids:
            raise PreflightError("source IDs must be unique, nonempty snake_case")
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
                or row.get("status") != "parsed" or not isinstance(chars, int) or chars < 0
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


def _external_lock(path: Path | None, expected_sha256: str | None, *, kind: str,
                   manifest_sha256: str, source_ids: set[str],
                   profile_sha256: str | None = None,
                   model_profiles: dict[str, Any] | None = None) -> tuple[bool, str, dict[str, Any] | None]:
    if path is None or expected_sha256 is None:
        return False, f"{kind} lock is not supplied", None
    try:
        value = _read_locked_json(path, expected_sha256)
        if value.get("version") != 1 or value.get("source_manifest_sha256") != manifest_sha256:
            raise PreflightError("lock version or source manifest binding differs")
        if kind == "rights":
            if value.get("status") != "cleared_for_local_ai_inference" or not value.get("reviewed_by"):
                raise PreflightError("rights review has not cleared local AI inference")
            rows = value.get("sources")
            if (not isinstance(rows, list) or {row.get("source_id") for row in rows if isinstance(row, dict)} != source_ids
                    or len(rows) != len(source_ids) or any(row.get("local_ai_inference_permitted") is not True or
                        not row.get("basis") for row in rows if isinstance(row, dict))):
                raise PreflightError("rights clearance is incomplete for the cohort")
        elif kind == "gold":
            if value.get("status") != "adjudicated" or len(set(value.get("annotators", []))) < 2 or not value.get("adjudicator"):
                raise PreflightError("gold lacks independent annotation and adjudication")
            rows = value.get("sources")
            if not isinstance(rows, list) or len(rows) != len(source_ids) or {row.get("source_id") for row in rows} != source_ids:
                raise PreflightError("gold source coverage differs")
            for row in rows:
                fields = row.get("fields")
                if not isinstance(fields, list) or not fields:
                    raise PreflightError("gold fields are missing")
                field_ids: set[str] = set()
                for field in fields:
                    if not isinstance(field, dict) or not isinstance(field.get("field_id"), str):
                        raise PreflightError("gold field is invalid")
                    field_id = field["field_id"]
                    if not FIELD_ID_PATTERN.fullmatch(field_id) or field_id in field_ids:
                        raise PreflightError("gold field IDs must be unique snake_case")
                    if field.get("type") not in ALLOWED_FIELD_TYPES or field.get("cardinality") not in ALLOWED_CARDINALITIES:
                        raise PreflightError("gold field type or cardinality is invalid")
                    if field.get("cardinality") == "repeated" and not field.get("group_id"):
                        raise PreflightError("repeated gold field lacks a group")
                    if (field.get("group_id") is not None and
                            (not isinstance(field["group_id"], str) or
                             not FIELD_ID_PATTERN.fullmatch(field["group_id"]))):
                        raise PreflightError("gold field group ID is invalid")
                    if (not isinstance(field.get("evidence"), list) or not field["evidence"] or
                            any(not isinstance(anchor, dict) or not anchor.get("locator") or
                                not anchor.get("quote") for anchor in field["evidence"])):
                        raise PreflightError("gold field lacks source anchors")
                    field_ids.add(field_id)
        elif kind == "aliases":
            if value.get("status") != "frozen" or not isinstance(value.get("sources"), list):
                raise PreflightError("alias ontology is not frozen")
            rows = value["sources"]
            if len(rows) != len(source_ids) or {row.get("source_id") for row in rows} != source_ids:
                raise PreflightError("alias source coverage differs")
            for row in rows:
                aliases = row.get("aliases")
                if not isinstance(aliases, dict):
                    raise PreflightError("aliases must be keyed by gold field ID")
                for field_id, names in aliases.items():
                    if (not FIELD_ID_PATTERN.fullmatch(field_id) or not isinstance(names, list)
                            or any(not isinstance(name, str) or not FIELD_ID_PATTERN.fullmatch(name) for name in names)
                            or len(names) != len(set(names))):
                        raise PreflightError("alias entry is invalid")
        elif kind == "runtime":
            if (value.get("status") != "source_free_verified"
                    or value.get("protocol_profile_sha256") != profile_sha256):
                raise PreflightError("runtime is not source-free verified")
            arms = value.get("model_arms")
            if not isinstance(arms, dict) or set(arms) != {"nuextract3_q4", "qwen35_2b_bf16"}:
                raise PreflightError("runtime receipt lacks both model arms")
            if any(not isinstance(arm, dict) or arm.get("loaded") is not True or
                   arm.get("source_free_smoke") is not True for arm in arms.values()):
                raise PreflightError("model load or source-free smoke was not verified")
            if not model_profiles or any(arms[name].get("weight_sha256") != profile["weight_sha256"]
                                         for name, profile in model_profiles.items()):
                raise PreflightError("runtime model weights differ from the protocol")
        else:
            raise PreflightError("unknown lock kind")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        return False, f"{kind} lock failed: {exc}", None
    return True, f"{kind} lock verified", value


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
    manifest_sha256 = args.manifest_sha256
    manifest = _read_locked_json(args.source_root / "manifest-final.json", manifest_sha256)
    eligibility = _read_locked_json(args.source_root / "eligibility.json", args.eligibility_sha256)
    cohort = _cohort_sources(args.source_root, manifest, eligibility, manifest_sha256,
                             profile["eligible_source_character_cap"], profile["cohort_size"])
    ids = set(cohort["source_ids"])
    gates: dict[str, bool] = {"source_lock": True}
    blockers: list[str] = []
    lock_values: dict[str, dict[str, Any]] = {}
    for kind in ("rights", "gold", "aliases", "runtime"):
        ok, message, lock_value = _external_lock(
            getattr(args, f"{kind}_lock"), getattr(args, f"{kind}_sha256"),
            kind=kind, manifest_sha256=manifest_sha256, source_ids=ids,
            profile_sha256=args.profile_sha256, model_profiles=profile["model_profiles"],
        )
        gates[kind] = ok
        if not ok:
            blockers.append(message)
        else:
            assert lock_value is not None
            lock_values[kind] = lock_value
    if gates["gold"] and gates["aliases"]:
        gold_fields = {row["source_id"]: {field["field_id"] for field in row["fields"]}
                       for row in lock_values["gold"]["sources"]}
        if any(set(row["aliases"]) - gold_fields[row["source_id"]]
               for row in lock_values["aliases"]["sources"]):
            gates["aliases"] = False
            blockers.append("alias ontology names a field absent from adjudicated gold")
    gates["model_assets"], asset_issues = _model_assets(args, profile)
    blockers.extend(asset_issues)
    gates["model_run_c_headroom"] = c_free >= limits["minimum_c_free_bytes_for_model_run"]
    if not gates["model_run_c_headroom"]:
        blockers.append("C: free space is below the 7 GiB model-run headroom gate")
    if cohort["eligible_under_character_cap"] < cohort["source_count"]:
        blockers.append("over-limit sources remain in the 12-source denominator and receive no model call")
    return {"ready_for_inference": all(gates.values()), "gates": gates, "blockers": blockers,
            "cohort": cohort, "manifest_sha256": manifest_sha256,
            "eligibility_sha256": args.eligibility_sha256, "profile_sha256": args.profile_sha256,
            "c_free_bytes_at_check": c_free, "model_calls_made": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--eligibility-sha256", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--profile-sha256", required=True)
    for kind in ("rights", "gold", "aliases", "runtime"):
        parser.add_argument(f"--{kind}-lock", type=Path)
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
    except (OSError, ValueError, KeyError) as exc:
        result = {"ready_for_inference": False, "blockers": [str(exc)], "model_calls_made": 0}
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 2 if args.require_ready and not result["ready_for_inference"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline, model-free schema-only scorer for a locked 12-source diagnostic.

This module does not score values, source evidence, human review, or cost. Raw
model replies must be projected into the versioned candidate envelope first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

CONTRACT_VERSION = 1
PLANNED_SOURCES = 12
STATUSES = {"ok", "failed", "unsupported", "over_limit", "malformed", "skipped"}
GROUP_KINDS = {"object", "array[object]", "array[scalar]"}
FIELD_TYPES = {"string", "number", "integer", "boolean", "date", "datetime", "currency", "identifier"}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
FIELD_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
MAX_JSON_BYTES = 10_000_000


class SchemaContractError(ValueError):
    """An input cannot be scored unambiguously under schema contract v1."""


def _unique_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SchemaContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise SchemaContractError(f"non-finite JSON number: {value}")


def read_json(path: Path) -> tuple[Any, str]:
    """Read one bounded UTF-8 JSON file and return its exact byte digest."""
    if path.stat().st_size > MAX_JSON_BYTES:
        raise SchemaContractError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path.name}")
    data = path.read_bytes()
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_json_pairs,
                           parse_constant=_reject_nonfinite)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaContractError(f"invalid JSON: {path.name}") from exc
    return value, hashlib.sha256(data).hexdigest()


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaContractError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SchemaContractError(f"{label} must be a list")
    return value


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaContractError(f"{label} must be a nonempty string")
    return value


def _version(value: dict[str, Any], label: str) -> None:
    if type(value.get("contract_version")) is not int or value["contract_version"] != CONTRACT_VERSION:
        raise SchemaContractError(f"{label}.contract_version must be {CONTRACT_VERSION}")


def normalize_name(value: str) -> str:
    """NFKC, ASCII camel boundary, casefold, then Unicode alphanumeric tokens."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", normalized).casefold()
    return "_".join(part for part in re.split(r"[^\w]+|_+", normalized, flags=re.UNICODE) if part)


def validate_source_lock(lock: Any) -> dict[str, str]:
    lock = _object(lock, "source_lock")
    _version(lock, "source_lock")
    rows = _list(lock.get("sources"), "source_lock.sources")
    if len(rows) != PLANNED_SOURCES:
        raise SchemaContractError(f"source_lock requires exactly {PLANNED_SOURCES} sources")
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    sources: dict[str, str] = {}
    for index, raw in enumerate(rows):
        row = _object(raw, f"source_lock.sources[{index}]")
        doc_id = _name(row.get("doc_id"), f"source_lock.sources[{index}].doc_id")
        digest = row.get("source_sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise SchemaContractError(f"source_lock.sources[{index}].source_sha256 must be lowercase SHA-256")
        if doc_id in seen_ids or digest in seen_hashes:
            raise SchemaContractError("source_lock has duplicate document ID or source SHA-256")
        sources[doc_id] = digest
        seen_ids.add(doc_id)
        seen_hashes.add(digest)
    return sources


def _schema_fields(raw: dict[str, Any], label: str, *, gold: bool) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    groups: dict[str, str] = {}
    for index, entry in enumerate(_list(raw.get("groups"), f"{label}.groups")):
        group = _object(entry, f"{label}.groups[{index}]")
        group_id = _name(group.get("group_id"), f"{label}.groups[{index}].group_id")
        kind = group.get("kind")
        if not isinstance(kind, str) or kind not in GROUP_KINDS or group_id in groups:
            raise SchemaContractError(f"{label} has invalid or duplicate group")
        groups[group_id] = kind
    fields: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(_list(raw.get("fields"), f"{label}.fields")):
        field = _object(entry, f"{label}.fields[{index}]")
        field_id = field.get("field_id")
        if not isinstance(field_id, str) or not field_id.strip() or (gold and not FIELD_ID_RE.fullmatch(field_id)):
            raise SchemaContractError(f"{label}.fields[{index}].field_id is invalid")
        if field_id in fields:
            raise SchemaContractError(f"{label} has duplicate field_id: {field_id}")
        if not isinstance(field.get("type"), str) or field["type"] not in FIELD_TYPES:
            raise SchemaContractError(f"{label}.fields[{index}] has unsupported type")
        group_id = field.get("group")
        if group_id is not None and (not isinstance(group_id, str) or group_id not in groups):
            raise SchemaContractError(f"{label}.fields[{index}] references an undeclared group")
        fields[field_id] = {"type": field["type"], "group": group_id}
    if any(not any(field["group"] == group_id for field in fields.values()) for group_id in groups):
        raise SchemaContractError(f"{label} has an empty group")
    return fields, groups


def validate_gold(gold: Any, planned_sources: dict[str, str], source_lock_sha256: str) -> dict[str, dict[str, Any]]:
    gold = _object(gold, "gold")
    _version(gold, "gold")
    if gold.get("source_lock_sha256") != source_lock_sha256:
        raise SchemaContractError("gold source_lock_sha256 differs")
    docs: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_list(gold.get("documents"), "gold.documents")):
        row = _object(raw, f"gold.documents[{index}]")
        doc_id = _name(row.get("doc_id"), f"gold.documents[{index}].doc_id")
        if doc_id in docs:
            raise SchemaContractError(f"gold has duplicate doc_id: {doc_id}")
        if doc_id not in planned_sources or row.get("source_sha256") != planned_sources[doc_id]:
            raise SchemaContractError(f"gold[{doc_id}] source hash differs from source lock")
        if type(row.get("gold_complete")) is not bool:
            raise SchemaContractError(f"gold[{doc_id}].gold_complete must be boolean")
        fields, groups = _schema_fields(row, f"gold[{doc_id}]", gold=True)
        docs[doc_id] = {"gold_complete": row["gold_complete"], "fields": fields, "groups": groups}
    if set(docs) != set(planned_sources) or len(docs) != PLANNED_SOURCES:
        raise SchemaContractError("gold must contain exactly the planned 12 document IDs")
    return docs


def validate_aliases(aliases: Any, gold_docs: dict[str, dict[str, Any]]) -> dict[str, str]:
    aliases = _object(aliases, "aliases")
    _version(aliases, "aliases")
    known_ids = {field_id for doc in gold_docs.values() for field_id in doc["fields"]}
    terms: dict[str, str] = {}
    for field_id in sorted(known_ids):
        term = normalize_name(field_id)
        previous = terms.get(term)
        if previous is not None and previous != field_id:
            raise SchemaContractError(f"normalized gold ID collision: {term}")
        terms[term] = field_id
    seen: set[str] = set()
    for index, raw in enumerate(_list(aliases.get("entries"), "aliases.entries")):
        entry = _object(raw, f"aliases.entries[{index}]")
        field_id = entry.get("field_id")
        if not isinstance(field_id, str) or field_id not in known_ids or field_id in seen:
            raise SchemaContractError(f"aliases has unknown or duplicate field_id: {field_id}")
        seen.add(field_id)
        for alias in _list(entry.get("aliases"), f"aliases.entries[{index}].aliases"):
            term = normalize_name(_name(alias, "alias"))
            if not term:
                raise SchemaContractError("alias normalizes to empty")
            previous = terms.get(term)
            if previous is not None and previous != field_id:
                raise SchemaContractError(f"alias collision: {term}")
            terms[term] = field_id
    return terms


def _candidate_docs(candidate: Any, planned_sources: dict[str, str], source_lock_sha256: str) -> dict[str, dict[str, Any]]:
    candidate = _object(candidate, "candidate")
    _version(candidate, "candidate")
    if candidate.get("source_lock_sha256") != source_lock_sha256:
        raise SchemaContractError("candidate source_lock_sha256 differs")
    known = set(planned_sources)
    rows: dict[str, list[Any]] = defaultdict(list)
    for index, raw in enumerate(_list(candidate.get("documents"), "candidate.documents")):
        row = _object(raw, f"candidate.documents[{index}]")
        doc_id = _name(row.get("doc_id"), f"candidate.documents[{index}].doc_id")
        if doc_id not in known:
            raise SchemaContractError(f"candidate has unknown doc_id: {doc_id}")
        if row.get("source_sha256") != planned_sources[doc_id]:
            raise SchemaContractError(f"candidate[{doc_id}] source hash differs from source lock")
        rows[doc_id].append(row)
    result: dict[str, dict[str, Any]] = {}
    for doc_id in planned_sources:
        records = rows.get(doc_id, [])
        if not records:
            result[doc_id] = {"status": "missing", "fields": {}, "groups": {}}
        elif len(records) > 1:
            result[doc_id] = {"status": "invalid_duplicate_doc", "fields": {}, "groups": {}}
        else:
            row = records[0]
            status = row.get("status")
            if not isinstance(status, str) or status not in STATUSES:
                result[doc_id] = {"status": "invalid_status", "fields": {}, "groups": {}}
            elif status != "ok":
                if (not isinstance(row.get("fields", []), list)
                        or not isinstance(row.get("groups", []), list)
                        or row.get("fields", []) or row.get("groups", [])):
                    result[doc_id] = {"status": "invalid_failure_envelope", "fields": {}, "groups": {}}
                else:
                    result[doc_id] = {"status": status, "fields": {}, "groups": {}}
            else:
                try:
                    fields, groups = _schema_fields(row, f"candidate[{doc_id}]", gold=False)
                except SchemaContractError:
                    result[doc_id] = {"status": "invalid_schema", "fields": {}, "groups": {}}
                else:
                    result[doc_id] = {"status": "ok", "fields": fields, "groups": groups}
    return result


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _metrics(tp: int, fp: int, fn: int, *, precision_available: bool) -> dict[str, Any]:
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": _rate(tp, tp + fp) if precision_available else None,
            "recall": _rate(tp, tp + fn),
            "f1": _rate(2 * tp, 2 * tp + fp + fn) if precision_available else None}


def _match_fields(gold_fields: dict[str, Any], predicted_fields: dict[str, Any],
                  alias_terms: dict[str, str], *, allow_aliases: bool) -> tuple[dict[str, str], list[str]]:
    matches = {field_id: field_id for field_id in gold_fields.keys() & predicted_fields.keys()}
    collisions: list[str] = []
    if not allow_aliases:
        return matches, collisions
    candidates: dict[str, list[str]] = defaultdict(list)
    for predicted_id in predicted_fields.keys() - matches.keys():
        target = alias_terms.get(normalize_name(predicted_id))
        if target in gold_fields:
            candidates[target].append(predicted_id)
    for gold_id, predicted_ids in candidates.items():
        if gold_id in matches or len(predicted_ids) != 1:
            collisions.append(gold_id)
        else:
            matches[predicted_ids[0]] = gold_id
    return matches, sorted(collisions)


def _linked_pairs(fields: dict[str, Any], groups: dict[str, str]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for group_id, kind in groups.items():
        if kind != "array[object]":
            continue
        leaves = sorted(field_id for field_id, field in fields.items() if field["group"] == group_id)
        pairs.update(combinations(leaves, 2))
    return pairs


def _score_doc(gold: dict[str, Any], candidate: dict[str, Any],
               alias_terms: dict[str, str], *, allow_aliases: bool) -> dict[str, Any]:
    gold_fields, gold_groups = gold["fields"], gold["groups"]
    predicted_fields, predicted_groups = candidate["fields"], candidate["groups"]
    matches, collisions = _match_fields(gold_fields, predicted_fields, alias_terms, allow_aliases=allow_aliases)
    tp = len(matches)
    field_score = _metrics(tp, len(predicted_fields) - tp, len(gold_fields) - tp,
                           precision_available=gold["gold_complete"])
    field_score["type_correct"] = sum(
        predicted_fields[predicted_id]["type"] == gold_fields[gold_id]["type"]
        for predicted_id, gold_id in matches.items()
    )
    field_score["group_role_correct"] = sum(
        (predicted_fields[predicted_id]["group"] is None and gold_fields[gold_id]["group"] is None)
        or (predicted_fields[predicted_id]["group"] is not None
            and gold_fields[gold_id]["group"] is not None
            and predicted_groups[predicted_fields[predicted_id]["group"]]
            == gold_groups[gold_fields[gold_id]["group"]])
        for predicted_id, gold_id in matches.items()
    )
    gold_pairs = _linked_pairs(gold_fields, gold_groups)
    candidate_pairs = _linked_pairs(predicted_fields, predicted_groups)
    pair_hits = {
        tuple(sorted((matches[a], matches[b])))
        for a, b in candidate_pairs if a in matches and b in matches
    } & gold_pairs
    pair_score = _metrics(len(pair_hits), len(candidate_pairs) - len(pair_hits),
                          len(gold_pairs) - len(pair_hits), precision_available=gold["gold_complete"])
    group_hits = 0
    group_coverage_hits = 0
    for group_id, kind in gold_groups.items():
        if kind != "array[object]":
            continue
        leaves = {field_id for field_id, field in gold_fields.items() if field["group"] == group_id}
        mapped = [(predicted_id, gold_id) for predicted_id, gold_id in matches.items() if gold_id in leaves]
        mapped_groups = {predicted_fields[predicted_id]["group"] for predicted_id, _ in mapped
                         if predicted_fields[predicted_id]["group"] is not None
                         and predicted_groups[predicted_fields[predicted_id]["group"]] == "array[object]"}
        covered = len(mapped) == len(leaves) and len(mapped_groups) == 1 and all(
            predicted_fields[predicted_id]["group"] in mapped_groups for predicted_id, _ in mapped
        )
        if covered:
            group_coverage_hits += 1
            predicted_group = next(iter(mapped_groups))
            predicted_leaves = {field_id for field_id, field in predicted_fields.items()
                                if field["group"] == predicted_group}
            if predicted_leaves == {predicted_id for predicted_id, _ in mapped}:
                group_hits += 1
    return {"fields": field_score, "linked_pairs": pair_score,
            "linked_groups": {"gold": sum(kind == "array[object]" for kind in gold_groups.values()),
                              "hit": group_hits, "coverage_hit": group_coverage_hits},
            "alias_collisions": collisions, "matches": dict(sorted(matches.items())),
            "unmatched_gold": sorted(gold_fields.keys() - set(matches.values())),
            "unmatched_predicted": sorted(predicted_fields.keys() - matches.keys())}


def score_cohort(source_lock: Any, gold: Any, candidate: Any, aliases: Any,
                 *, source_lock_sha256: str) -> dict[str, Any]:
    """Score all locked source IDs, including absent and invalid candidate records."""
    planned_sources = validate_source_lock(source_lock)
    if not isinstance(source_lock_sha256, str) or not SHA256_RE.fullmatch(source_lock_sha256):
        raise SchemaContractError("source_lock_sha256 must be lowercase SHA-256")
    gold_docs = validate_gold(gold, planned_sources, source_lock_sha256)
    alias_terms = validate_aliases(aliases, gold_docs)
    candidate_docs = _candidate_docs(candidate, planned_sources, source_lock_sha256)
    per_document: list[dict[str, Any]] = []
    totals = {mode: {"fields": Counter(), "linked_pairs": Counter(), "linked_groups": Counter()}
              for mode in ("exact", "predeclared_alias")}
    all_complete = all(doc["gold_complete"] for doc in gold_docs.values())
    statuses = Counter()
    for doc_id in planned_sources:
        gold_doc, candidate_doc = gold_docs[doc_id], candidate_docs[doc_id]
        statuses[candidate_doc["status"]] += 1
        scores = {}
        for mode, allow_aliases in (("exact", False), ("predeclared_alias", True)):
            item = _score_doc(gold_doc, candidate_doc, alias_terms, allow_aliases=allow_aliases)
            scores[mode] = item
            for key in ("tp", "fp", "fn", "type_correct", "group_role_correct"):
                if key in item["fields"]:
                    totals[mode]["fields"][key] += item["fields"][key]
            for key in ("tp", "fp", "fn"):
                totals[mode]["linked_pairs"][key] += item["linked_pairs"][key]
            totals[mode]["linked_groups"].update(item["linked_groups"])
        per_document.append({"doc_id": doc_id, "status": candidate_doc["status"],
                             "gold_complete": gold_doc["gold_complete"], "scores": scores})
    summary = {}
    for mode, part in totals.items():
        field_counts, pair_counts = part["fields"], part["linked_pairs"]
        summary[mode] = {
            "fields": _metrics(field_counts["tp"], field_counts["fp"], field_counts["fn"],
                               precision_available=all_complete)
            | {"type_correct": field_counts["type_correct"],
               "group_role_correct": field_counts["group_role_correct"]},
            "linked_pairs": _metrics(pair_counts["tp"], pair_counts["fp"], pair_counts["fn"],
                                     precision_available=all_complete),
            "linked_groups": {"gold": part["linked_groups"]["gold"],
                              "hit": part["linked_groups"]["hit"],
                              "coverage_hit": part["linked_groups"]["coverage_hit"]},
        }
    return {"contract_version": CONTRACT_VERSION, "scope": "schema_only",
            "planned_sources": PLANNED_SOURCES, "candidate_statuses": dict(sorted(statuses.items())),
            "summary": summary, "per_document": per_document,
            "limits": "No value, row-content, source-evidence, HITL, cost or product-release score."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-lock", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--aliases", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("report path already exists; preserve immutable scoring receipts")
    lock, lock_sha256 = read_json(args.source_lock)
    gold, gold_sha256 = read_json(args.gold)
    candidate, candidate_sha256 = read_json(args.candidate)
    aliases, aliases_sha256 = read_json(args.aliases)
    report = score_cohort(lock, gold, candidate, aliases, source_lock_sha256=lock_sha256)
    report["input_sha256"] = {"source_lock": lock_sha256, "gold": gold_sha256,
                              "candidate": candidate_sha256, "aliases": aliases_sha256}
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({"planned_sources": PLANNED_SOURCES, "candidate_statuses": report["candidate_statuses"],
                      "report": str(args.report)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

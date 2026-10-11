"""Verify that a product run actually processed distinct source documents."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from product_eval.contracts import (
    CONTRACT_VERSION,
    DOCUMENT_STATUSES,
    ContractError,
    load_jsonl,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContractError(f"{path}: cannot read JSON: {exc}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ContractError(f"{path}: cannot read source: {exc}") from exc
    return digest.hexdigest()


def _require_nonnegative_number(value: Any, label: str) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ContractError(f"{label} must be a finite non-negative number")


def verify_run(run_dir: str | Path, *, min_unique: int = 0, verify_sources: bool = True) -> dict[str, Any]:
    """Check a completed run's manifest, candidates, and source-byte evidence.

    One JSON-array entry is one source document. Its digest is computed from
    canonical JSON; for every other input the digest is computed from file bytes.
    Retries and repeated files cannot increase the distinct-source count.
    """
    if type(min_unique) is not int or min_unique < 0:
        raise ValueError("min_unique must be a non-negative integer")
    run_dir = Path(run_dir)
    run_path = run_dir / "run.json"
    run = _read_json(run_path)
    if not isinstance(run, dict) or run.get("contract_version") != CONTRACT_VERSION:
        raise ContractError(f"{run_path}: expected contract version {CONTRACT_VERSION}")
    run_id = run.get("run_id")
    if not isinstance(run_id, str) or not run_id or run.get("mode") != "product_auto":
        raise ContractError(f"{run_path}: invalid product run identity")

    candidates = load_jsonl(run_dir / "candidates.jsonl", kind="candidate")
    manifest_path = run_dir / "manifest.jsonl"
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ContractError(f"{manifest_path}: cannot read manifest: {exc}") from exc
    receipts: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        label = f"{manifest_path}:{line_number}"
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ContractError(f"{label}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict) or row.get("contract_version") != CONTRACT_VERSION:
            raise ContractError(f"{label}: invalid contract version")
        doc_id = row.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id or doc_id in receipts:
            raise ContractError(f"{label}: missing or duplicate doc_id")
        if row.get("run_id") != run_id:
            raise ContractError(f"{label}: run_id differs from run.json")
        source_hash = row.get("source_sha256")
        if not isinstance(source_hash, str) or not _SHA256.fullmatch(source_hash):
            raise ContractError(f"{label}: invalid source_sha256")
        if row.get("source_hash_kind") not in {"raw_file", "canonical_json_entry"}:
            raise ContractError(f"{label}: invalid source_hash_kind")
        if not isinstance(row.get("source_path"), str) or not row["source_path"]:
            raise ContractError(f"{label}: missing source_path")
        if type(row.get("source_index")) is not int or row["source_index"] < 0:
            raise ContractError(f"{label}: invalid source_index")
        if type(row.get("source_size_bytes")) is not int or row["source_size_bytes"] < 0:
            raise ContractError(f"{label}: invalid source_size_bytes")
        if row.get("document_status") not in DOCUMENT_STATUSES:
            raise ContractError(f"{label}: invalid document_status")
        for name in ("duration_ms", "page_count", "model_call_count"):
            _require_nonnegative_number(row.get(name), f"{label}.{name}")
        for name in ("page_count", "model_call_count"):
            if type(row[name]) is not int:
                raise ContractError(f"{label}.{name} must be an integer")
        receipts[doc_id] = row

    if receipts.keys() != candidates.keys():
        missing = sorted(receipts.keys() - candidates.keys())
        extra = sorted(candidates.keys() - receipts.keys())
        raise ContractError(f"candidate/manifest doc_id mismatch: missing={missing[:5]}, extra={extra[:5]}")
    counts: Counter[str] = Counter()
    hashes: Counter[str] = Counter()
    source_cache: dict[str, tuple[str, Any]] = {}
    total_duration_ms = 0.0
    for doc_id, row in receipts.items():
        status = row["document_status"]
        if candidates[doc_id]["document_status"] != status:
            raise ContractError(f"{doc_id}: candidate/manifest document_status mismatch")
        counts[status] += 1
        hashes[row["source_sha256"]] += 1
        total_duration_ms += row["duration_ms"]
        if not verify_sources:
            continue
        source_path = Path(row["source_path"])
        cache_key = str(source_path)
        if cache_key not in source_cache:
            file_hash = _sha256_file(source_path)
            source_cache[cache_key] = (file_hash, None)
        file_hash, entries = source_cache[cache_key]
        if row["source_hash_kind"] == "raw_file":
            if source_path.stat().st_size != row["source_size_bytes"]:
                raise ContractError(f"{doc_id}: source file size changed")
            expected = file_hash
        else:
            container_hash = row.get("source_container_sha256")
            if file_hash != container_hash:
                raise ContractError(f"{doc_id}: source container hash mismatch")
            if entries is None:
                parsed = _read_json(source_path)
                entries = parsed if isinstance(parsed, list) else [parsed]
                source_cache[cache_key] = (file_hash, entries)
            index = row["source_index"]
            if index >= len(entries):
                raise ContractError(f"{doc_id}: source_index exceeds JSON array")
            encoded = json.dumps(entries[index], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(encoded) != row["source_size_bytes"]:
                raise ContractError(f"{doc_id}: canonical source entry size changed")
            expected = hashlib.sha256(encoded).hexdigest()
        if expected != row["source_sha256"]:
            raise ContractError(f"{doc_id}: source_sha256 does not match source content")

    if type(run.get("doc_count")) is not int or run["doc_count"] != len(receipts):
        raise ContractError(f"{run_path}: doc_count does not match manifest")
    if not isinstance(run.get("status_counts"), dict) or any(
        run["status_counts"].get(status) != counts[status] for status in DOCUMENT_STATUSES
    ):
        raise ContractError(f"{run_path}: status_counts do not match manifest")
    unique_count = len(hashes)
    if unique_count < min_unique:
        raise ContractError(f"run has {unique_count} distinct source SHA-256 hashes; requires {min_unique}")
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "documents": len(receipts),
        "distinct_sources": unique_count,
        "repeated_source_outputs": sum(count - 1 for count in hashes.values()),
        "source_hashes_verified": verify_sources,
        "status_counts": {status: counts[status] for status in sorted(DOCUMENT_STATUSES)},
        "sum_document_duration_ms": round(total_duration_ms, 3),
    }


def verify_runs(run_dirs: list[str | Path], *, min_unique: int = 0) -> dict[str, Any]:
    """Verify completed shards and count unique source bytes across all shards."""
    if not run_dirs:
        raise ValueError("at least one run directory is required")
    reports = [verify_run(run_dir) for run_dir in run_dirs]
    seen_runs: set[str] = set()
    seen_docs: set[str] = set()
    source_hashes: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    for run_dir, report in zip(run_dirs, reports):
        run_id = report["run_id"]
        if run_id in seen_runs:
            raise ContractError(f"duplicate run_id {run_id!r}")
        seen_runs.add(run_id)
        path = Path(run_dir) / "manifest.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            receipt = json.loads(line)
            doc_id = receipt["doc_id"]
            if doc_id in seen_docs:
                raise ContractError(f"duplicate doc_id across runs: {doc_id!r}")
            seen_docs.add(doc_id)
            source_hashes[receipt["source_sha256"]] += 1
            counts[receipt["document_status"]] += 1
    distinct = len(source_hashes)
    if distinct < min_unique:
        raise ContractError(f"runs have {distinct} distinct source SHA-256 hashes; requires {min_unique}")
    return {
        "contract_version": CONTRACT_VERSION,
        "run_ids": sorted(seen_runs),
        "documents": len(seen_docs),
        "distinct_sources": distinct,
        "repeated_source_outputs": sum(count - 1 for count in source_hashes.values()),
        "source_hashes_verified": True,
        "status_counts": {status: counts[status] for status in sorted(DOCUMENT_STATUSES)},
        "sum_document_duration_ms": round(sum(report["sum_document_duration_ms"] for report in reports), 3),
    }

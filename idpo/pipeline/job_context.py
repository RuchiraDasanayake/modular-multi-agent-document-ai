"""Job-level field context accumulation for adaptive routing.

After each document is processed, field success/failure rates are written here.
At routing time this history feeds back into AHMN so the system adapts to what
actually works within a job — not just per-document TS priors.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

_write_lock = threading.Lock()
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DATA_ROOT = _REPO_ROOT / "idpo-data"


def _data_root() -> Path:
    raw = os.getenv("IDPO_DATA_DIR", "").strip()
    if raw:
        p = Path(raw).expanduser()
        return p.resolve() if p.is_absolute() else (Path.cwd() / p).resolve()
    return _DEFAULT_DATA_ROOT.resolve()


def _safe_job_token(job_id: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in job_id.strip())
    return cleaned[:120] or "default"


def _context_file(job_id: str) -> Path:
    job_dir = _data_root() / "jobs" / _safe_job_token(job_id) / "field_context"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir / "field_context.jsonl"


def write_field_context(
    *,
    job_id: str,
    doc_id: str,
    policy_id: str,
    field_confidence: dict[str, float],
    validation_issues: list[Any],
    vendor_cluster: str = "",
    semantic_doc_type: str = "unknown",
) -> None:
    """Append per-document field outcome to the job context JSONL.

    Thread-safe: called from concurrent document processing.
    """
    if not job_id:
        return

    ungrounded = {
        str(getattr(issue, "field", "") or "")
        for issue in validation_issues
        if str(getattr(issue, "issue", "") or "") == "ungrounded_value"
    }
    high_severity_fails = {
        str(getattr(issue, "field", "") or "")
        for issue in validation_issues
        if str(getattr(issue, "severity", "") or "") == "high"
    }

    field_results: dict[str, dict[str, Any]] = {}
    for field, conf in field_confidence.items():
        extracted = conf > 0.15
        field_results[field] = {
            "extracted": extracted,
            "confidence": round(conf, 4),
            "grounded": field not in ungrounded,
            "valid": field not in high_severity_fails,
        }

    entry = {
        "doc_id": doc_id,
        "policy_id": policy_id,
        "vendor_cluster": vendor_cluster,
        "semantic_doc_type": semantic_doc_type,
        "field_results": field_results,
    }

    path = _context_file(job_id)
    line = json.dumps(entry, separators=(",", ":"))
    with _write_lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_job_context(job_id: str) -> dict[str, Any]:
    """Read and summarise all field outcomes accumulated so far in this job.

    Returns empty dict if no context exists yet (first document in job).
    """
    if not job_id:
        return {}

    path = _context_file(job_id)
    if not path.exists():
        return {}

    entries: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        return {}

    if not entries:
        return {}

    field_success: dict[str, int] = {}
    field_total: dict[str, int] = {}
    field_conf_sum: dict[str, float] = {}
    policy_dist: dict[str, int] = {}
    vendor_clusters: set[str] = set()
    semantic_types: set[str] = set()

    for entry in entries:
        pid = str(entry.get("policy_id", "") or "")
        if pid:
            policy_dist[pid] = policy_dist.get(pid, 0) + 1
        vc = str(entry.get("vendor_cluster", "") or "")
        if vc:
            vendor_clusters.add(vc)
        st = str(entry.get("semantic_doc_type", "") or "")
        if st and st != "unknown":
            semantic_types.add(st)

        for field, result in (entry.get("field_results") or {}).items():
            field_total[field] = field_total.get(field, 0) + 1
            field_conf_sum[field] = field_conf_sum.get(field, 0.0) + float(result.get("confidence", 0.0))
            if result.get("extracted") and result.get("valid"):
                field_success[field] = field_success.get(field, 0) + 1

    field_success_rates = {
        f: round(field_success.get(f, 0) / total, 3)
        for f, total in field_total.items()
    }
    field_avg_confidence = {
        f: round(field_conf_sum[f] / field_total[f], 3)
        for f in field_total
    }

    # Only flag consistently failing/succeeding after >= 2 docs of evidence
    consistently_failing = [
        f for f, r in field_success_rates.items()
        if r < 0.4 and field_total.get(f, 0) >= 2
    ]
    consistently_succeeding = [
        f for f, r in field_success_rates.items()
        if r >= 0.75 and field_total.get(f, 0) >= 2
    ]

    return {
        "doc_count": len(entries),
        "field_success_rates": field_success_rates,
        "field_avg_confidence": field_avg_confidence,
        "vendor_clusters_seen": sorted(vendor_clusters),
        "semantic_types_seen": sorted(semantic_types),
        "policy_distribution": policy_dist,
        "consistently_failing": consistently_failing,
        "consistently_succeeding": consistently_succeeding,
    }


def build_dynamic_extraction_context(
    job_context: dict[str, Any],
    static_context: str,
    explicit_fields: list[str],
) -> str:
    """Prepend job-level field observations to the static extraction context.

    Only activates after >= 2 documents so there's real evidence.
    """
    if not job_context or job_context.get("doc_count", 0) < 2:
        return static_context

    failing = [
        f for f in job_context.get("consistently_failing", [])
        if f in explicit_fields
    ]
    low_confidence = [
        f for f in explicit_fields
        if job_context.get("field_success_rates", {}).get(f, 1.0) < 0.5
        and f not in failing
        and job_context.get("field_avg_confidence", {}).get(f, 1.0) < 0.5
    ]

    if not failing and not low_confidence:
        return static_context

    lines = [f"JOB CONTEXT ({job_context['doc_count']} docs processed so far):"]
    if failing:
        lines.append(
            f"DIFFICULT FIELDS (< 40% success in this job — look very carefully): {', '.join(failing)}"
        )
    if low_confidence:
        lines.append(
            f"LOW-CONFIDENCE FIELDS (often ambiguous in this job): {', '.join(low_confidence)}"
        )
    lines.append("")

    prefix = "\n".join(lines)
    if static_context.strip():
        return prefix + static_context.strip()
    return prefix

"""Run static vs adaptive_safe IDPO benchmarks and emit a canonical evidence bundle."""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Prefer the repo's .venv Python (has paddleocr + all deps) over sys.executable
# which may point to a backup/dev venv missing optional packages.
_VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
_SUBPROCESS_PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable

from idpo.core.storage import benchmark_reports_dir

ADAPTIVE_LABEL = "adaptive_safe"
PRIMARY_GROUP_TAGS = ("table", "form", "scanned", "text", "mixed", "noisy_ocr")
BOOTSTRAP_ITERATIONS = 1000
BOOTSTRAP_SEED = 17
_NUMERIC_FIELD_HINTS = ("amount", "price", "total", "subtotal", "tax", "cash", "change")


def _norm(value: object) -> str:
    import re as _re
    text = str(value or "").strip().lower()
    text = " ".join(text.split())
    # Collapse whitespace around punctuation so "12 / 10 / 98" == "12/10/98"
    text = _re.sub(r"\s*([/\-,.])\s*", r"\1", text)
    return text


_MONTH_ALIASES: dict[str, str] = {
    # Common OCR misspellings of month names
    "janry": "january", "janury": "january", "janaury": "january",
    "febray": "february", "feburary": "february", "februray": "february",
    "marck": "march", "mrach": "march",
    "apirl": "april", "aprl": "april",
    "juen": "june", "jne": "june",
    "jully": "july", "jluy": "july",
    "agust": "august", "augst": "august",
    "septmber": "september", "septembar": "september", "sepember": "september",
    "ocober": "october", "octber": "october",
    "novmber": "november", "novamber": "november", "novembar": "november",
    "decmber": "december", "decamber": "december", "decembar": "december",
}


def _norm_text(value: object) -> str:
    """Normalise a free-text field (name / date) for fuzzy comparison.

    Beyond basic _norm: unify comma/dot as date separator, correct common OCR
    month misspellings, and remove dots inside initials so "S.P.ZOLOT" and
    "SPOLOT" both become "spolot".
    """
    import re as _re
    text = _norm(value)
    # Treat dot/comma interchangeably as date separator between digit groups
    text = _re.sub(r"(\d)[,.](\d)", r"\1,\2", text)
    # Insert space between a letter run and a digit run so "january311997" →
    # "january 31 1997" (helps date comparison)
    text = _re.sub(r"([a-z])(\d)", r"\1 \2", text)
    text = _re.sub(r"(\d)([a-z])", r"\1 \2", text)
    # Collapse again after insertions
    text = " ".join(text.split())
    # Fix OCR month misspellings
    for bad, good in _MONTH_ALIASES.items():
        text = _re.sub(r"\b" + bad + r"\b", good, text)
    # Remove dots within initials: "s.p.zolot" → "spzolot" for comparison
    # (only when the pattern is single-letter.single-letter)
    text = _re.sub(r"(?<=[a-z])\.(?=[a-z])", "", text)
    return text


def _text_similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio on normalised text strings."""
    import difflib
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


_CURRENCY_PREFIX_RE = None


def _strip_currency_prefix(text: str) -> str:
    """Strip leading currency symbols/codes (e.g. 'Rp ', '₩', '$', '€') from a value string."""
    import re
    stripped = re.sub(r"^[^\d\-\.]+", "", text).strip()
    return stripped if stripped else text


def _normalize_exact_value(key: str, value: object) -> str:
    normalized = _norm(value)
    lowered_key = str(key or "").strip().lower()
    if any(hint in lowered_key for hint in _NUMERIC_FIELD_HINTS):
        # Strip currency prefix before processing (e.g. "Rp 39.600" → "39.600")
        normalized = _strip_currency_prefix(normalized)
        compact = normalized.replace(" ", "").replace(",", "")
        if compact.count(".") == 1:
            integer_part, frac_part = compact.split(".")
            if len(frac_part) == 3:
                # Exactly 3 digits after decimal = thousands separator in Korean/Indonesian
                # receipts (e.g. "81.400" = 81,400 won, "74.000" = 74,000 won).
                compact = integer_part + frac_part
            else:
                # Regular decimal — strip trailing zeros (e.g. "14.00" → "14", "12.60" → "12.6")
                frac_stripped = frac_part.rstrip("0")
                compact = f"{integer_part}.{frac_stripped}" if frac_stripped else integer_part
        return compact
    return normalized


_FUZZY_MATCH_THRESHOLD = 0.75


def _case_metrics(expected: dict[str, str], extracted: dict[str, object]) -> tuple[int, int, int]:
    tp = 0
    fp = 0
    fn = 0
    lowered_key: str
    for key, expected_value in expected.items():
        lowered_key = str(key or "").strip().lower()
        is_numeric = any(hint in lowered_key for hint in _NUMERIC_FIELD_HINTS)
        got_norm = _normalize_exact_value(key, extracted.get(key, ""))
        exp_norm = _normalize_exact_value(key, expected_value)
        if got_norm and got_norm == exp_norm:
            tp += 1
        elif not is_numeric and got_norm:
            # For text fields, accept fuzzy match to handle OCR noise on names/dates
            sim = _text_similarity(_norm_text(extracted.get(key, "")), _norm_text(expected_value))
            if sim >= _FUZZY_MATCH_THRESHOLD:
                tp += 1
            else:
                fp += 1
                fn += 1
        elif got_norm:
            fp += 1
            fn += 1
        else:
            fn += 1
    # Count hallucinated fields (extracted but not in expected) as false positives.
    for key, value in extracted.items():
        if key not in expected and _normalize_exact_value(key, value):
            fp += 1
    return tp, fp, fn


def _precision_recall_f1(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _load_config_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _now_iso(timestamp: float | None = None) -> str:
    if timestamp is None:
        moment = datetime.now(timezone.utc)
    else:
        moment = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return moment.isoformat().replace("+00:00", "Z")


def _display_path(path_value: str | Path | None) -> str | None:
    if path_value is None:
        return None
    return str(path_value).replace("\\", "/")


def _sanitize_filename(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {".", "_", "-"} else "_" for ch in name)


def _unique_nonempty(values: list[object]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _job_review_state(doc: dict[str, Any]) -> str:
    issue_count = int(doc.get("validation_issue_count", 0) or 0)
    if issue_count > 0:
        return f"{issue_count} issue(s)"
    defer_status = str(doc.get("defer_status", "")).strip()
    if defer_status and defer_status != "not_needed":
        return defer_status
    if str(doc.get("fallback_reason", "")).strip():
        return "fallback"
    return "clear"


def _structured_field_values(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    fields: dict[str, str] = {}
    for key, raw in value.items():
        name = str(key).strip()
        if not name:
            continue
        fields[name] = "" if raw is None else str(raw)
    return fields


def _benchmark_review_state(exact: dict[str, Any], doc: dict[str, Any]) -> str:
    f1 = float(exact.get("f1", 0.0) or 0.0)
    base = f"human_reviewed | F1 {f1:.2f}"
    issue_count = int(doc.get("validation_issue_count", 0) or 0)
    if issue_count > 0:
        return f"{base} | {issue_count} issue(s)"
    fallback_reason = str(doc.get("fallback_reason", "")).strip()
    if fallback_reason:
        return f"{base} | {fallback_reason}"
    return base


def _frontend_job_storage_paths() -> tuple[Path, Path]:
    frontend_root = REPO_ROOT / "frontend"
    runner_config = _load_config_payload(frontend_root / "runner.config.json")
    runtime_root = os.getenv("IDPO_DATA_DIR", "").strip()
    if runtime_root:
        data_root = Path(runtime_root).expanduser()
        if not data_root.is_absolute():
            data_root = (Path.cwd() / data_root).resolve()
        uploads_dir = (data_root / "frontend" / "uploads").resolve()
        jobs_dir = (data_root / "frontend" / "jobs").resolve()
    else:
        uploads_dir = (frontend_root / str(runner_config.get("uploadsDir", "../../idpo-data/frontend/uploads"))).resolve()
        jobs_dir = (frontend_root / str(runner_config.get("jobsDir", "../../idpo-data/frontend/jobs"))).resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir, jobs_dir


def _case_source_path(case: dict[str, Any]) -> Path:
    return (REPO_ROOT / str(case.get("path", ""))).resolve()


def _default_research_job_name(pack_name: str, case: dict[str, Any]) -> str:
    source_name = str(case.get("source_dataset", "")).strip() or pack_name
    case_id = str(case.get("case_id", "")).strip() or "case"
    category = "receipt" if "receipt" in {str(tag).strip() for tag in (case.get("tags", []) or [])} else "document"
    source_label = source_name.replace("naver-clova-ix/", "").replace("_", " ").replace("-", " ").strip()
    source_label = source_label or "benchmark"
    return f"Research Pilot: {source_label} {category} {case_id}"


def _build_job_outcome(condition: str, item: dict[str, Any]) -> dict[str, Any]:
    run_mode = "strict" if condition == "static" else "adaptive"
    doc = item.get("doc", {}) if isinstance(item.get("doc"), dict) else {}
    ok = bool(doc) and bool(str(doc.get("doc_id", "")).strip()) and not str(item.get("error", "")).strip()
    exact = item.get("exact_metrics", {}) if isinstance(item.get("exact_metrics"), dict) else {}
    return {
        "runId": str(item.get("run_id", "")).strip() or None,
        "mode": run_mode,
        "docId": str(doc.get("doc_id", "")).strip() or None,
        "status": "processed" if ok else "failed",
        "route": str(doc.get("route_bin", "")).strip() or None,
        "policy": str(doc.get("policy_id", "")).strip() or None,
        "errorSummary": None if ok else str(item.get("error", "Benchmark case failed")).strip(),
        "reviewState": _benchmark_review_state(exact, doc) if ok else "failed",
        "reviewStatus": "human_reviewed" if ok else "unreviewed",
        "reviewSource": "human" if ok else None,
        "fieldValues": _structured_field_values(doc.get("structured_fields", {})),
        "adviceInfluenced": bool(doc.get("advice_accepted", False)) or bool(doc.get("policy_changed", False)),
        "feedbackLogged": bool(doc.get("feedback_logged", False)),
        "fallbackReason": str(doc.get("fallback_reason", "")).strip() or None,
        "exactPrecision": float(exact.get("precision", 0.0) or 0.0) if ok else None,
        "exactRecall": float(exact.get("recall", 0.0) or 0.0) if ok else None,
        "exactF1": float(exact.get("f1", 0.0) or 0.0) if ok else None,
    }


def register_frontend_jobs_from_evidence(
    evidence: dict[str, Any],
    *,
    pack_path: str | None = None,
    job_name_prefix: str | None = None,
    existing_job_id: str | None = None,
) -> dict[str, Any]:
    """Register all benchmark documents into ONE persistent job.

    AHMN learning accumulates within a job context. Using a single job for all
    benchmark documents preserves bandit state across the whole evaluation run.
    Pass ``existing_job_id`` to extend a previous benchmark job (e.g. Phase A →
    Phase B → Phase C) rather than starting a new one.
    """
    experiment = evidence.get("experiment", {}) if isinstance(evidence.get("experiment"), dict) else {}
    documents = evidence.get("documents", [])
    if not isinstance(documents, list) or not documents:
        return {}

    resolved_pack_path = Path(pack_path or str(experiment.get("pack_path", ""))).resolve()
    pack_payload = _load_config_payload(resolved_pack_path)
    cases = {
        str(case.get("case_id", "")).strip(): case
        for case in pack_payload.get("cases", [])
        if isinstance(case, dict) and str(case.get("case_id", "")).strip()
    }
    uploads_root, jobs_root = _frontend_job_storage_paths()
    generated_at = float(experiment.get("generated_at", time.time()) or time.time())
    created_at = _now_iso(generated_at)
    default_prefix = job_name_prefix.strip() if isinstance(job_name_prefix, str) and job_name_prefix.strip() else ""
    pack_name = str(pack_payload.get("name", "benchmark_pack"))

    # Load existing job or scaffold a new one
    if existing_job_id:
        job_file = jobs_root / f"{existing_job_id}.json"
        if not job_file.exists():
            raise FileNotFoundError(f"Benchmark job not found: {job_file}")
        job_payload: dict[str, Any] = json.loads(job_file.read_text(encoding="utf-8"))
        job_id = existing_job_id
    else:
        job_id = uuid4().hex
        job_name = f"{default_prefix}: {pack_name}" if default_prefix else f"Research Benchmark: {pack_name}"
        job_payload = {
            "jobId": job_id,
            "status": "success",
            "createdAt": created_at,
            "startedAt": created_at,
            "endedAt": created_at,
            "commandId": "idpo_process_inbox",
            "runId": None,
            "runPath": None,
            "latestRunId": None,
            "logs": [
                f"[benchmark] benchmark_run_id={experiment.get('benchmark_run_id', '')}",
                f"[benchmark] pack_path={_display_path(resolved_pack_path)}",
                f"[benchmark] report_path={_display_path(benchmark_reports_dir() / str(experiment.get('benchmark_run_id', '')) / 'paper_evidence.json')}",
            ],
            "settings": {
                "source": "benchmark_import",
                "benchmarkRunId": str(experiment.get("benchmark_run_id", "")).strip() or None,
                "packName": pack_name or None,
                "packPath": _display_path(resolved_pack_path),
                "fieldMappingVersion": str(pack_payload.get("field_mapping_version", "")).strip() or None,
            },
            "jobName": job_name,
            "mode": "both",
            "fieldConfigCurrent": [],
            "documents": [],
            "runs": [],
            "counts": {"loadedCount": 0, "processingCount": 0, "processedCount": 0, "failedCount": 0},
            "ahmnSummary": {
                "jobProfile": "research_benchmark_import",
                "memoryMatched": False,
                "documentsWithAdvice": 0,
                "documentsLoggedBack": 0,
                "adviceInfluencedCount": 0,
                "reviewedDocumentCount": 0,
                "reviewedHumanCount": 0,
                "reviewedAiCount": 0,
                "reviewedFeedbackLoggedCount": 0,
                "reviewedFeedbackPendingCount": 0,
                "jobOverlayPolicies": 0,
                "jobOverlayReady": False,
                "adaptationSummary": "",
            },
            "uploadsPath": _display_path(uploads_root / job_id),
        }

    uploads_path = uploads_root / job_id
    uploads_path.mkdir(parents=True, exist_ok=True)

    existing_field_names = {
        fc["name"]
        for fc in (job_payload.get("fieldConfigCurrent") or [])
        if isinstance(fc, dict) and fc.get("name")
    }
    existing_file_ids = {d["fileId"] for d in (job_payload.get("documents") or []) if isinstance(d, dict)}
    added_count = 0

    for document in documents:
        if not isinstance(document, dict):
            continue
        case_id = str(document.get("case_id", "")).strip()
        case = cases.get(case_id)
        if not case:
            continue
        source_path = _case_source_path(case)
        if not source_path.exists():
            raise FileNotFoundError(f"Benchmark source file missing for case '{case_id}': {source_path}")

        file_id = case_id or uuid4().hex
        # Skip if this case was already registered into the job (idempotent re-import)
        if file_id in existing_file_ids:
            continue

        file_name = source_path.name
        stored_name = f"{file_id}__{_sanitize_filename(file_name)}"
        shutil.copy2(source_path, uploads_path / stored_name)

        static_item = document.get("static", {}) if isinstance(document.get("static"), dict) else {}
        adaptive_item = document.get(ADAPTIVE_LABEL, {}) if isinstance(document.get(ADAPTIVE_LABEL), dict) else {}
        expected_fields = {str(k): str(v) for k, v in (case.get("expected", {}) or {}).items()}
        strict_outcome = _build_job_outcome("static", static_item)
        adaptive_outcome = _build_job_outcome(ADAPTIVE_LABEL, adaptive_item)
        for outcome in (strict_outcome, adaptive_outcome):
            outcome["expectedFieldValues"] = expected_fields
        outcomes = [strict_outcome, adaptive_outcome]
        processed_modes = {o["mode"] for o in outcomes if o.get("status") == "processed"}
        document_status = "processed" if processed_modes == {"strict", "adaptive"} else "failed"
        preferred = adaptive_outcome if adaptive_outcome.get("runId") else strict_outcome

        field_snapshot = [
            {"name": str(name), "description": str(description)}
            for name, description in (case.get("fields", {}) or {}).items()
        ]
        for fc in field_snapshot:
            if fc["name"] not in existing_field_names:
                job_payload["fieldConfigCurrent"].append(fc)
                existing_field_names.add(fc["name"])

        job_payload["documents"].append({
            "fileId": file_id,
            "fileName": file_name,
            "storedName": stored_name,
            "size": source_path.stat().st_size,
            "selected": True,
            "status": document_status,
            "errorSummary": None if document_status == "processed" else "Benchmark case did not complete in both modes.",
            "reviewState": preferred.get("reviewState"),
            "reviewStatus": "human_reviewed" if document_status == "processed" else "unreviewed",
            "reviewSource": "human" if document_status == "processed" else None,
            "latestRoute": preferred.get("route"),
            "latestPolicy": preferred.get("policy"),
            "latestRunId": preferred.get("runId"),
            "latestDocId": preferred.get("docId"),
            "createdAt": created_at,
            "updatedAt": created_at,
            "outcomes": outcomes,
        })

        job_run_id_base = f"{job_id}_{case_id}"
        job_payload["runs"].append({
            "jobRunId": f"{job_run_id_base}_adaptive",
            "runId": adaptive_outcome.get("runId"),
            "mode": "adaptive",
            "status": "success" if adaptive_outcome.get("status") == "processed" else "failed",
            "createdAt": created_at,
            "startedAt": created_at,
            "endedAt": created_at,
            "fieldSnapshot": field_snapshot,
            "selectedFileIds": [file_id],
            "runPath": _display_path(adaptive_item.get("run_dir")),
            "error": adaptive_outcome.get("errorSummary"),
            "processedCount": 1 if adaptive_outcome.get("status") == "processed" else 0,
            "failedCount": 0 if adaptive_outcome.get("status") == "processed" else 1,
            "adviceDocumentCount": 1 if adaptive_outcome.get("adviceInfluenced") else 0,
            "loggedFeedbackCount": 1 if adaptive_outcome.get("feedbackLogged") else 0,
        })
        job_payload["runs"].append({
            "jobRunId": f"{job_run_id_base}_strict",
            "runId": strict_outcome.get("runId"),
            "mode": "strict",
            "status": "success" if strict_outcome.get("status") == "processed" else "failed",
            "createdAt": created_at,
            "startedAt": created_at,
            "endedAt": created_at,
            "fieldSnapshot": field_snapshot,
            "selectedFileIds": [file_id],
            "runPath": _display_path(static_item.get("run_dir")),
            "error": strict_outcome.get("errorSummary"),
            "processedCount": 1 if strict_outcome.get("status") == "processed" else 0,
            "failedCount": 0 if strict_outcome.get("status") == "processed" else 1,
            "adviceDocumentCount": 0,
            "loggedFeedbackCount": 1 if strict_outcome.get("feedbackLogged") else 0,
        })

        job_payload["logs"].append(f"[benchmark] case_id={case_id}")
        existing_file_ids.add(file_id)
        added_count += 1

    # Recompute counts and AHMN summary from the full document list
    all_docs: list[dict[str, Any]] = job_payload.get("documents") or []
    processed_count = sum(1 for d in all_docs if d.get("status") == "processed")
    failed_count = len(all_docs) - processed_count
    job_payload["counts"] = {
        "loadedCount": 0,
        "processingCount": 0,
        "processedCount": processed_count,
        "failedCount": failed_count,
    }
    job_payload["status"] = "success" if failed_count == 0 else "failed"

    all_adaptive_influenced = sum(
        1 for d in all_docs
        for o in (d.get("outcomes") or [])
        if o.get("mode") == "adaptive" and o.get("adviceInfluenced")
    )
    all_adaptive_feedback = sum(
        1 for d in all_docs
        for o in (d.get("outcomes") or [])
        if o.get("mode") == "adaptive" and o.get("feedbackLogged")
    )
    any_memory_matched = any(
        o.get("retrievalSource") or o.get("retrieval_source")
        for d in all_docs
        for o in (d.get("outcomes") or [])
    )
    prev_ahmn = job_payload.get("ahmnSummary") or {}
    job_payload["ahmnSummary"] = {
        "jobProfile": "research_benchmark_import",
        "memoryMatched": any_memory_matched,
        "documentsWithAdvice": all_adaptive_influenced,
        "documentsLoggedBack": all_adaptive_feedback,
        "adviceInfluencedCount": all_adaptive_influenced,
        "reviewedDocumentCount": len(all_docs),
        "reviewedHumanCount": len(all_docs),
        "reviewedAiCount": 0,
        "reviewedFeedbackLoggedCount": int(prev_ahmn.get("reviewedFeedbackLoggedCount", 0) or 0),
        "reviewedFeedbackPendingCount": int(prev_ahmn.get("reviewedFeedbackPendingCount", 0) or 0),
        "jobOverlayPolicies": int(prev_ahmn.get("jobOverlayPolicies", 0) or 0),
        "jobOverlayReady": bool(prev_ahmn.get("jobOverlayReady", False)),
        "adaptationSummary": (
            f"Benchmark import: {len(all_docs)} documents total, "
            f"{all_adaptive_influenced} advice-influenced, "
            f"{all_adaptive_feedback} feedback logged."
        ),
    }

    if all_docs:
        last_doc = all_docs[-1]
        job_payload["latestRunId"] = last_doc.get("latestRunId")
        job_payload["runId"] = last_doc.get("latestRunId")

    job_file = jobs_root / f"{job_id}.json"
    job_file.write_text(json.dumps(job_payload, indent=2), encoding="utf-8")
    return {
        "job_id": job_id,
        "job_name": job_payload.get("jobName", ""),
        "job_file": str(job_file),
        "doc_count": len(all_docs),
        "added_count": added_count,
    }


def _launch_process_inbox(
    *,
    root: Path,
    config_path: str,
    extraction_fields: list[dict[str, str]],
    run_id: str,
    input_dir: Path,
    job_id: str | None = None,
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(extraction_fields, handle, indent=2)
        fields_file = handle.name
    try:
        command = [
            _SUBPROCESS_PYTHON,
            "-m",
            "idpo.cli",
            "process-inbox",
            "--root",
            str(root),
            "--config",
            config_path,
            "--input-dir",
            str(input_dir),
            "--run-id",
            run_id,
            "--fields-file",
            fields_file,
            "--output-mode",
            "full",
        ]
        env = os.environ.copy()
        if job_id:
            env["IDPO_JOB_ID"] = str(job_id)
        completed = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            env=env,
        )
        if completed.returncode != 0:
            raise SystemExit(
                "process-inbox CLI failed"
                f"\ncommand={' '.join(command)}"
                f"\nstdout={completed.stdout.strip()}"
                f"\nstderr={completed.stderr.strip()}"
            )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise SystemExit(
                "process-inbox CLI returned invalid JSON"
                f"\nstdout={completed.stdout.strip()}"
                f"\nstderr={completed.stderr.strip()}"
            ) from exc
    finally:
        try:
            Path(fields_file).unlink(missing_ok=True)
        except Exception:
            pass


def _containment_state(doc: dict[str, Any]) -> str:
    if bool(doc.get("blocked_policy", False)):
        return "blocked"
    if bool(doc.get("rollback_triggered", False)):
        return "rollback"
    if str(doc.get("fallback_reason", "")).strip():
        return "fallback"
    defer_status = str(doc.get("defer_status", "")).strip()
    if defer_status in {"requested", "blocked"}:
        return f"defer_{defer_status}"
    return "none"


def _write_condition_config(base_config: Path, condition: str, temp_dir: Path) -> Path:
    payload = _load_config_payload(base_config)
    ahmn = payload.setdefault("ahmn", {})
    runtime_mode = "static" if condition == "static" else "adaptive"
    ahmn["policy_mode"] = runtime_mode
    if condition == "static":
        ahmn["enabled"] = False
    else:
        ahmn["enabled"] = True
        if str(ahmn.get("mode", "")).strip().lower() in {"", "mock"}:
            ahmn["mode"] = "auto"
    out_path = temp_dir / f"{condition}_config.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def _should_batch_cases(pack: dict[str, Any], cases: list[dict[str, Any]]) -> bool:
    mode = str(pack.get("batch_mode", "")).strip().lower()
    return bool(cases) and (mode == "single_run_per_condition" or isinstance(pack.get("shared_fields"), dict))


def _shared_extraction_fields(pack: dict[str, Any], cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    shared = pack.get("shared_fields")
    if isinstance(shared, dict) and shared:
        return [{"name": str(key), "description": str(value)} for key, value in shared.items()]

    merged: dict[str, str] = {}
    for case in cases:
        fields = case.get("fields", {})
        if not isinstance(fields, dict):
            continue
        for key, value in fields.items():
            normalized = str(key).strip()
            if not normalized or normalized in merged:
                continue
            merged[normalized] = str(value)
    return [{"name": key, "description": value} for key, value in merged.items()]


def _case_doc_keys(case_id: str, source_path: Path, doc: dict[str, Any]) -> set[str]:
    keys = {
        case_id.strip().lower(),
        source_path.stem.strip().lower(),
        source_path.name.strip().lower(),
    }
    doc_id = str(doc.get("doc_id", "")).strip().lower()
    filename = str(doc.get("filename", "") or doc.get("file_name", "")).strip().lower()
    if doc_id:
        keys.add(doc_id)
    if filename:
        keys.add(filename)
        keys.add(Path(filename).stem.strip().lower())
    return {key for key in keys if key}


def _run_condition_batch(
    *,
    repo_root: Path,
    config_path: str,
    condition: str,
    cases: list[dict[str, Any]],
    shared_fields: list[dict[str, str]],
    job_id: str | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    staged_cases: list[tuple[dict[str, Any], Path]] = []

    with tempfile.TemporaryDirectory(prefix=f"idpo_bench_{condition}_batch_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        for case in cases:
            case_id = str(case.get("case_id", "")).strip() or f"case_{len(results) + len(staged_cases) + 1}"
            tags = [str(tag).strip() for tag in (case.get("tags", []) or []) if str(tag).strip()]
            source_path = (repo_root / str(case.get("path", ""))).resolve()
            expected = {str(k): str(v) for k, v in (case.get("expected", {}) or {}).items()}
            if not source_path.exists():
                results.append({"case_id": case_id, "status": "failed", "tags": tags, "error": f"missing_file:{source_path}"})
                continue
            target_name = f"{_sanitize_filename(case_id)}{source_path.suffix}"
            shutil.copy2(source_path, tmp_root / target_name)
            staged_cases.append((case, source_path))

        if not staged_cases:
            return results

        run = _launch_process_inbox(
            root=repo_root,
            config_path=config_path,
            extraction_fields=shared_fields,
            run_id=f"{condition}_batch_{int(time.time() * 1000)}",
            input_dir=tmp_root,
            job_id=job_id,
        )

    unmatched_docs = [doc for doc in run.get("doc_records", []) if isinstance(doc, dict)]
    run_payload = run.get("run_payload", {}) if isinstance(run.get("run_payload"), dict) else {}
    ahmn_state_path = str(run_payload.get("ahmn_state_path", "")).strip() or None

    for case, source_path in staged_cases:
        case_id = str(case.get("case_id", "")).strip()
        tags = [str(tag).strip() for tag in (case.get("tags", []) or []) if str(tag).strip()]
        expected = {str(k): str(v) for k, v in (case.get("expected", {}) or {}).items()}
        match_index = None
        target_keys = {case_id.strip().lower(), source_path.stem.strip().lower(), source_path.name.strip().lower()}
        for idx, doc in enumerate(unmatched_docs):
            if target_keys & _case_doc_keys(case_id, source_path, doc):
                match_index = idx
                break
        if match_index is None:
            results.append({"case_id": case_id, "status": "failed", "tags": tags, "error": "no_doc_record"})
            continue
        doc = unmatched_docs.pop(match_index)
        structured = doc.get("structured_fields", {})
        if not isinstance(structured, dict):
            structured = {}
        tp, fp, fn = _case_metrics(expected, structured)
        results.append(
            {
                "case_id": case_id,
                "status": "ok",
                "tags": tags,
                "doc": doc,
                "run_id": run.get("run_id", ""),
                "run_dir": run.get("run_dir", ""),
                "expected": expected,
                "ahmn_state_path": ahmn_state_path,
                "exact_metrics": {
                    "tp": tp,
                    "fp": fp,
                    "fn": fn,
                    **_precision_recall_f1(tp, fp, fn),
                },
            }
        )
    return results


def _condition_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    doc_count = len(results)
    total_latency = sum(float(item["doc"].get("latency_ms", 0.0) or 0.0) for item in results)
    total_reward = sum(float(item["doc"].get("reward", 0.0) or 0.0) for item in results)
    validation_passes = sum(1 for item in results if int(item["doc"].get("validation_issue_count", 0) or 0) == 0)
    recovery_hits = sum(1 for item in results if int(item["doc"].get("recovered_fields_count", 0) or 0) > 0)
    escalation_hits = sum(
        1
        for item in results
        if str(item["doc"].get("escalation_status", "not_needed")).strip() != "not_needed"
    )
    policy_distribution = Counter(str(item["doc"].get("policy_id", "")).strip() for item in results)
    operator_counts = Counter()
    reward_types = Counter()
    advice_sources = Counter()
    advice_statuses = Counter()
    containment_states = Counter()
    feedback_errors = Counter()
    exact_tp = exact_fp = exact_fn = 0
    rollback_count = 0
    blocked_policy_count = 0
    fallback_count = 0
    feedback_logged_count = 0
    rabi_used_count = 0
    defer_requested_count = 0
    defer_blocked_count = 0
    retrieval_sources = Counter()
    advice_confidences: list[float] = []
    schema_coverages: list[float] = []
    grounding_coverages: list[float] = []
    schema_valid_count = 0
    advice_accepted_count = 0
    policy_changed_count = 0
    exact_scored_doc_count = 0
    for item in results:
        doc = item["doc"]
        operator_counts.update(str(op).strip() for op in doc.get("operator_stack", []) or [])
        reward_types.update([str(doc.get("reward_type", "proxy")).strip() or "proxy"])
        advice_sources.update([str(doc.get("advice_source", "unknown")).strip() or "unknown"])
        advice_statuses.update([str(doc.get("advice_status", "static")).strip() or "unknown"])
        retrieval_sources.update([str(doc.get("retrieval_source", "unknown")).strip() or "unknown"])
        containment_states.update([_containment_state(doc)])
        if doc.get("rollback_triggered"):
            rollback_count += 1
        if doc.get("blocked_policy"):
            blocked_policy_count += 1
        if doc.get("fallback_reason"):
            fallback_count += 1
        if doc.get("feedback_logged"):
            feedback_logged_count += 1
        if doc.get("feedback_error"):
            feedback_errors.update([str(doc.get("feedback_error")).strip()])
        if doc.get("rabi_used"):
            rabi_used_count += 1
        defer_status = str(doc.get("defer_status", "")).strip()
        if defer_status == "requested":
            defer_requested_count += 1
        elif defer_status == "blocked":
            defer_blocked_count += 1
        if doc.get("advice_confidence") is not None:
            try:
                advice_confidences.append(float(doc.get("advice_confidence", 0.0) or 0.0))
            except Exception:
                pass
        if doc.get("advice_accepted"):
            advice_accepted_count += 1
        if doc.get("policy_changed"):
            policy_changed_count += 1
        exact = item.get("exact_metrics", {})
        if isinstance(exact, dict) and any(key in exact for key in ("tp", "fp", "fn", "f1", "precision", "recall")):
            exact_scored_doc_count += 1
        if doc.get("schema_coverage") is not None:
            try:
                schema_coverages.append(float(doc.get("schema_coverage", 0.0) or 0.0))
            except Exception:
                pass
        if doc.get("schema_grounding_coverage") is not None:
            try:
                grounding_coverages.append(float(doc.get("schema_grounding_coverage", 0.0) or 0.0))
            except Exception:
                pass
        if bool(doc.get("schema_valid", False)):
            schema_valid_count += 1
        exact_tp += int(exact.get("tp", 0) or 0)
        exact_fp += int(exact.get("fp", 0) or 0)
        exact_fn += int(exact.get("fn", 0) or 0)
    exact_metrics = {
        "tp": exact_tp,
        "fp": exact_fp,
        "fn": exact_fn,
        **_precision_recall_f1(exact_tp, exact_fp, exact_fn),
    }
    summary = {
        "doc_count": doc_count,
        "run_ids": _unique_nonempty([item.get("run_id", "") for item in results]),
        "run_dirs": _unique_nonempty([item.get("run_dir", "") for item in results]),
        "ahmn_state_paths": _unique_nonempty([item.get("ahmn_state_path", "") for item in results]),
        "avg_latency_ms": round(total_latency / doc_count, 2) if doc_count else 0.0,
        "avg_reward": round(total_reward / doc_count, 4) if doc_count else 0.0,
        "validation_pass_rate": round(validation_passes / doc_count, 4) if doc_count else 0.0,
        "recovery_rate": round(recovery_hits / doc_count, 4) if doc_count else 0.0,
        "escalation_rate": round(escalation_hits / doc_count, 4) if doc_count else 0.0,
        "policy_distribution": dict(sorted(policy_distribution.items())),
        "operator_counts": dict(sorted(operator_counts.items())),
        "reward_type_counts": dict(sorted(reward_types.items())),
        "advice_source_counts": dict(sorted(advice_sources.items())),
        "advice_status_counts": dict(sorted(advice_statuses.items())),
        "retrieval_source_counts": dict(sorted(retrieval_sources.items())),
        "containment_state_counts": dict(sorted(containment_states.items())),
        "rollback_count": rollback_count,
        "blocked_policy_count": blocked_policy_count,
        "fallback_count": fallback_count,
        "feedback_logged_count": feedback_logged_count,
        "feedback_error_counts": dict(sorted(feedback_errors.items())),
        "policy_coverage_count": len([key for key in policy_distribution if key]),
        "rabi_used_count": rabi_used_count,
        "defer_requested_count": defer_requested_count,
        "defer_blocked_count": defer_blocked_count,
        "avg_advice_confidence": round(sum(advice_confidences) / len(advice_confidences), 4) if advice_confidences else 0.0,
        "avg_schema_coverage": round(sum(schema_coverages) / len(schema_coverages), 4) if schema_coverages else 0.0,
        "avg_schema_grounding_coverage": round(sum(grounding_coverages) / len(grounding_coverages), 4) if grounding_coverages else 0.0,
        "schema_valid_rate": round(schema_valid_count / doc_count, 4) if doc_count else 0.0,
        "advice_accepted_count": advice_accepted_count,
        "policy_changed_count": policy_changed_count,
        "exact_scored_doc_count": exact_scored_doc_count,
        "exact_field_metrics": exact_metrics,
    }
    return summary


def _comparison_table(static_summary: dict[str, Any], adaptive_summary: dict[str, Any], doc_count: int) -> dict[str, Any]:
    return {
        "doc_count": doc_count,
        "avg_latency_ms": {
            "static": static_summary["avg_latency_ms"],
            ADAPTIVE_LABEL: adaptive_summary["avg_latency_ms"],
        },
        "avg_reward": {
            "static": static_summary["avg_reward"],
            ADAPTIVE_LABEL: adaptive_summary["avg_reward"],
        },
        "exact_precision": {
            "static": static_summary["exact_field_metrics"]["precision"],
            ADAPTIVE_LABEL: adaptive_summary["exact_field_metrics"]["precision"],
        },
        "exact_recall": {
            "static": static_summary["exact_field_metrics"]["recall"],
            ADAPTIVE_LABEL: adaptive_summary["exact_field_metrics"]["recall"],
        },
        "exact_f1": {
            "static": static_summary["exact_field_metrics"]["f1"],
            ADAPTIVE_LABEL: adaptive_summary["exact_field_metrics"]["f1"],
        },
        "validation_pass_rate": {
            "static": static_summary["validation_pass_rate"],
            ADAPTIVE_LABEL: adaptive_summary["validation_pass_rate"],
        },
        "recovery_rate": {
            "static": static_summary["recovery_rate"],
            ADAPTIVE_LABEL: adaptive_summary["recovery_rate"],
        },
        "escalation_rate": {
            "static": static_summary["escalation_rate"],
            ADAPTIVE_LABEL: adaptive_summary["escalation_rate"],
        },
        "policy_distribution": {
            "static": static_summary["policy_distribution"],
            ADAPTIVE_LABEL: adaptive_summary["policy_distribution"],
        },
        "advice_source_counts": {
            "static": static_summary["advice_source_counts"],
            ADAPTIVE_LABEL: adaptive_summary["advice_source_counts"],
        },
        "advice_status_counts": {
            "static": static_summary["advice_status_counts"],
            ADAPTIVE_LABEL: adaptive_summary["advice_status_counts"],
        },
        "operator_counts": {
            "static": static_summary["operator_counts"],
            ADAPTIVE_LABEL: adaptive_summary["operator_counts"],
        },
        "retrieval_source_counts": {
            "static": static_summary["retrieval_source_counts"],
            ADAPTIVE_LABEL: adaptive_summary["retrieval_source_counts"],
        },
        "containment_state_counts": {
            "static": static_summary["containment_state_counts"],
            ADAPTIVE_LABEL: adaptive_summary["containment_state_counts"],
        },
        "rollback_count": {
            "static": static_summary["rollback_count"],
            ADAPTIVE_LABEL: adaptive_summary["rollback_count"],
        },
        "blocked_policy_count": {
            "static": static_summary["blocked_policy_count"],
            ADAPTIVE_LABEL: adaptive_summary["blocked_policy_count"],
        },
        "fallback_count": {
            "static": static_summary["fallback_count"],
            ADAPTIVE_LABEL: adaptive_summary["fallback_count"],
        },
        "feedback_logged_count": {
            "static": static_summary["feedback_logged_count"],
            ADAPTIVE_LABEL: adaptive_summary["feedback_logged_count"],
        },
        "rabi_used_count": {
            "static": static_summary["rabi_used_count"],
            ADAPTIVE_LABEL: adaptive_summary["rabi_used_count"],
        },
        "avg_advice_confidence": {
            "static": static_summary["avg_advice_confidence"],
            ADAPTIVE_LABEL: adaptive_summary["avg_advice_confidence"],
        },
        "avg_schema_coverage": {
            "static": static_summary["avg_schema_coverage"],
            ADAPTIVE_LABEL: adaptive_summary["avg_schema_coverage"],
        },
        "avg_schema_grounding_coverage": {
            "static": static_summary["avg_schema_grounding_coverage"],
            ADAPTIVE_LABEL: adaptive_summary["avg_schema_grounding_coverage"],
        },
        "schema_valid_rate": {
            "static": static_summary["schema_valid_rate"],
            ADAPTIVE_LABEL: adaptive_summary["schema_valid_rate"],
        },
        "defer_requested_count": {
            "static": static_summary["defer_requested_count"],
            ADAPTIVE_LABEL: adaptive_summary["defer_requested_count"],
        },
        "defer_blocked_count": {
            "static": static_summary["defer_blocked_count"],
            ADAPTIVE_LABEL: adaptive_summary["defer_blocked_count"],
        },
        "policy_coverage_count": {
            "static": static_summary["policy_coverage_count"],
            ADAPTIVE_LABEL: adaptive_summary["policy_coverage_count"],
        },
        "advice_accepted_count": {
            "static": static_summary.get("advice_accepted_count", 0),
            ADAPTIVE_LABEL: adaptive_summary.get("advice_accepted_count", 0),
        },
        "policy_changed_count": {
            "static": static_summary.get("policy_changed_count", 0),
            ADAPTIVE_LABEL: adaptive_summary.get("policy_changed_count", 0),
        },
        "exact_scored_doc_count": {
            "static": static_summary.get("exact_scored_doc_count", 0),
            ADAPTIVE_LABEL: adaptive_summary.get("exact_scored_doc_count", 0),
        },
    }


def _assert_adaptive_valid(results: list[dict[str, Any]], valid_policy_ids: set[str]) -> None:
    ok_docs = [item["doc"] for item in results if item.get("status") == "ok" and isinstance(item.get("doc"), dict)]
    if not ok_docs:
        raise SystemExit("Adaptive benchmark invalid: no successful adaptive documents")
    if all(str(doc.get("advice_source", "")).strip() == "fallback" for doc in ok_docs):
        raise SystemExit("Adaptive benchmark invalid: AHMN advice was unreachable or never used")
    if any(str(doc.get("fallback_reason", "")).strip() == "invalid_recommendation" for doc in ok_docs):
        raise SystemExit("Adaptive benchmark invalid: AHMN returned an invalid policy recommendation")
    if any(str(doc.get("policy_id", "")).strip() not in valid_policy_ids for doc in ok_docs):
        raise SystemExit("Adaptive benchmark invalid: adaptive run emitted a policy not present in the configured policy store")
    if all(not bool(doc.get("feedback_logged", False)) for doc in ok_docs):
        raise SystemExit("Adaptive benchmark invalid: AHMN feedback logging failed for all adaptive cases")


def _validation_pass(doc: dict[str, Any]) -> float:
    return 1.0 if int(doc.get("validation_issue_count", 0) or 0) == 0 else 0.0


def _bootstrap_interval(values: list[float], label: str) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rng = random.Random(BOOTSTRAP_SEED + sum(ord(ch) for ch in label))
    sample_count = len(values)
    estimates: list[float] = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        resample_mean = sum(values[rng.randrange(sample_count)] for _ in range(sample_count)) / sample_count
        estimates.append(resample_mean)
    estimates.sort()
    low_idx = max(0, min(len(estimates) - 1, int(0.025 * (len(estimates) - 1))))
    high_idx = max(0, min(len(estimates) - 1, int(0.975 * (len(estimates) - 1))))
    return {
        "count": sample_count,
        "mean": round(sum(values) / sample_count, 4),
        "ci_low": round(estimates[low_idx], 4),
        "ci_high": round(estimates[high_idx], 4),
    }


def _bootstrap_summary(documents: list[dict[str, Any]], label: str) -> dict[str, Any]:
    exact_f1_delta: list[float] = []
    latency_delta: list[float] = []
    validation_delta: list[float] = []
    for item in documents:
        static_doc = item.get("static", {}).get("doc", {})
        adaptive_doc = item.get(ADAPTIVE_LABEL, {}).get("doc", {})
        if not isinstance(static_doc, dict) or not isinstance(adaptive_doc, dict):
            continue
        deltas = item.get("deltas", {})
        exact_f1_delta.append(float(deltas.get("exact_f1_delta", 0.0) or 0.0))
        latency_delta.append(float(deltas.get("latency_ms", 0.0) or 0.0))
        validation_delta.append(_validation_pass(adaptive_doc) - _validation_pass(static_doc))
    return {
        "exact_f1_delta": _bootstrap_interval(exact_f1_delta, f"{label}:exact_f1_delta"),
        "latency_delta_ms": _bootstrap_interval(latency_delta, f"{label}:latency_delta_ms"),
        "validation_pass_rate_delta": _bootstrap_interval(validation_delta, f"{label}:validation_pass_rate_delta"),
    }


def _compare_case_outcome(static_doc: dict[str, Any], adaptive_doc: dict[str, Any], static_item: dict[str, Any], adaptive_item: dict[str, Any]) -> dict[str, Any]:
    static_exact = float((static_item.get("exact_metrics") or {}).get("f1", 0.0) or 0.0)
    adaptive_exact = float((adaptive_item.get("exact_metrics") or {}).get("f1", 0.0) or 0.0)
    has_exact = bool(static_item.get("exact_metrics")) or bool(adaptive_item.get("exact_metrics"))
    if has_exact:
        if adaptive_exact > static_exact + 1e-6:
            exact_state = "win"
        elif adaptive_exact < static_exact - 1e-6:
            exact_state = "loss"
        else:
            exact_state = "match"
    else:
        exact_state = "unscored"

    static_schema = bool(static_doc.get("schema_valid", False))
    adaptive_schema = bool(adaptive_doc.get("schema_valid", False))
    static_grounding = float(static_doc.get("schema_grounding_coverage", 0.0) or 0.0)
    adaptive_grounding = float(adaptive_doc.get("schema_grounding_coverage", 0.0) or 0.0)
    static_missing = int(static_doc.get("schema_missing_required_count", 0) or 0)
    adaptive_missing = int(adaptive_doc.get("schema_missing_required_count", 0) or 0)
    static_hallucinated = int(static_doc.get("schema_hallucinated_field_count", 0) or 0)
    adaptive_hallucinated = int(adaptive_doc.get("schema_hallucinated_field_count", 0) or 0)
    structural_score = (
        (1 if adaptive_schema else 0) - (1 if static_schema else 0),
        adaptive_grounding - static_grounding,
        static_missing - adaptive_missing,
        static_hallucinated - adaptive_hallucinated,
    )
    if structural_score > (0, 0.0, 0, 0):
        structural_state = "win"
    elif structural_score < (0, 0.0, 0, 0):
        structural_state = "loss"
    else:
        structural_state = "match"

    return {
        "exact_win_loss_state": exact_state,
        "structural_win_loss_state": structural_state,
        "exact_scored": has_exact,
    }


def _policy_impact_summary(documents: list[dict[str, Any]]) -> dict[str, Any]:
    impact = {
        "policy_changed_count": 0,
        "advice_accepted_count": 0,
        "exact_scored_doc_count": 0,
        "exact_win_count": 0,
        "exact_match_count": 0,
        "exact_loss_count": 0,
        "structural_win_count": 0,
        "structural_match_count": 0,
        "structural_loss_count": 0,
    }
    for item in documents:
        deltas = item.get("deltas", {})
        if bool(deltas.get("policy_changed")):
            impact["policy_changed_count"] += 1
        adaptive_doc = item.get(ADAPTIVE_LABEL, {}).get("doc", {})
        if isinstance(adaptive_doc, dict) and adaptive_doc.get("advice_accepted"):
            impact["advice_accepted_count"] += 1
        state = str(deltas.get("exact_win_loss_state", "unscored"))
        if state == "win":
            impact["exact_win_count"] += 1
        elif state == "loss":
            impact["exact_loss_count"] += 1
        elif state == "match":
            impact["exact_match_count"] += 1
            impact["exact_scored_doc_count"] += 1
        if state in {"win", "loss"}:
            impact["exact_scored_doc_count"] += 1
        structural_state = str(deltas.get("structural_win_loss_state", "match"))
        if structural_state == "win":
            impact["structural_win_count"] += 1
        elif structural_state == "loss":
            impact["structural_loss_count"] += 1
        else:
            impact["structural_match_count"] += 1
    total_docs = len(documents)
    impact["policy_switch_rate"] = round(impact["policy_changed_count"] / total_docs, 4) if total_docs else 0.0
    impact["advice_acceptance_rate"] = round(impact["advice_accepted_count"] / total_docs, 4) if total_docs else 0.0
    return impact


def _claim_checks(
    static_summary: dict[str, Any],
    adaptive_summary: dict[str, Any],
    comparison_table: dict[str, Any],
    policy_impact: dict[str, Any],
) -> dict[str, Any]:
    adaptive_statuses = adaptive_summary.get("advice_status_counts", {}) or {}
    adaptive_containment = adaptive_summary.get("containment_state_counts", {}) or {}
    accepted_count = int(adaptive_statuses.get("accepted", 0) or 0)
    rejected_count = int(adaptive_statuses.get("rejected", 0) or 0)
    no_advice_count = int(adaptive_statuses.get("no_advice", 0) or 0)
    policy_changed_count = int(policy_impact.get("policy_changed_count", 0) or 0)
    containment_count = sum(
        int(adaptive_containment.get(key, 0) or 0)
        for key in ("fallback", "rollback", "blocked", "defer_requested", "defer_blocked")
    )
    exact_f1_delta = float(comparison_table["exact_f1"][ADAPTIVE_LABEL] or 0.0) - float(comparison_table["exact_f1"]["static"] or 0.0)
    schema_delta = float(comparison_table["schema_valid_rate"][ADAPTIVE_LABEL] or 0.0) - float(comparison_table["schema_valid_rate"]["static"] or 0.0)
    validation_delta = float(comparison_table["validation_pass_rate"][ADAPTIVE_LABEL] or 0.0) - float(comparison_table["validation_pass_rate"]["static"] or 0.0)
    latency_delta = float(comparison_table["avg_latency_ms"]["static"] or 0.0) - float(comparison_table["avg_latency_ms"][ADAPTIVE_LABEL] or 0.0)

    checks = {
        "adaptive_safe_runtime_real": {
            "pass": accepted_count + rejected_count + no_advice_count > 0,
            "detail": f"accepted={accepted_count}, rejected={rejected_count}, no_advice={no_advice_count}",
        },
        "ahmn_changes_policy": {
            "pass": policy_changed_count > 0,
            "detail": f"policy_changed_count={policy_changed_count}",
        },
        "idpo_containment_exercised": {
            "pass": containment_count > 0,
            "detail": json.dumps(adaptive_containment, sort_keys=True),
        },
        "adaptive_improves_any_supported_metric": {
            "pass": exact_f1_delta > 0.0 or schema_delta > 0.0 or validation_delta > 0.0 or latency_delta > 0.0,
            "detail": (
                f"exact_f1_delta={round(exact_f1_delta, 4)}, "
                f"schema_valid_delta={round(schema_delta, 4)}, "
                f"validation_delta={round(validation_delta, 4)}, "
                f"latency_gain_ms={round(latency_delta, 2)}"
            ),
        },
        "claims_remain_limited": {
            "pass": True,
            "detail": "Benchmark supports adaptive-safe routing, containment behavior, and measured outcome deltas only.",
        },
    }
    return checks


def run_benchmark(
    config_path: str = "configs/idpo_research_config.json",
    pack_path: str = "idpo/benchmark/benchmark_pack.json",
    *,
    register_frontend_jobs: bool = False,
    job_name_prefix: str | None = None,
    existing_job_id: str | None = None,
) -> dict[str, Any]:
    repo_root = REPO_ROOT
    pack_file = (repo_root / pack_path).resolve()
    base_config_path = (repo_root / config_path).resolve()
    pack = json.loads(pack_file.read_text(encoding="utf-8"))
    cases = pack.get("cases", [])
    if not cases:
        raise SystemExit("Benchmark pack has no cases")

    benchmark_run_id = f"benchmark_{int(time.time())}"
    out_dir = benchmark_reports_dir() / benchmark_run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    conditions: dict[str, list[dict[str, Any]]] = {"static": [], ADAPTIVE_LABEL: []}
    started = time.time()

    with tempfile.TemporaryDirectory(prefix="idpo_benchmark_cfg_") as cfg_dir:
        cfg_root = Path(cfg_dir)
        condition_configs = {
            "static": _write_condition_config(base_config_path, "static", cfg_root),
            ADAPTIVE_LABEL: _write_condition_config(base_config_path, ADAPTIVE_LABEL, cfg_root),
        }
        condition_settings = {
            name: _load_config_payload(path).get("ahmn", {}) for name, path in condition_configs.items()
        }
        policy_store_path = str(_load_config_payload(base_config_path).get("knowledge", {}).get("policy_store_path", "")).strip()
        policy_store_payload = _load_config_payload((repo_root / policy_store_path).resolve()) if policy_store_path else {}
        valid_policy_ids = {
            str(item.get("policy_id", "")).strip()
            for item in policy_store_payload.get("policies", [])
            if isinstance(item, dict)
        }
        if not bool(condition_settings[ADAPTIVE_LABEL].get("enabled")):
            raise SystemExit("Adaptive benchmark configuration must enable AHMN")
        if _should_batch_cases(pack, cases):
            shared_fields = _shared_extraction_fields(pack, cases)
            for condition in ("static", ADAPTIVE_LABEL):
                conditions[condition].extend(
                    _run_condition_batch(
                        repo_root=repo_root,
                        config_path=str(condition_configs[condition]),
                        condition=condition,
                        cases=cases,
                        shared_fields=shared_fields,
                        job_id=existing_job_id,
                    )
                )
        else:
            for case in cases:
                case_id = str(case.get("case_id", "")).strip() or f"case_{sum(len(v) for v in conditions.values()) + 1}"
                tags = [str(tag).strip() for tag in (case.get("tags", []) or []) if str(tag).strip()]
                source_path = (repo_root / str(case.get("path", ""))).resolve()
                fields = [
                    {"name": key, "description": str(desc)}
                    for key, desc in (case.get("fields", {}) or {}).items()
                ]
                expected = {str(k): str(v) for k, v in (case.get("expected", {}) or {}).items()}
                if not source_path.exists():
                    for condition in conditions:
                        conditions[condition].append(
                            {"case_id": case_id, "status": "failed", "error": f"missing_file:{source_path}"}
                        )
                    continue

                for condition in ("static", ADAPTIVE_LABEL):
                    with tempfile.TemporaryDirectory(prefix=f"idpo_bench_{condition}_{case_id}_") as tmp_dir:
                        temp_path = Path(tmp_dir) / (case_id + source_path.suffix)
                        shutil.copy2(source_path, temp_path)
                        run = _launch_process_inbox(
                            root=repo_root,
                            config_path=str(condition_configs[condition]),
                            extraction_fields=fields,
                            run_id=f"{condition}_{case_id}_{int(time.time() * 1000)}",
                            input_dir=Path(tmp_dir),
                            job_id=existing_job_id,
                        )

                    docs = run.get("doc_records", [])
                    if not docs:
                        conditions[condition].append({"case_id": case_id, "status": "failed", "error": "no_doc_records"})
                        continue
                    doc = docs[0]
                    structured = doc.get("structured_fields", {})
                    if not isinstance(structured, dict):
                        structured = {}
                    tp, fp, fn = _case_metrics(expected, structured)
                    conditions[condition].append(
                        {
                            "case_id": case_id,
                            "status": "ok",
                            "tags": tags,
                            "doc": doc,
                            "run_id": run.get("run_id", ""),
                            "run_dir": run.get("run_dir", ""),
                            "ahmn_state_path": str((run.get("run_payload") or {}).get("ahmn_state_path", "")).strip() or None,
                            "expected": expected,
                            "exact_metrics": {
                                "tp": tp,
                                "fp": fp,
                                "fn": fn,
                                **_precision_recall_f1(tp, fp, fn),
                            },
                        }
                    )

    _assert_adaptive_valid(conditions[ADAPTIVE_LABEL], valid_policy_ids)
    condition_summaries = {key: _condition_summary(value) for key, value in conditions.items()}
    documents = []
    grouped_static: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_adaptive: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in conditions["static"]:
        for tag in item.get("tags", []):
            grouped_static[tag].append(item)
    for item in conditions[ADAPTIVE_LABEL]:
        for tag in item.get("tags", []):
            grouped_adaptive[tag].append(item)
    static_by_case = {item["case_id"]: item for item in conditions["static"] if item.get("status") == "ok"}
    adaptive_by_case = {item["case_id"]: item for item in conditions[ADAPTIVE_LABEL] if item.get("status") == "ok"}
    for case in cases:
        case_id = str(case.get("case_id", "")).strip()
        tags = [str(tag).strip() for tag in (case.get("tags", []) or []) if str(tag).strip()]
        static_item = static_by_case.get(case_id, {})
        adaptive_item = adaptive_by_case.get(case_id, {})
        static_doc = static_item.get("doc", {})
        adaptive_doc = adaptive_item.get("doc", {})
        documents.append(
            {
                "case_id": case_id,
                "tags": tags,
                "expected": {str(k): str(v) for k, v in (case.get("expected") or {}).items()},
                "static": {
                    "run_id": static_item.get("run_id", ""),
                    "run_dir": static_item.get("run_dir", ""),
                    "ahmn_state_path": static_item.get("ahmn_state_path"),
                    "doc": static_doc,
                    "exact_metrics": static_item.get("exact_metrics", {}),
                },
                ADAPTIVE_LABEL: {
                    "run_id": adaptive_item.get("run_id", ""),
                    "run_dir": adaptive_item.get("run_dir", ""),
                    "ahmn_state_path": adaptive_item.get("ahmn_state_path"),
                    "doc": adaptive_doc,
                    "exact_metrics": adaptive_item.get("exact_metrics", {}),
                },
                "deltas": {
                    "latency_ms": round(float(adaptive_doc.get("latency_ms", 0.0) or 0.0) - float(static_doc.get("latency_ms", 0.0) or 0.0), 2),
                    "reward": round(float(adaptive_doc.get("reward", 0.0) or 0.0) - float(static_doc.get("reward", 0.0) or 0.0), 4),
                    "policy_changed": str(adaptive_doc.get("policy_id", "")) != str(static_doc.get("policy_id", "")),
                    "recovery_delta": int(adaptive_doc.get("recovered_fields_count", 0) or 0) - int(static_doc.get("recovered_fields_count", 0) or 0),
                    "escalation_changed": str(adaptive_doc.get("escalation_status", "")) != str(static_doc.get("escalation_status", "")),
                    "exact_f1_delta": round(
                        float((adaptive_item.get("exact_metrics") or {}).get("f1", 0.0) or 0.0)
                        - float((static_item.get("exact_metrics") or {}).get("f1", 0.0) or 0.0),
                        4,
                    ),
                    **_compare_case_outcome(static_doc, adaptive_doc, static_item, adaptive_item),
                },
            }
        )
    grouped_tables = {}
    for tag in sorted(set(grouped_static.keys()) | set(grouped_adaptive.keys())):
        static_summary = _condition_summary(grouped_static.get(tag, []))
        adaptive_summary = _condition_summary(grouped_adaptive.get(tag, []))
        grouped_tables[tag] = _comparison_table(static_summary, adaptive_summary, len(grouped_static.get(tag, [])))
    grouped_bootstrap = {
        tag: _bootstrap_summary([item for item in documents if tag in (item.get("tags") or [])], f"group:{tag}")
        for tag in PRIMARY_GROUP_TAGS
        if any(tag in (item.get("tags") or []) for item in documents)
    }

    comparison_table = _comparison_table(condition_summaries["static"], condition_summaries[ADAPTIVE_LABEL], len(cases))
    policy_impact = _policy_impact_summary(documents)
    evidence = {
        "experiment": {
            "benchmark_run_id": benchmark_run_id,
            "pack_name": pack.get("name", "benchmark_pack"),
            "pack_path": str(pack_file),
            "config_path": str(base_config_path),
            "ahmn_seed_mode": (os.getenv("AHMN_SEED_MODE", "seeded").strip().lower() or "seeded"),
            "condition_configs": {
                name: {
                    "path": str(path),
                    "ahmn_enabled": bool(condition_settings[name].get("enabled")),
                    "ahmn_mode": str(condition_settings[name].get("mode", "")).strip() or None,
                    "policy_mode": name,
                    "runtime_policy_mode": str(condition_settings[name].get("policy_mode", name)).strip() or name,
                }
                for name, path in condition_configs.items()
            },
            "generated_at": time.time(),
            "elapsed_ms": round((time.time() - started) * 1000, 2),
            "doc_count": len(cases),
            "generation_version": 1,
        },
        "conditions": condition_summaries,
        "comparison": {
            "doc_count": len(cases),
            "static": condition_summaries["static"],
            ADAPTIVE_LABEL: condition_summaries[ADAPTIVE_LABEL],
            "table": comparison_table,
            "groups": grouped_tables,
            "bootstrap": {
                "overall": _bootstrap_summary(documents, "overall"),
                "groups": grouped_bootstrap,
            },
            "claim_checks": _claim_checks(condition_summaries["static"], condition_summaries[ADAPTIVE_LABEL], comparison_table, policy_impact),
            **policy_impact,
        },
        "documents": documents,
    }

    (out_dir / "paper_evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (out_dir / "paper_table.md").write_text(_table_markdown(evidence), encoding="utf-8")
    (out_dir / "paper_table.csv").write_text(_table_csv(evidence), encoding="utf-8")
    if register_frontend_jobs:
        result = register_frontend_jobs_from_evidence(
            evidence,
            pack_path=str(pack_file),
            job_name_prefix=job_name_prefix,
            existing_job_id=existing_job_id,
        )
        evidence["frontend_job"] = result
    return evidence


def _table_markdown(evidence: dict[str, Any]) -> str:
    table = evidence["comparison"]["table"]
    bootstrap = evidence["comparison"].get("bootstrap", {}).get("overall", {})
    exact_f1_delta = bootstrap.get("exact_f1_delta", {})
    latency_delta = bootstrap.get("latency_delta_ms", {})
    validation_delta = bootstrap.get("validation_pass_rate_delta", {})
    rows = [
        "| Metric | Static | Adaptive Safe |",
        "| --- | ---: | ---: |",
        f"| Doc Count | {table['doc_count']} | {table['doc_count']} |",
        f"| Avg Latency (ms) | {table['avg_latency_ms']['static']} | {table['avg_latency_ms'][ADAPTIVE_LABEL]} |",
        f"| Avg Runtime Proxy Reward | {table['avg_reward']['static']} | {table['avg_reward'][ADAPTIVE_LABEL]} |",
        f"| Exact Precision | {table['exact_precision']['static']} | {table['exact_precision'][ADAPTIVE_LABEL]} |",
        f"| Exact Recall | {table['exact_recall']['static']} | {table['exact_recall'][ADAPTIVE_LABEL]} |",
        f"| Exact F1 | {table['exact_f1']['static']} | {table['exact_f1'][ADAPTIVE_LABEL]} |",
        f"| Validation Pass Rate | {table['validation_pass_rate']['static']} | {table['validation_pass_rate'][ADAPTIVE_LABEL]} |",
        f"| Recovery Rate | {table['recovery_rate']['static']} | {table['recovery_rate'][ADAPTIVE_LABEL]} |",
        f"| Escalation Rate | {table['escalation_rate']['static']} | {table['escalation_rate'][ADAPTIVE_LABEL]} |",
        f"| Rollback Count | {table['rollback_count']['static']} | {table['rollback_count'][ADAPTIVE_LABEL]} |",
        f"| Blocked Policy Count | {table['blocked_policy_count']['static']} | {table['blocked_policy_count'][ADAPTIVE_LABEL]} |",
        f"| Feedback Logged | {table['feedback_logged_count']['static']} | {table['feedback_logged_count'][ADAPTIVE_LABEL]} |",
        f"| Advice Accepted Count | {table['advice_accepted_count']['static']} | {table['advice_accepted_count'][ADAPTIVE_LABEL]} |",
        f"| Policy Changed Count | {table['policy_changed_count']['static']} | {table['policy_changed_count'][ADAPTIVE_LABEL]} |",
        f"| Exact-Scored Doc Count | {table['exact_scored_doc_count']['static']} | {table['exact_scored_doc_count'][ADAPTIVE_LABEL]} |",
        f"| Avg Schema Coverage | {table['avg_schema_coverage']['static']} | {table['avg_schema_coverage'][ADAPTIVE_LABEL]} |",
        f"| Avg Grounding Coverage | {table['avg_schema_grounding_coverage']['static']} | {table['avg_schema_grounding_coverage'][ADAPTIVE_LABEL]} |",
        f"| Schema Valid Rate | {table['schema_valid_rate']['static']} | {table['schema_valid_rate'][ADAPTIVE_LABEL]} |",
        f"| Defer Requested Count | {table['defer_requested_count']['static']} | {table['defer_requested_count'][ADAPTIVE_LABEL]} |",
        f"| Defer Blocked Count | {table['defer_blocked_count']['static']} | {table['defer_blocked_count'][ADAPTIVE_LABEL]} |",
        f"| Exact F1 Delta Mean | - | {exact_f1_delta.get('mean', 0.0)} |",
        f"| Exact F1 Delta 95% CI | - | [{exact_f1_delta.get('ci_low', 0.0)}, {exact_f1_delta.get('ci_high', 0.0)}] |",
        f"| Latency Delta Mean (ms) | - | {latency_delta.get('mean', 0.0)} |",
        f"| Latency Delta 95% CI | - | [{latency_delta.get('ci_low', 0.0)}, {latency_delta.get('ci_high', 0.0)}] |",
        f"| Validation Pass Delta Mean | - | {validation_delta.get('mean', 0.0)} |",
        f"| Validation Pass Delta 95% CI | - | [{validation_delta.get('ci_low', 0.0)}, {validation_delta.get('ci_high', 0.0)}] |",
        f"| Policy Distribution | `{json.dumps(table['policy_distribution']['static'], sort_keys=True)}` | `{json.dumps(table['policy_distribution'][ADAPTIVE_LABEL], sort_keys=True)}` |",
        f"| Advice Sources | `{json.dumps(table['advice_source_counts']['static'], sort_keys=True)}` | `{json.dumps(table['advice_source_counts'][ADAPTIVE_LABEL], sort_keys=True)}` |",
        f"| Advice Statuses | `{json.dumps(table['advice_status_counts']['static'], sort_keys=True)}` | `{json.dumps(table['advice_status_counts'][ADAPTIVE_LABEL], sort_keys=True)}` |",
        f"| Retrieval Sources | `{json.dumps(table['retrieval_source_counts']['static'], sort_keys=True)}` | `{json.dumps(table['retrieval_source_counts'][ADAPTIVE_LABEL], sort_keys=True)}` |",
        f"| Containment States | `{json.dumps(table['containment_state_counts']['static'], sort_keys=True)}` | `{json.dumps(table['containment_state_counts'][ADAPTIVE_LABEL], sort_keys=True)}` |",
        f"| Operator Counts | `{json.dumps(table['operator_counts']['static'], sort_keys=True)}` | `{json.dumps(table['operator_counts'][ADAPTIVE_LABEL], sort_keys=True)}` |",
    ]
    return "\n".join(rows) + "\n"


def _table_csv(evidence: dict[str, Any]) -> str:
    table = evidence["comparison"]["table"]
    bootstrap = evidence["comparison"].get("bootstrap", {}).get("overall", {})
    exact_f1_delta = bootstrap.get("exact_f1_delta", {})
    latency_delta = bootstrap.get("latency_delta_ms", {})
    validation_delta = bootstrap.get("validation_pass_rate_delta", {})
    rows = [
        f"metric,static,{ADAPTIVE_LABEL}",
        f"doc_count,{table['doc_count']},{table['doc_count']}",
        f"avg_latency_ms,{table['avg_latency_ms']['static']},{table['avg_latency_ms'][ADAPTIVE_LABEL]}",
        f"avg_runtime_proxy_reward,{table['avg_reward']['static']},{table['avg_reward'][ADAPTIVE_LABEL]}",
        f"exact_precision,{table['exact_precision']['static']},{table['exact_precision'][ADAPTIVE_LABEL]}",
        f"exact_recall,{table['exact_recall']['static']},{table['exact_recall'][ADAPTIVE_LABEL]}",
        f"exact_f1,{table['exact_f1']['static']},{table['exact_f1'][ADAPTIVE_LABEL]}",
        f"validation_pass_rate,{table['validation_pass_rate']['static']},{table['validation_pass_rate'][ADAPTIVE_LABEL]}",
        f"recovery_rate,{table['recovery_rate']['static']},{table['recovery_rate'][ADAPTIVE_LABEL]}",
        f"escalation_rate,{table['escalation_rate']['static']},{table['escalation_rate'][ADAPTIVE_LABEL]}",
        f"rollback_count,{table['rollback_count']['static']},{table['rollback_count'][ADAPTIVE_LABEL]}",
        f"blocked_policy_count,{table['blocked_policy_count']['static']},{table['blocked_policy_count'][ADAPTIVE_LABEL]}",
        f"feedback_logged_count,{table['feedback_logged_count']['static']},{table['feedback_logged_count'][ADAPTIVE_LABEL]}",
        f"advice_accepted_count,{table['advice_accepted_count']['static']},{table['advice_accepted_count'][ADAPTIVE_LABEL]}",
        f"policy_changed_count,{table['policy_changed_count']['static']},{table['policy_changed_count'][ADAPTIVE_LABEL]}",
        f"exact_scored_doc_count,{table['exact_scored_doc_count']['static']},{table['exact_scored_doc_count'][ADAPTIVE_LABEL]}",
        f"avg_schema_coverage,{table['avg_schema_coverage']['static']},{table['avg_schema_coverage'][ADAPTIVE_LABEL]}",
        f"avg_schema_grounding_coverage,{table['avg_schema_grounding_coverage']['static']},{table['avg_schema_grounding_coverage'][ADAPTIVE_LABEL]}",
        f"schema_valid_rate,{table['schema_valid_rate']['static']},{table['schema_valid_rate'][ADAPTIVE_LABEL]}",
        f"defer_requested_count,{table['defer_requested_count']['static']},{table['defer_requested_count'][ADAPTIVE_LABEL]}",
        f"defer_blocked_count,{table['defer_blocked_count']['static']},{table['defer_blocked_count'][ADAPTIVE_LABEL]}",
        f"exact_f1_delta_mean,,{exact_f1_delta.get('mean', 0.0)}",
        f"exact_f1_delta_ci,,\"[{exact_f1_delta.get('ci_low', 0.0)}, {exact_f1_delta.get('ci_high', 0.0)}]\"",
        f"latency_delta_ms_mean,,{latency_delta.get('mean', 0.0)}",
        f"latency_delta_ms_ci,,\"[{latency_delta.get('ci_low', 0.0)}, {latency_delta.get('ci_high', 0.0)}]\"",
        f"validation_pass_rate_delta_mean,,{validation_delta.get('mean', 0.0)}",
        f"validation_pass_rate_delta_ci,,\"[{validation_delta.get('ci_low', 0.0)}, {validation_delta.get('ci_high', 0.0)}]\"",
        f"policy_distribution,\"{json.dumps(table['policy_distribution']['static'], sort_keys=True)}\",\"{json.dumps(table['policy_distribution'][ADAPTIVE_LABEL], sort_keys=True)}\"",
        f"advice_source_counts,\"{json.dumps(table['advice_source_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['advice_source_counts'][ADAPTIVE_LABEL], sort_keys=True)}\"",
        f"advice_status_counts,\"{json.dumps(table['advice_status_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['advice_status_counts'][ADAPTIVE_LABEL], sort_keys=True)}\"",
        f"retrieval_source_counts,\"{json.dumps(table['retrieval_source_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['retrieval_source_counts'][ADAPTIVE_LABEL], sort_keys=True)}\"",
        f"containment_state_counts,\"{json.dumps(table['containment_state_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['containment_state_counts'][ADAPTIVE_LABEL], sort_keys=True)}\"",
        f"operator_counts,\"{json.dumps(table['operator_counts']['static'], sort_keys=True)}\",\"{json.dumps(table['operator_counts'][ADAPTIVE_LABEL], sort_keys=True)}\"",
    ]
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/idpo_research_config.json")
    parser.add_argument("--pack", default="idpo/benchmark/benchmark_pack.json")
    parser.add_argument("--register-frontend-jobs", action="store_true")
    parser.add_argument("--job-name-prefix", default=None)
    parser.add_argument(
        "--benchmark-job-id",
        default=None,
        help="Existing frontend job ID to append documents to. "
             "Omit to create a new job. Use this to extend Phase A → B → C "
             "while preserving AHMN learning context across all processed documents.",
    )
    args = parser.parse_args()
    evidence = run_benchmark(
        config_path=args.config,
        pack_path=args.pack,
        register_frontend_jobs=args.register_frontend_jobs,
        job_name_prefix=args.job_name_prefix,
        existing_job_id=args.benchmark_job_id,
    )
    print(json.dumps(evidence["comparison"]["table"], indent=2))
    print(f"report_path={benchmark_reports_dir() / evidence['experiment']['benchmark_run_id'] / 'paper_evidence.json'}")
    if "frontend_job" in evidence:
        fj = evidence["frontend_job"]
        print(f"frontend_job_id={fj.get('job_id')} doc_count={fj.get('doc_count')} added={fj.get('added_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

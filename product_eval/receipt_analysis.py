"""Summarize product receipts after a source-verified evaluation gate.

The summary contains only counts and resource measurements. It never copies
source text, paths, OCR output, or provider credentials from sidecars.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError

_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_RENDERERS = {"pdfium", "poppler", "none", "poppler_direct", "pillow_direct"}


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContractError(f"{path}: unreadable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{path}: expected JSON object")
    return value


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ContractError(f"{path}: unreadable manifest: {exc}") from exc
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ContractError(f"{path}:{number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ContractError(f"{path}:{number}: expected JSON object")
        rows.append(row)
    return rows


def _nonnegative_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def summarize_receipts(report_dir: Path, data_dir: Path) -> dict[str, Any]:
    """Check sidecar/manifest joins and count observed provenance and resources.

    Call this only after ``run_gate`` has verified source bytes and candidate/gold
    joins. These counts add transparency; they are not an accuracy scorer.
    """
    provenance = _read_object(report_dir / "provenance.json")
    execution = _read_object(report_dir / "execution-report.json")
    run_ids = provenance.get("run_ids")
    if not isinstance(run_ids, list) or not run_ids or any(
        not isinstance(run_id, str) or not _SAFE_ID.fullmatch(run_id) for run_id in run_ids
    ) or len(run_ids) != len(set(run_ids)):
        raise ContractError("gate provenance contains invalid run IDs")
    if set(run_ids) != set(execution.get("run_ids", [])):
        raise ContractError("gate provenance and execution report have different run IDs")

    statuses: Counter[str] = Counter()
    engines: Counter[str] = Counter()
    renderers: Counter[str] = Counter()
    fallbacks: Counter[str] = Counter()
    retry_paths: Counter[str] = Counter()
    missing = Counter()
    coverage = Counter()
    costs = Counter()
    document_count = page_count = pdf_page_count = pdf_ocr_page_count = 0
    total_doc_cpu_ms = total_run_cpu_ms = 0.0
    rss_observed_max_bytes: int | None = None
    model_calls = sdk_attempts = 0

    for run_id in run_ids:
        run_dir = data_dir / "product_runs" / run_id
        run = _read_object(run_dir / "run.json")
        if run.get("run_id") != run_id or run.get("model_configured") is not False:
            raise ContractError(f"{run_id}: unexpected run identity or configured model")
        run_resource = run.get("resource_usage")
        if isinstance(run_resource, dict) and _nonnegative_number(run_resource.get("worker_process_cpu_ms")):
            coverage["runs_with_cpu"] += 1
            total_run_cpu_ms += run_resource["worker_process_cpu_ms"]
        else:
            missing["run_cpu"] += 1
        for key in ("worker_rss_start_bytes", "worker_rss_end_bytes"):
            value = run_resource.get(key) if isinstance(run_resource, dict) else None
            if _nonnegative_int(value):
                coverage[f"runs_with_{key}"] += 1
                rss_observed_max_bytes = max(rss_observed_max_bytes or 0, value)
            else:
                missing[f"run_{key}"] += 1

        rows = _read_manifest(run_dir / "manifest.jsonl")
        if run.get("doc_count") != len(rows):
            raise ContractError(f"{run_id}: run document count differs from manifest")
        for receipt in rows:
            doc_id = receipt.get("doc_id")
            if not isinstance(doc_id, str) or not _SAFE_ID.fullmatch(doc_id):
                raise ContractError(f"{run_id}: invalid document ID in manifest")
            result = _read_object(run_dir / "docs" / doc_id / "result.json")
            if result.get("run_id") != run_id or result.get("candidate", {}).get("doc_id") != doc_id:
                raise ContractError(f"{run_id}/{doc_id}: sidecar identity differs from manifest")
            status = receipt.get("document_status")
            if status != result.get("document_status") or status != result["candidate"].get("document_status"):
                raise ContractError(f"{run_id}/{doc_id}: sidecar status differs from manifest")
            pages = result.get("ocr_pages", [])
            if not isinstance(pages, list) or len(pages) != receipt.get("page_count"):
                raise ContractError(f"{run_id}/{doc_id}: OCR page count differs from manifest")
            if receipt.get("model_call_count") != len(result.get("model_calls", [])):
                raise ContractError(f"{run_id}/{doc_id}: model call count differs from sidecar")
            document_count += 1
            statuses[str(status)] += 1
            model_calls += receipt["model_call_count"]
            if _nonnegative_int(receipt.get("model_sdk_attempt_count")):
                sdk_attempts += receipt["model_sdk_attempt_count"]
                coverage["documents_with_sdk_attempt_count"] += 1
            is_pdf = str(receipt.get("source_file", "")).lower().endswith(".pdf")
            doc_resource = receipt.get("resource_usage")
            if isinstance(doc_resource, dict) and _nonnegative_number(doc_resource.get("worker_process_cpu_ms")):
                coverage["documents_with_cpu"] += 1
                total_doc_cpu_ms += doc_resource["worker_process_cpu_ms"]
            else:
                missing["document_cpu"] += 1
            for key in ("worker_rss_before_bytes", "worker_rss_after_bytes"):
                value = doc_resource.get(key) if isinstance(doc_resource, dict) else None
                if _nonnegative_int(value):
                    coverage[f"documents_with_{key}"] += 1
                    rss_observed_max_bytes = max(rss_observed_max_bytes or 0, value)
                else:
                    missing[f"document_{key}"] += 1
            for key in ("api_cost_usd", "compute_cost_usd", "total_cost_usd"):
                if _nonnegative_number(result.get(key)):
                    costs[f"documents_with_{key}"] += 1
                else:
                    costs[f"documents_unpriced_{key}"] += 1

            for page in pages:
                if not isinstance(page, dict):
                    raise ContractError(f"{run_id}/{doc_id}: invalid OCR page")
                page_count += 1
                engine = page.get("engine")
                engines[str(engine) if engine is not None else "missing"] += 1
                if page.get("retry_path"):
                    retry_paths[str(page["retry_path"])] += 1
                if not is_pdf:
                    continue
                pdf_page_count += 1
                if not _nonnegative_int(page.get("pdf_page_index")):
                    missing["pdf_page_index"] += 1
                if engine == "native_text":
                    continue
                pdf_ocr_page_count += 1
                renderer = page.get("pdf_renderer")
                if renderer in _RENDERERS:
                    renderers[renderer] += 1
                else:
                    missing["pdf_ocr_renderer"] += 1
                reason = page.get("pdf_renderer_fallback_reason")
                if isinstance(reason, str) and reason:
                    fallbacks[reason] += 1
                if renderer not in (None, "none"):
                    if not _nonnegative_int(page.get("pdf_rendered_dpi")):
                        missing["rendered_dpi"] += 1
                    size = page.get("pdf_render_size_px")
                    if not (isinstance(size, list) and len(size) == 2 and all(
                        type(value) is int and value > 0 for value in size
                    )):
                        missing["render_size_px"] += 1

    if document_count != execution.get("documents") or statuses != Counter(execution.get("status_counts", {})):
        raise ContractError("receipt totals differ from source-verified execution report")
    return {
        "gate_id": provenance.get("gate_id"),
        "git_commit": provenance.get("git_commit"),
        "runs": len(run_ids),
        "documents": document_count,
        "distinct_sources_verified": execution.get("distinct_sources"),
        "status_counts": dict(sorted(statuses.items())),
        "pages": page_count,
        "pdf_pages": pdf_page_count,
        "pdf_ocr_pages": pdf_ocr_page_count,
        "ocr_engines": dict(sorted(engines.items())),
        "pdf_ocr_renderers": dict(sorted(renderers.items())),
        "pdf_renderer_fallback_reasons": dict(sorted(fallbacks.items())),
        "ocr_retry_paths": dict(sorted(retry_paths.items())),
        "missing_provenance_or_resource": dict(sorted(missing.items())),
        "resource_coverage": dict(sorted(coverage.items())),
        "sum_document_worker_process_cpu_ms": round(total_doc_cpu_ms, 3),
        "sum_run_worker_process_cpu_ms": round(total_run_cpu_ms, 3),
        "maximum_observed_worker_rss_boundary_bytes": rss_observed_max_bytes,
        "resource_scope": "worker process only; OCR subprocess CPU/RSS and peaks are excluded",
        "model_call_count": model_calls,
        "known_model_sdk_attempt_count": sdk_attempts,
        "cost_coverage": dict(sorted(costs.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    summary = summarize_receipts(args.report_dir, args.data_dir)
    content = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(content, end="")
    else:
        args.output.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()

"""Inbox-driven runtime entrypoint for the canonical IDPO processing path.

This module should stay focused on:

- resolving input files
- creating the run layout
- invoking the pipeline
- persisting stable run and per-document outputs

It should not become the home for unrelated product features or legacy
integration behavior.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from idpo.agents.intake import IntakeAgent
from idpo.core.config import PipelineConfig, load_config
from idpo.core.preflight import run_preflight
from idpo.core.storage import failed_dir as storage_failed_dir
from idpo.core.storage import inbox_dir as storage_inbox_dir
from idpo.core.storage import processed_dir as storage_processed_dir
from idpo.core.storage import runs_root as storage_runs_root
from idpo.pipeline.doc_artifacts import build_run_provenance_index, prepare_doc_input, write_doc_outputs
from idpo.pipeline.doc_records import create_doc_record, normalize_key
from idpo.pipeline.job_context import write_field_context
from idpo.pipeline.orchestrator import Pipeline
from idpo.pipeline.run_reports import (
    aggregate_reward_metrics,
    entity_records,
    write_decision_chain_summary,
    write_docs_excel,
    write_entities_excel,
    write_run_excel,
)
from idpo.pipeline.telemetry import persist_run_telemetry

SUPPORTED_INPUT_EXTS = {".json", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
logger = logging.getLogger("idpo.inbox")

def process_inbox(
    root: Path,
    config_path: str | None = None,
    extraction_fields: list[dict[str, str]] | None = None,
    run_id: str | None = None,
    file_paths: list[str] | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    preflight_warnings = run_preflight(config)

    _ = Path(root)
    inbox_dir = storage_inbox_dir()
    processed_dir = storage_processed_dir()
    failed_dir = storage_failed_dir()
    runs_dir = storage_runs_root()
    inbox_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    if file_paths:
        files = [Path(p) for p in file_paths if Path(p).exists() and Path(p).suffix.lower() in SUPPORTED_INPUT_EXTS]
    else:
        files = [
            path for path in inbox_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_EXTS
        ]
    if not files:
        raise ValueError(f"No supported files found in {inbox_dir}. Drop files there and retry.")

    resolved_run_id = run_id or uuid.uuid4().hex
    job_id = os.getenv("IDPO_JOB_ID", "").strip() or None
    run_dir = runs_dir / resolved_run_id
    docs_dir = run_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    expected_fields = _normalize_fields(extraction_fields or [])
    if expected_fields:
        _write_fields_schema(run_dir, expected_fields)
        _apply_requested_fields(config, expected_fields)

    events_path = run_dir / "events.jsonl"
    errors_path = run_dir / "errors.jsonl"
    start_time = time.time()
    run_payload = {
        "run_id": resolved_run_id,
        "started_at": start_time,
        "config_path": config_path,
        "policy_store_path": config.knowledge.policy_store_path,
        "execution_surface": os.getenv("IDPO_EXECUTION_SURFACE", "cli_process_inbox"),
        "job_id": job_id,
        "preflight_warnings": " | ".join(preflight_warnings),
    }
    (run_dir / "run.json").write_text(json.dumps(run_payload, indent=2), encoding="utf-8")

    intake = IntakeAgent()
    failed: list[dict[str, str]] = []
    doc_records: list[dict[str, object]] = []
    ingested_items: list[dict[str, Any]] = []
    ingested_files: list[Path] = []

    for file_path in files:
        try:
            docs = intake.ingest(str(file_path))
            if not docs:
                raise ValueError("No documents were parsed from the input")
            for doc in docs:
                doc.metadata["run_id"] = resolved_run_id
                if job_id:
                    doc.metadata["job_id"] = job_id
                doc_dir = docs_dir / _safe_path_component(doc.doc_id)
                prepare_doc_input(doc, file_path, doc_dir)
                ingested_items.append({"doc": doc, "doc_dir": doc_dir, "file_path": file_path})
            ingested_files.append(file_path)
        except Exception as exc:
            error_msg = str(exc)
            failed.append({"file": file_path.name, "error": error_msg})
            errors_path.parent.mkdir(parents=True, exist_ok=True)
            with errors_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"file": str(file_path), "error": error_msg}) + "\n")
            try:
                shutil.move(str(file_path), str(failed_dir / file_path.name))
            except Exception:
                pass

    if not ingested_items:
        raise ValueError("No valid documents were ingested for processing.")

    pipeline = Pipeline(config=config, run_dir=str(run_dir), run_id=resolved_run_id)
    docs_batch = [item["doc"] for item in ingested_items]
    results: list[Any] = []
    failed_doc_ids: set[str] = set()

    try:
        results = pipeline.process_documents(docs_batch)
    except Exception as exc:
        # Preserve progress by falling back to per-document execution in the same pipeline run.
        logger.warning("Batch processing failed, falling back to per-document mode: %s", exc)
        preflight_warnings.append(f"Batch mode fallback triggered: {str(exc)[:180]}")
        for item in ingested_items:
            doc = item["doc"]
            try:
                results.append(pipeline.process_document(doc))
            except Exception as inner_exc:
                failed_doc_ids.add(str(doc.doc_id))
                error_msg = str(inner_exc)
                failed.append({"file": Path(item["file_path"]).name, "error": f"{doc.doc_id}: {error_msg}"})
                with errors_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {"file": str(item["file_path"]), "doc_id": doc.doc_id, "error": error_msg}
                        )
                        + "\n"
                    )

    if _results_have_chunks(results):
        pipeline.build_index(results, directory=str(run_dir / "embeddings" / "index"))

    # Build provenance index once so write_doc_outputs doesn't rescan events.jsonl
    # for every document (was O(N*M) — N docs times M total events).
    run_prov_index = build_run_provenance_index(run_dir)
    results_by_doc_id = {str(result.doc_id): result for result in results}
    for item in ingested_items:
        doc = item["doc"]
        doc_dir = item["doc_dir"]
        result = results_by_doc_id.get(str(doc.doc_id))
        if not result:
            failed_doc_ids.add(str(doc.doc_id))
            continue
        write_doc_outputs(run_dir, doc, result, doc_dir, events_path, run_provenance_index=run_prov_index)
        if job_id:
            write_field_context(
                job_id=job_id,
                doc_id=doc.doc_id,
                policy_id=str(getattr(result, "policy_id", "") or ""),
                field_confidence=getattr(result, "field_confidence", {}) or {},
                validation_issues=getattr(result, "validation_issues", []) or [],
                vendor_cluster=str(getattr(result, "vendor_cluster", "") or ""),
                semantic_doc_type=str(getattr(result, "semantic_doc_type", "unknown") or "unknown"),
            )
        doc_records.append(create_doc_record(result, doc_dir, expected_fields, doc))

    for file_path in ingested_files:
        if not file_path.exists():
            continue
        try:
            shutil.move(str(file_path), str(processed_dir / file_path.name))
        except Exception:
            pass

    reward_metrics = aggregate_reward_metrics(doc_records)
    metrics_payload = {
        "file_count": len(files),
        "doc_count": len(ingested_items),
        "processed_doc_count": len(doc_records),
        "failed_count": len(failed),
        "failed_doc_count": len(failed_doc_ids),
        "ended_at": time.time(),
        "duration_ms": (time.time() - start_time) * 1000,
        **reward_metrics,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
    write_decision_chain_summary(run_dir, doc_records)
    write_docs_excel(run_dir, doc_records)
    write_entities_excel(run_dir, doc_records, expected_fields)
    write_run_excel(run_dir, run_payload, metrics_payload)
    telemetry_status = persist_run_telemetry(run_dir, resolved_run_id, doc_records, metrics_payload, preflight_warnings)
    if telemetry_status and telemetry_status.get("warning"):
        preflight_warnings.append(str(telemetry_status["warning"]))
    run_payload["telemetry"] = telemetry_status
    ahmn_state = _write_ahmn_state_snapshot(
        run_dir=run_dir,
        config=config,
        run_id=resolved_run_id,
        job_id=job_id,
    )
    if ahmn_state:
        run_payload.update(ahmn_state)
    (run_dir / "run.json").write_text(json.dumps(run_payload, indent=2), encoding="utf-8")

    return {
        "run_id": resolved_run_id,
        "run_dir": str(run_dir),
        "doc_records": doc_records,
        "entity_records": entity_records(doc_records, expected_fields),
        "metrics": metrics_payload,
        "run_payload": run_payload,
        "preflight_warnings": preflight_warnings,
        "failed": failed,
    }

def _apply_requested_fields(config: PipelineConfig, fields: list[dict[str, str]]) -> None:
    config.structuring.requested_fields = [field["key"] for field in fields if field.get("key")]
    config.structuring.field_descriptions = {
        field["key"]: field.get("description", "")
        for field in fields
        if field.get("key") and field.get("description")
    }
    config.llm.use_extraction = True

def _normalize_fields(fields: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = []
    for field in fields:
        name = str(field.get("name", "")).strip()
        description = str(field.get("description", "")).strip()
        if not name:
            continue
        key = normalize_key(name)
        normalized.append({"name": name, "key": key, "description": description})
    return normalized

def _write_fields_schema(run_dir: Path, fields: list[dict[str, str]]) -> None:
    schema = {"fields": fields}
    (run_dir / "fields.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")

def _safe_path_component(raw: object) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(raw or "")).strip("._-")
    return value[:120] if value else uuid.uuid4().hex


def _results_have_chunks(results: list[Any]) -> bool:
    return any(bool(getattr(result, "chunks", None)) for result in results)


def _write_ahmn_state_snapshot(
    *,
    run_dir: Path,
    config: PipelineConfig,
    run_id: str,
    job_id: str | None,
) -> dict[str, object]:
    if not config.ahmn.enabled:
        return {}
    direct_import = (config.ahmn.direct_import or "").strip()
    if not direct_import:
        return {}
    try:
        module_path, _ = direct_import.rsplit(":", 1)
        module = importlib.import_module(module_path)
    except Exception:
        return {}
    snapshot_fn = getattr(module, "get_state_snapshot", None)
    if not callable(snapshot_fn):
        return {}
    resolve_scope = getattr(module, "resolve_scope_key", None)
    try:
        scope_key = (
            resolve_scope(job_id=job_id, run_id=run_id)
            if callable(resolve_scope)
            else (job_id or run_id)
        )
        snapshot = snapshot_fn(scope_key) if scope_key else snapshot_fn()
    except Exception:
        return {}
    if not isinstance(snapshot, dict):
        return {}
    snapshot_path = run_dir / "ahmn_state.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return {
        "ahmn_state_path": str(snapshot_path),
        "ahmn_scope_key": str(snapshot.get("scope_key", scope_key or "")),
    }

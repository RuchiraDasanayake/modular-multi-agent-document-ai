"""Optional run telemetry persistence for inbox processing.

This module isolates the database write path from ``inbox.py`` so telemetry can
stay optional and operationally separate from the canonical runtime flow.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from idpo.pipeline.doc_artifacts import fallback_path


def persist_run_telemetry(
    run_dir: Path,
    run_id: str,
    doc_records: list[dict[str, object]],
    metrics_payload: dict[str, object],
    preflight_warnings: list[str],
) -> dict[str, object]:
    dsn = (os.getenv("POSTGRES_URI") or "").strip()
    if not dsn:
        return {"enabled": False, "status": "skipped", "reason": "POSTGRES_URI_not_set"}
    try:
        import psycopg
    except Exception as exc:
        return {"enabled": False, "status": "skipped", "warning": f"psycopg_unavailable: {exc}"}

    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS idpo_run_telemetry (
                        run_id TEXT PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        doc_count INTEGER NOT NULL,
                        processed_doc_count INTEGER NOT NULL,
                        failed_count INTEGER NOT NULL,
                        duration_ms DOUBLE PRECISION NOT NULL,
                        preflight_warnings TEXT NOT NULL,
                        metrics_json JSONB NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS idpo_doc_telemetry (
                        run_id TEXT NOT NULL,
                        doc_id TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        model_mode TEXT,
                        model_used TEXT,
                        ocr_confidence DOUBLE PRECISION,
                        cloud_total_tokens INTEGER,
                        cloud_estimated_cost_usd DOUBLE PRECISION,
                        fallback_path TEXT,
                        extraction_success BOOLEAN,
                        unresolved_fields TEXT[] NOT NULL DEFAULT '{}',
                        latency_ms DOUBLE PRECISION,
                        llm_diag_json JSONB NOT NULL,
                        PRIMARY KEY (run_id, doc_id)
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO idpo_run_telemetry
                        (run_id, doc_count, processed_doc_count, failed_count, duration_ms, preflight_warnings, metrics_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (run_id) DO UPDATE SET
                        doc_count = EXCLUDED.doc_count,
                        processed_doc_count = EXCLUDED.processed_doc_count,
                        failed_count = EXCLUDED.failed_count,
                        duration_ms = EXCLUDED.duration_ms,
                        preflight_warnings = EXCLUDED.preflight_warnings,
                        metrics_json = EXCLUDED.metrics_json
                    """,
                    (
                        run_id,
                        int(metrics_payload.get("doc_count", 0) or 0),
                        int(metrics_payload.get("processed_doc_count", 0) or 0),
                        int(metrics_payload.get("failed_count", 0) or 0),
                        float(metrics_payload.get("duration_ms", 0.0) or 0.0),
                        " | ".join(preflight_warnings),
                        json.dumps(metrics_payload),
                    ),
                )

                persisted_docs = 0
                for record in doc_records:
                    doc_id = str(record.get("doc_id", "")).strip()
                    if not doc_id:
                        continue
                    llm_diag = record.get("llm_diagnostics", {})
                    if not isinstance(llm_diag, dict):
                        llm_diag = {}
                    cloud_usage = llm_diag.get("cloud_usage", {})
                    if not isinstance(cloud_usage, dict):
                        cloud_usage = {}

                    ocr_conf = _read_ocr_confidence(record.get("ocr_path"))
                    llm_fallback_path = fallback_path(llm_diag)
                    missing_fields = record.get("missing_fields", [])
                    if not isinstance(missing_fields, list):
                        missing_fields = []
                    extraction_success = bool(record.get("entity_count", 0)) and not bool(missing_fields)

                    cur.execute(
                        """
                        INSERT INTO idpo_doc_telemetry
                            (run_id, doc_id, model_mode, model_used, ocr_confidence, cloud_total_tokens,
                             cloud_estimated_cost_usd, fallback_path, extraction_success, unresolved_fields,
                             latency_ms, llm_diag_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (run_id, doc_id) DO UPDATE SET
                            model_mode = EXCLUDED.model_mode,
                            model_used = EXCLUDED.model_used,
                            ocr_confidence = EXCLUDED.ocr_confidence,
                            cloud_total_tokens = EXCLUDED.cloud_total_tokens,
                            cloud_estimated_cost_usd = EXCLUDED.cloud_estimated_cost_usd,
                            fallback_path = EXCLUDED.fallback_path,
                            extraction_success = EXCLUDED.extraction_success,
                            unresolved_fields = EXCLUDED.unresolved_fields,
                            latency_ms = EXCLUDED.latency_ms,
                            llm_diag_json = EXCLUDED.llm_diag_json
                        """,
                        (
                            run_id,
                            doc_id,
                            str(record.get("model_mode", "") or ""),
                            str(record.get("model_used", "") or ""),
                            ocr_conf,
                            int(cloud_usage.get("total_tokens", 0) or 0),
                            float(cloud_usage.get("estimated_cost_usd", 0.0) or 0.0),
                            llm_fallback_path,
                            extraction_success,
                            [str(item) for item in missing_fields],
                            float(record.get("latency_ms", 0.0) or 0.0),
                            json.dumps(llm_diag),
                        ),
                    )
                    persisted_docs += 1

        return {"enabled": True, "status": "ok", "persisted_docs": persisted_docs}
    except Exception as exc:
        return {"enabled": False, "status": "error", "warning": f"telemetry_db_write_failed: {exc}"}


def _read_ocr_confidence(path_like: object) -> float:
    if not path_like:
        return 0.0
    try:
        path = Path(str(path_like))
        if not path.exists():
            return 0.0
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("confidence", 0.0)
        return float(value or 0.0)
    except Exception:
        return 0.0

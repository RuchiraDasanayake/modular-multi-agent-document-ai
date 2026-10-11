"""FastAPI web UI for document upload and pipeline execution.

Research note:
This module is legacy compatibility surface. It is not the canonical
paper-facing runtime, which is the frontend job runner path ending in
``idpo.cli process-inbox``.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from idpo.pipeline.inbox import process_inbox
from idpo.integration import (
    run_integration_cycle,
    forward_hitl_correction,
    IntegrationResult,
)
from idpo.core.storage import inbox_dir as storage_inbox_dir
from idpo.core.storage import runs_root as storage_runs_root

logger = logging.getLogger("idpo.app")

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
REPO_ROOT = APP_DIR.parents[1]  # /app/ in Docker container
RUNS_ROOT = storage_runs_root()

FULL_TEXT_EXPORT_NAME = "full_text.txt"

def _safe_run_dir(run_id: str) -> Path:
    """Resolve run directory, rejecting path traversal attempts."""
    run_dir = (RUNS_ROOT / run_id).resolve()
    if not run_dir.is_relative_to(RUNS_ROOT.resolve()):
        raise ValueError("Invalid run_id")
    return run_dir

def _read_doc_title(doc_dir: Path) -> str:
    manifest_path = doc_dir / "input" / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    source_path = str(payload.get("path") or "").strip()
    if source_path:
        return Path(source_path).name
    return doc_dir.name

def _read_doc_extracted_text(doc_dir: Path) -> str:
    ocr_path = doc_dir / "preprocessing" / "ocr" / "text.json"
    try:
        payload = json.loads(ocr_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    pages = payload.get("pages")
    if not isinstance(pages, list):
        return ""
    chunks: list[str] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        text = str(page.get("text") or "").strip()
        if not text:
            continue
        number = page.get("number")
        if number is not None:
            chunks.append(f"--- Page {number} ---\n{text}")
        else:
            chunks.append(text)
    return "\n\n".join(chunks).strip()

def _build_full_text_export(run_dir: Path) -> Path | None:
    target_path = run_dir / FULL_TEXT_EXPORT_NAME
    if target_path.exists() and target_path.stat().st_size > 0:
        return target_path

    docs_root = run_dir / "docs"
    if not docs_root.exists() or not docs_root.is_dir():
        return None

    sections: list[str] = []
    for index, doc_dir in enumerate(sorted(child for child in docs_root.iterdir() if child.is_dir()), start=1):
        extracted_text = _read_doc_extracted_text(doc_dir)
        if not extracted_text:
            continue
        title = _read_doc_title(doc_dir)
        header = [
            f"Document {index}: {title}",
            f"Doc ID: {doc_dir.name}",
            "",
        ]
        sections.append("\n".join(header) + extracted_text)

    if not sections:
        return None

    separator = "\n\n" + ("=" * 80) + "\n\n"
    target_path.write_text(separator.join(sections), encoding="utf-8")
    return target_path

def _run_has_full_text_export(run_dir: Path) -> bool:
    if (run_dir / FULL_TEXT_EXPORT_NAME).exists():
        return True
    docs_root = run_dir / "docs"
    if not docs_root.exists() or not docs_root.is_dir():
        return False
    return any((doc_dir / "preprocessing" / "ocr" / "text.json").exists() for doc_dir in docs_root.iterdir() if doc_dir.is_dir())

app = FastAPI(title="IDPO Service", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/health")
def health():
    return {"status": "healthy", "service": "idpo"}

@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Deprecated standalone UI — redirects to main frontend."""
    return HTMLResponse(
        """<!doctype html><html><head><meta charset="utf-8"/>
        <meta http-equiv="refresh" content="0;url=http://localhost:3000/dashboard/idpo"/>
        <title>Redirecting...</title></head><body style="font-family:system-ui;background:#0a0a0a;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh">
        <div style="text-align:center"><p style="font-size:1.5rem;margin-bottom:1rem">📄</p>
        <p>IDPO is now part of the main dashboard.</p>
        <p style="margin-top:.5rem"><a href="http://localhost:3000/dashboard/idpo" style="color:#06b6d4">Go to Document Processing →</a></p>
        </div></body></html>"""
    )

@app.post("/idpo/run")
async def run_demo(
    files: list[UploadFile] = File(...),
    fields: str = Form("[]"),
    config_path: str = Form("configs/config.json"),
    skip_guardrails: str = Form("false"),
    skip_xai: str = Form("false"),
) -> JSONResponse:
    """Legacy direct-run endpoint kept only for compatibility."""
    import asyncio

    logger.warning("Legacy direct-run endpoint /idpo/run invoked; prefer the frontend job path via POST /api/jobs/<job_id>/runs")

    inbox_dir = storage_inbox_dir()
    inbox_dir.mkdir(parents=True, exist_ok=True)

    # Validate file sizes (max 50MB per file)
    MAX_FILE_SIZE = 50 * 1024 * 1024
    saved = []
    for upload in files:
        filename = _safe_filename(upload.filename or f"upload_{uuid.uuid4().hex}")
        target = inbox_dir / filename
        if target.exists():
            target = inbox_dir / f"{target.stem}_{uuid.uuid4().hex}{target.suffix}"
        content = await upload.read()
        if len(content) > MAX_FILE_SIZE:
            return JSONResponse(
                {"error": f"File '{filename}' exceeds 50MB limit"},
                status_code=413,
            )
        with target.open("wb") as handle:
            handle.write(content)
        saved.append(str(target))

    extraction_fields = _parse_fields(fields)

    # ── Step 1: IDPO Processing (run in thread pool to avoid blocking event loop) ──
    # NOTE: AHMN advice is now requested AFTER processing, based on actual doc_type
    # from DAE classification (per-document policies)
    logger.info("Step 1/4: Running extraction pipeline")
    doc_count = max(1, len(saved))
    # Adaptive timeout: keep single-doc runs snappy, allow larger multi-doc batches to complete.
    PIPELINE_TIMEOUT_S = min(1800, max(540, doc_count * 120))
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                process_inbox, REPO_ROOT, config_path, extraction_fields, None, saved
            ),
            timeout=PIPELINE_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.error("Pipeline timed out after %ds for %d file(s)", PIPELINE_TIMEOUT_S, len(saved))
        for path_str in saved:
            try:
                Path(path_str).unlink(missing_ok=True)
            except Exception:
                pass
        return JSONResponse(
            {"error": f"Processing timed out after {PIPELINE_TIMEOUT_S}s — try with fewer or smaller documents"},
            status_code=504,
        )
    except (ValueError, RuntimeError) as exc:
        # Clean up saved files on failure
        for path_str in saved:
            try:
                Path(path_str).unlink(missing_ok=True)
            except Exception:
                pass
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("Pipeline failed unexpectedly")
        for path_str in saved:
            try:
                Path(path_str).unlink(missing_ok=True)
            except Exception:
                pass
        return JSONResponse(
            {"error": f"Pipeline error: {str(exc)}"},
            status_code=500,
        )

    doc_records = cast(list[dict[str, Any]], result["doc_records"])
    metrics = cast(dict[str, Any], result["metrics"])
    processing_time_ms = metrics.get("duration_ms", 0.0)
    failed = result.get("failed", [])

    # ── Steps 2–4: Per-Doc AHMN → Guardrails → XAI → AHMN Feedback ──
    # AHMN advice is now requested per-document AFTER DAE classification,
    # so each document gets a policy based on its actual type
    do_skip_guardrails = skip_guardrails.lower() in ("true", "1", "yes")
    do_skip_xai = skip_xai.lower() in ("true", "1", "yes")
    skipped = [s for s in [
        ("Guardrails" if do_skip_guardrails else ""),
        ("XAI" if do_skip_xai else "")
    ] if s]
    logger.info("Steps 2-4/4: Running integration cycle with per-doc AHMN%s",
                f" (skipping {', '.join(skipped)})" if skipped else "")
    # Adaptive timeout for post-processing integration across doc batches.
    INTEGRATION_TIMEOUT_S = min(600, max(180, len(doc_records) * 45))
    try:
        integration = await asyncio.wait_for(
            asyncio.to_thread(
                run_integration_cycle,
                doc_records=doc_records,
                processing_time_ms=processing_time_ms,
                ahmn_advices=None,
                skip_guardrails=do_skip_guardrails,
                skip_xai=do_skip_xai,
            ),
            timeout=INTEGRATION_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning("Integration cycle timed out after %ds — returning results without integration", INTEGRATION_TIMEOUT_S)
        integration = IntegrationResult()
    except Exception as exc:
        logger.warning("Integration cycle failed: %s — returning results without integration", exc)
        integration = IntegrationResult()

    response_data: dict[str, Any] = {
        "run_id": result["run_id"],
        "run_dir": result["run_dir"],
        "metrics": metrics,
        "docs": doc_records,
        "entities": result.get("entity_records", []),
        "warnings": result.get("preflight_warnings", []),
        "pipeline_integration": integration.to_dict(),
    }
    if failed:
        response_data["partial_failures"] = failed

    return JSONResponse(response_data)

@app.get("/idpo/runs")
def list_runs():
    """List all pipeline runs with metadata, sorted newest-first."""
    runs = []
    if not RUNS_ROOT.exists():
        return {"runs": [], "total": 0}
    for run_dir in sorted(RUNS_ROOT.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        run_info: dict[str, Any] = {"run_id": run_id, "status": "completed"}

        # Read run.json for metadata
        run_json = run_dir / "run.json"
        if run_json.exists():
            try:
                with run_json.open() as f:
                    meta = json.load(f)
                raw_ts = meta.get("started_at")
                if isinstance(raw_ts, (int, float)):
                    from datetime import datetime, timezone
                    run_info["started_at"] = datetime.fromtimestamp(raw_ts, tz=timezone.utc).isoformat()
                elif raw_ts:
                    run_info["started_at"] = str(raw_ts)
                run_info["config_path"] = meta.get("config_path")
            except Exception:
                pass

        # Read metrics.json for stats
        metrics_json = run_dir / "metrics.json"
        if metrics_json.exists():
            try:
                with metrics_json.open() as f:
                    metrics = json.load(f)
                run_info["doc_count"] = metrics.get("doc_count", 0)
                run_info["failed_count"] = metrics.get("failed_count", 0)
                run_info["duration_ms"] = metrics.get("duration_ms", 0)
            except Exception:
                pass

        # Check available exports
        run_info["has_docs_export"] = (run_dir / "docs.xlsx").exists() or (run_dir / "docs.csv").exists()
        run_info["has_entities_export"] = (run_dir / "entities.xlsx").exists() or (run_dir / "entities.csv").exists()
        run_info["has_text_export"] = _run_has_full_text_export(run_dir)

        runs.append(run_info)
    return {"runs": runs, "total": len(runs)}

@app.get("/idpo/runs/{run_id}/docs.xlsx")
def download_docs(run_id: str):
    try:
        run_dir = _safe_run_dir(run_id)
    except ValueError:
        return JSONResponse({"error": "invalid run_id"}, status_code=400)
    xlsx_path = run_dir / "docs.xlsx"
    if xlsx_path.exists():
        return FileResponse(
            xlsx_path, filename="docs.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    csv_path = run_dir / "docs.csv"
    if csv_path.exists():
        return FileResponse(csv_path, filename="docs.csv", media_type="text/csv")
    return JSONResponse({"error": "docs export not found"}, status_code=404)

@app.get("/idpo/runs/{run_id}/run.xlsx")
def download_run(run_id: str):
    try:
        run_dir = _safe_run_dir(run_id)
    except ValueError:
        return JSONResponse({"error": "invalid run_id"}, status_code=400)
    xlsx_path = run_dir / "run.xlsx"
    if xlsx_path.exists():
        return FileResponse(
            xlsx_path, filename="run.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    csv_path = run_dir / "run.csv"
    if csv_path.exists():
        return FileResponse(csv_path, filename="run.csv", media_type="text/csv")
    return JSONResponse({"error": "run export not found"}, status_code=404)

@app.get("/idpo/runs/{run_id}/entities.xlsx")
def download_entities(run_id: str):
    try:
        run_dir = _safe_run_dir(run_id)
    except ValueError:
        return JSONResponse({"error": "invalid run_id"}, status_code=400)
    xlsx_path = run_dir / "entities.xlsx"
    if xlsx_path.exists():
        return FileResponse(
            xlsx_path, filename="entities.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    csv_path = run_dir / "entities.csv"
    if csv_path.exists():
        return FileResponse(csv_path, filename="entities.csv", media_type="text/csv")
    return JSONResponse({"error": "entities export not found"}, status_code=404)

@app.get("/idpo/runs/{run_id}/full_text.txt")
def download_full_text(run_id: str):
    try:
        run_dir = _safe_run_dir(run_id)
    except ValueError:
        return JSONResponse({"error": "invalid run_id"}, status_code=400)
    text_path = _build_full_text_export(run_dir)
    if text_path is None:
        return JSONResponse({"error": "full text export not found"}, status_code=404)
    return FileResponse(text_path, filename=FULL_TEXT_EXPORT_NAME, media_type="text/plain; charset=utf-8")

def _parse_fields(fields_payload: str) -> list[dict[str, str]]:
    if not fields_payload:
        return []
    try:
        parsed = json.loads(fields_payload)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    fields: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        description = str(item.get("description", "")).strip()
        if not name:
            continue
        fields.append({"name": name, "description": description})
    return fields

def _safe_filename(name: str) -> str:
    return Path(name).name.replace("..", "")

# ─── HITL → AHMN Bridge Endpoint ─────────────────────────────────────────

from pydantic import BaseModel, Field

class HITLCorrectionRequest(BaseModel):
    advice_id: str = Field(..., description="AHMN advice ID from the original processing run")
    feedback_type: str = Field(
        ..., pattern="^(correct|incorrect|partially_correct|needs_more_context)$",
        description="Human reviewer's assessment of answer quality",
    )

@app.post("/idpo/hitl-correction")
def hitl_correction(body: HITLCorrectionRequest):
    """Forward human reviewer corrections from XAI-HITL to AHMN's learning loop.

    When a reviewer marks an extraction as incorrect, this sets the
    human_corrected flag on the MTM outcome so AHMN can learn from review.
    """
    result = forward_hitl_correction(
        advice_id=body.advice_id,
        feedback_type=body.feedback_type,
    )
    return JSONResponse(content=result)

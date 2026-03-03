from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from idpo.pipeline.inbox import process_inbox


APP_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = APP_DIR / "templates" / "index.html"
STATIC_DIR = APP_DIR / "static"
REPO_ROOT = APP_DIR.parents[1]  # /app/ in Docker container

app = FastAPI(title="IDPO Demo", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
def health():
    return {"status": "healthy", "service": "idpo"}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.post("/idpo/run")
@app.post("/api/run")
def run_demo(
    files: List[UploadFile] = File(...),
    fields: str = Form("[]"),
    config_path: str = Form("configs/sample_config.json"),
) -> JSONResponse:
    inbox_dir = REPO_ROOT / "inputs" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for upload in files:
        filename = _safe_filename(upload.filename or f"upload_{uuid.uuid4().hex}")
        target = inbox_dir / filename
        if target.exists():
            target = inbox_dir / f"{target.stem}_{uuid.uuid4().hex}{target.suffix}"
        with target.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        saved.append(str(target))

    extraction_fields = _parse_fields(fields)

    try:
        result = process_inbox(REPO_ROOT, config_path, extraction_fields=extraction_fields)
    except SystemExit as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    return JSONResponse(
        {
            "run_id": result["run_id"],
            "run_dir": result["run_dir"],
            "metrics": result["metrics"],
            "docs": result["doc_records"],
            "entities": result.get("entity_records", []),
            "warnings": result.get("preflight_warnings", []),
        }
    )


@app.get("/idpo/runs/{run_id}/docs.xlsx")
@app.get("/api/runs/{run_id}/docs.xlsx")
def download_docs(run_id: str):
    run_dir = REPO_ROOT / "runs" / run_id
    xlsx_path = run_dir / "docs.xlsx"
    if xlsx_path.exists():
        return FileResponse(xlsx_path, filename="docs.xlsx")
    csv_path = run_dir / "docs.csv"
    if csv_path.exists():
        return FileResponse(csv_path, filename="docs.csv")
    return JSONResponse({"error": "docs export not found"}, status_code=404)


@app.get("/idpo/runs/{run_id}/run.xlsx")
@app.get("/api/runs/{run_id}/run.xlsx")
def download_run(run_id: str):
    run_dir = REPO_ROOT / "runs" / run_id
    xlsx_path = run_dir / "run.xlsx"
    if xlsx_path.exists():
        return FileResponse(xlsx_path, filename="run.xlsx")
    csv_path = run_dir / "run.csv"
    if csv_path.exists():
        return FileResponse(csv_path, filename="run.csv")
    return JSONResponse({"error": "run export not found"}, status_code=404)


@app.get("/idpo/runs/{run_id}/entities.xlsx")
@app.get("/api/runs/{run_id}/entities.xlsx")
def download_entities(run_id: str):
    run_dir = REPO_ROOT / "runs" / run_id
    xlsx_path = run_dir / "entities.xlsx"
    if xlsx_path.exists():
        return FileResponse(xlsx_path, filename="entities.xlsx")
    csv_path = run_dir / "entities.csv"
    if csv_path.exists():
        return FileResponse(csv_path, filename="entities.csv")
    return JSONResponse({"error": "entities export not found"}, status_code=404)


def _parse_fields(fields_payload: str) -> List[Dict[str, str]]:
    if not fields_payload:
        return []
    try:
        parsed = json.loads(fields_payload)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    fields: List[Dict[str, str]] = []
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

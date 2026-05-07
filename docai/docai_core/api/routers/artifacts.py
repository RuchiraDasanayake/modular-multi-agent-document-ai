"""Artifact indexing and retrieval endpoints."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from docai_core.api.route_helpers import (
    get_db_path,
    get_runs_dir,
    read_doc_artifact,
    resolve_artifact_job_dir,
    validate_artifact_root_containment,
)
from docai_core.api.schemas import (
    ArtifactIndexRequest,
    ArtifactIndexResponse,
    ArtifactListResponse,
)
from docai_core.persistence import ArtifactIndexer, SQLiteStore

router = APIRouter()


@router.post("/runs/{run_id}/index-artifacts", response_model=ArtifactIndexResponse)
def index_run_artifacts(request: Request, run_id: str, body: ArtifactIndexRequest) -> ArtifactIndexResponse:
    """Index execution artifacts for a run into SQLite."""
    db_path: Path = get_db_path(request)
    runs_dir: Path = get_runs_dir(request)
    store = SQLiteStore(db_path)

    try:
        run = store.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifact_root = body.artifact_root or run.artifact_root
    if not artifact_root:
        raise HTTPException(
            status_code=400,
            detail="artifact_root must be provided in request or stored in run record",
        )
    artifact_root = str(validate_artifact_root_containment(runs_dir, artifact_root))

    indexer = ArtifactIndexer(store)
    result = indexer.index_run_artifacts(
        run_id=run_id,
        artifact_root=artifact_root,
        document_id=body.document_id,
    )

    return ArtifactIndexResponse(
        run_id=run_id,
        document_id=body.document_id,
        artifact_root=artifact_root,
        artifacts_indexed=result["artifacts_indexed"],
        metrics_indexed=result["metrics_indexed"],
        warnings=result["warnings"],
        errors=result["errors"],
    )


@router.get("/runs/{run_id}/artifacts", response_model=ArtifactListResponse)
def get_run_artifacts(run_id: str, request: Request) -> ArtifactListResponse:
    """List artifacts for a run."""
    _, _, job_dir, _ = resolve_artifact_job_dir(request, run_id)
    artifacts = sorted(
        str(p.relative_to(job_dir)) for p in job_dir.rglob("*") if p.is_file()
    )
    return ArtifactListResponse(run_id=run_id, artifact_count=len(artifacts), artifacts=artifacts)


@router.get("/runs/{run_id}/documents/{doc_id}/final-output")
def get_final_output(run_id: str, doc_id: str, request: Request) -> dict[str, Any]:
    """Get final extraction output for a document."""
    return read_doc_artifact(request, run_id, doc_id, "final_output.json")


@router.get("/runs/{run_id}/documents/{doc_id}/validation-report")
def get_validation_report(run_id: str, doc_id: str, request: Request) -> dict[str, Any]:
    """Get validation report for a document."""
    return read_doc_artifact(request, run_id, doc_id, "validation_report.json")

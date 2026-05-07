"""Runs metadata endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from docai_core.api.route_helpers import (
    get_db_path,
    get_runs_dir,
    load_schema_or_404,
    validate_artifact_root_containment,
)
from docai_core.api.schemas import (
    RunCreate,
    RunDocumentCreate,
    RunDocumentOut,
    RunDocumentRoutingUpdate,
    RunOut,
)
from docai_core.persistence import SQLiteStore

_VALID_MODES = frozenset({"stub", "local_text", "local_text_model"})

router = APIRouter()


@router.get("/jobs/{job_id}/runs", response_model=list[RunOut])
def list_job_runs(request: Request, job_id: str) -> list[RunOut]:
    """List runs for a job."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        job = store.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    runs = store.list_runs_for_job(job_id)
    return [
        RunOut(
            run_id=r.run_id,
            project_id=r.project_id,
            job_id=r.job_id,
            schema_id=r.schema_id,
            policy_id=r.policy_id,
            mode=r.mode,
            run_type=r.run_type,
            status=r.status,
            artifact_root=r.artifact_root,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in runs
    ]


@router.post("/jobs/{job_id}/runs", response_model=RunOut)
def create_job_run(request: Request, job_id: str, body: RunCreate) -> RunOut:
    """Create a run under a job (metadata only, no execution)."""
    db_path: Path = get_db_path(request)
    runs_dir: Path = get_runs_dir(request)
    store = SQLiteStore(db_path)

    try:
        job = store.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    artifact_root = body.artifact_root
    if artifact_root:
        artifact_root = str(validate_artifact_root_containment(runs_dir, artifact_root))

    run = store.create_run(
        project_id=job.project_id,
        job_id=job_id,
        schema_id=job.schema_id,
        run_type=body.run_type,
        policy_id=body.policy_id,
        mode=body.mode if body.mode is not None else job.default_mode,
        artifact_root=artifact_root,
        status=body.status,
    )

    return RunOut(
        run_id=run.run_id,
        project_id=run.project_id,
        job_id=run.job_id,
        schema_id=run.schema_id,
        policy_id=run.policy_id,
        mode=run.mode,
        run_type=run.run_type,
        status=run.status,
        artifact_root=run.artifact_root,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(request: Request, run_id: str) -> RunOut:
    """Get a run by ID."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    try:
        run = store.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return RunOut(
        run_id=run.run_id,
        project_id=run.project_id,
        job_id=run.job_id,
        schema_id=run.schema_id,
        policy_id=run.policy_id,
        mode=run.mode,
        run_type=run.run_type,
        status=run.status,
        artifact_root=run.artifact_root,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.get("/runs/{run_id}/documents", response_model=list[RunDocumentOut])
def list_run_documents(request: Request, run_id: str) -> list[RunDocumentOut]:
    """List documents attached to a run."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        run = store.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    run_docs = store.list_run_documents(run_id)
    return [
        RunDocumentOut(
            run_document_id=rd["run_document_id"],
            run_id=rd["run_id"],
            document_id=rd["document_id"],
            schema_id=rd.get("schema_id"),
            mode=rd.get("mode"),
            routing_reason=rd.get("routing_reason"),
            routing_source="document_override" if (rd.get("schema_id") or rd.get("mode")) else "run_default",
            status=rd["status"],
            created_at=rd["created_at"],
            completed_at=rd["completed_at"],
        )
        for rd in run_docs
    ]


@router.post("/runs/{run_id}/documents", response_model=RunDocumentOut)
def attach_document_to_run(request: Request, run_id: str, body: RunDocumentCreate) -> RunDocumentOut:
    """Attach a registered document to a run."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        run = store.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    try:
        doc = store.get_document(body.document_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Document not found: {body.document_id}")

    if doc["job_id"] != run.job_id:
        raise HTTPException(
            status_code=400,
            detail=f"Document {body.document_id} does not belong to job {run.job_id}",
        )

    if body.mode is not None and body.mode not in _VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"mode must be one of: {', '.join(sorted(_VALID_MODES))}",
        )
    if body.schema_id is not None:
        load_schema_or_404(body.schema_id, db_path)

    run_document_id = store.create_run_document(
        run_id,
        body.document_id,
        schema_id=body.schema_id,
        mode=body.mode,
        routing_reason=body.routing_reason,
    )

    if body.status != "processing":
        store.update_run_document_status(run_document_id, body.status)

    rd = store.get_run_document(run_document_id)
    return RunDocumentOut(
        run_document_id=rd["run_document_id"],
        run_id=rd["run_id"],
        document_id=rd["document_id"],
        schema_id=rd.get("schema_id"),
        mode=rd.get("mode"),
        routing_reason=rd.get("routing_reason"),
        routing_source="document_override" if (rd.get("schema_id") or rd.get("mode")) else "run_default",
        status=rd["status"],
        created_at=rd["created_at"],
        completed_at=rd["completed_at"],
    )


@router.put("/runs/{run_id}/documents/{document_id}/routing", response_model=RunDocumentOut)
def update_run_document_routing(
    request: Request,
    run_id: str,
    document_id: str,
    body: RunDocumentRoutingUpdate,
) -> RunDocumentOut:
    """Update per-document routing override for a run/document mapping."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        run = store.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    try:
        doc = store.get_document(document_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    if doc["job_id"] != run.job_id:
        raise HTTPException(
            status_code=400,
            detail=f"Document {document_id} does not belong to job {run.job_id}",
        )

    try:
        store.get_run_document_by_run_and_document(run_id, document_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Document {document_id} is not attached to run {run_id}")

    if body.mode is not None and body.mode not in _VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"mode must be one of: {', '.join(sorted(_VALID_MODES))}",
        )
    if body.schema_id is not None:
        load_schema_or_404(body.schema_id, db_path)

    try:
        store.update_run_document_routing(
            run_id=run_id,
            document_id=document_id,
            schema_id=body.schema_id,
            mode=body.mode,
            routing_reason=body.routing_reason,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Document {document_id} is not attached to run {run_id}")

    rd = store.get_run_document_by_run_and_document(run_id, document_id)
    return RunDocumentOut(
        run_document_id=rd["run_document_id"],
        run_id=rd["run_id"],
        document_id=rd["document_id"],
        schema_id=rd.get("schema_id"),
        mode=rd.get("mode"),
        routing_reason=rd.get("routing_reason"),
        routing_source="document_override" if (rd.get("schema_id") or rd.get("mode")) else "run_default",
        status=rd["status"],
        created_at=rd["created_at"],
        completed_at=rd["completed_at"],
    )

"""Jobs endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from docai_core.api.route_helpers import (
    load_schema_or_404,
    get_db_path,
)
from docai_core.api.schemas import JobCreate, JobOut
from docai_core.persistence import SQLiteStore

_VALID_MODES = frozenset({"stub", "local_text", "local_text_model"})

router = APIRouter()


@router.get("/projects/{project_id}/jobs", response_model=list[JobOut])
def list_project_jobs(request: Request, project_id: str) -> list[JobOut]:
    """List jobs for a project."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    jobs = store.list_jobs(project_id)
    return [
        JobOut(
            job_id=j.job_id,
            project_id=j.project_id,
            schema_id=j.schema_id,
            profile_id=j.profile_id,
            default_mode=j.default_mode,
            name=j.name,
            job_type=j.job_type,
            status=j.status,
            created_at=j.created_at,
        )
        for j in jobs
    ]


@router.post("/projects/{project_id}/jobs", response_model=JobOut)
def create_project_job(request: Request, project_id: str, body: JobCreate) -> JobOut:
    """Create a job under a project."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    profile_id = body.profile_id
    schema_id = body.schema_id
    default_mode = body.default_mode

    if profile_id:
        try:
            profile = store.get_extraction_profile(profile_id)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Extraction profile not found: {profile_id}")
        if profile.project_id != project_id:
            raise HTTPException(status_code=400, detail=f"Extraction profile {profile_id} does not belong to project {project_id}")
        schema_id = profile.schema_id
        default_mode = profile.mode
    elif not schema_id:
        raise HTTPException(status_code=422, detail="schema_id is required when profile_id is not provided")

    if default_mode is not None and default_mode not in _VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"default_mode must be one of: {', '.join(sorted(_VALID_MODES))}",
        )

    load_schema_or_404(schema_id, db_path)

    job = store.create_job(
        project_id=project_id,
        schema_id=schema_id,
        profile_id=profile_id,
        default_mode=default_mode,
        name=body.name,
        job_type=body.job_type,
    )
    return JobOut(
        job_id=job.job_id,
        project_id=job.project_id,
        schema_id=job.schema_id,
        profile_id=job.profile_id,
        default_mode=job.default_mode,
        name=job.name,
        job_type=job.job_type,
        status=job.status,
        created_at=job.created_at,
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(request: Request, job_id: str) -> JobOut:
    """Get a job by ID."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    try:
        job = store.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return JobOut(
        job_id=job.job_id,
        project_id=job.project_id,
        schema_id=job.schema_id,
        profile_id=job.profile_id,
        default_mode=job.default_mode,
        name=job.name,
        job_type=job.job_type,
        status=job.status,
        created_at=job.created_at,
    )

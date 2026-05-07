"""Projects and extraction profiles endpoints."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from docai_core.api.route_helpers import (
    extraction_profile_to_out,
    load_schema_or_404,
    get_db_path,
)
from docai_core.api.schemas import (
    ExtractionProfileCreate,
    ExtractionProfileOut,
    ExtractionProfileUpdate,
    ProjectCreate,
    ProjectOut,
)
from docai_core.persistence import SQLiteStore

_VALID_MODES = frozenset({"stub", "local_text", "local_text_model"})

router = APIRouter()


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(request: Request) -> list[ProjectOut]:
    """List all projects."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    projects = store.list_projects()
    return [
        ProjectOut(
            project_id=p.project_id,
            name=p.name,
            description=p.description,
            status=p.status,
            created_at=p.created_at,
        )
        for p in projects
    ]


@router.post("/projects", response_model=ProjectOut)
def create_project(request: Request, body: ProjectCreate) -> ProjectOut:
    """Create a new project."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    project = store.create_project(
        project_id=f"proj-{uuid.uuid4().hex[:12]}",
        name=body.name,
        description=body.description,
    )
    return ProjectOut(
        project_id=project.project_id,
        name=project.name,
        description=project.description,
        status=project.status,
        created_at=project.created_at,
    )


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(request: Request, project_id: str) -> ProjectOut:
    """Get a project by ID."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    try:
        project = store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return ProjectOut(
        project_id=project.project_id,
        name=project.name,
        description=project.description,
        status=project.status,
        created_at=project.created_at,
    )


@router.get("/projects/{project_id}/extraction-profiles", response_model=list[ExtractionProfileOut])
def list_project_extraction_profiles(request: Request, project_id: str) -> list[ExtractionProfileOut]:
    """List extraction profiles for a project."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    try:
        store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return [extraction_profile_to_out(record) for record in store.list_extraction_profiles(project_id)]


@router.post("/projects/{project_id}/extraction-profiles", response_model=ExtractionProfileOut)
def create_project_extraction_profile(
    request: Request,
    project_id: str,
    body: ExtractionProfileCreate,
) -> ExtractionProfileOut:
    """Create an extraction profile for a project."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    try:
        store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    if body.mode not in _VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"mode must be one of: {', '.join(sorted(_VALID_MODES))}",
        )
    load_schema_or_404(body.schema_id, db_path)
    record = store.create_extraction_profile(
        project_id=project_id,
        name=body.name.strip(),
        schema_id=body.schema_id,
        mode=body.mode,
        ocr_strategy=body.ocr_strategy.strip(),
        validation_level=body.validation_level.strip(),
        is_default=1 if body.is_default else 0,
        created_from_advice_id=body.created_from_advice_id,
    )
    return extraction_profile_to_out(record)


@router.get("/extraction-profiles/{profile_id}", response_model=ExtractionProfileOut)
def get_extraction_profile(request: Request, profile_id: str) -> ExtractionProfileOut:
    """Get an extraction profile by ID."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    try:
        record = store.get_extraction_profile(profile_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Extraction profile not found: {profile_id}")
    return extraction_profile_to_out(record)


@router.put("/extraction-profiles/{profile_id}", response_model=ExtractionProfileOut)
def update_extraction_profile(request: Request, profile_id: str, body: ExtractionProfileUpdate) -> ExtractionProfileOut:
    """Update an extraction profile."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    if body.mode not in _VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"mode must be one of: {', '.join(sorted(_VALID_MODES))}",
        )
    load_schema_or_404(body.schema_id, db_path)
    try:
        record = store.update_extraction_profile(
            profile_id=profile_id,
            name=body.name.strip(),
            schema_id=body.schema_id,
            mode=body.mode,
            ocr_strategy=body.ocr_strategy.strip(),
            validation_level=body.validation_level.strip(),
            is_default=1 if body.is_default else 0,
            created_from_advice_id=body.created_from_advice_id,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Extraction profile not found: {profile_id}")
    return extraction_profile_to_out(record)

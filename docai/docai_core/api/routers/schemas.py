"""Extraction schemas endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from docai_core.api.route_helpers import (
    schema_record_to_out,
    validate_schema_payload,
    get_db_path,
)
from docai_core.api.schemas import (
    ExtractionSchemaCreate,
    ExtractionSchemaOut,
    ExtractionSchemaUpdate,
)
from docai_core.persistence import SQLiteStore

router = APIRouter()


@router.get("/projects/{project_id}/schemas", response_model=list[ExtractionSchemaOut])
def list_project_schemas(request: Request, project_id: str) -> list[ExtractionSchemaOut]:
    """List extraction schemas for a project."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    records = store.list_extraction_schemas(project_id)
    return [schema_record_to_out(record) for record in records]


@router.post("/projects/{project_id}/schemas", response_model=ExtractionSchemaOut)
def create_project_schema(
    request: Request,
    project_id: str,
    body: ExtractionSchemaCreate,
) -> ExtractionSchemaOut:
    """Create extraction schema under a project."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    fields, tables = validate_schema_payload(body.name, body.fields, body.tables)
    record = store.create_extraction_schema(
        project_id=project_id,
        name=body.name.strip(),
        document_type=body.document_type.strip() if isinstance(body.document_type, str) else None,
        fields=fields,
        tables=tables,
    )
    return schema_record_to_out(record)


@router.get("/schemas/{schema_id}", response_model=ExtractionSchemaOut)
def get_schema(request: Request, schema_id: str) -> ExtractionSchemaOut:
    """Get extraction schema by ID."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    try:
        record = store.get_extraction_schema(schema_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Schema not found: {schema_id}")
    return schema_record_to_out(record)


@router.put("/schemas/{schema_id}", response_model=ExtractionSchemaOut)
def update_schema(request: Request, schema_id: str, body: ExtractionSchemaUpdate) -> ExtractionSchemaOut:
    """Update extraction schema payload and increment version."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    try:
        store.get_extraction_schema(schema_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Schema not found: {schema_id}")

    fields, tables = validate_schema_payload(body.name, body.fields, body.tables)
    record = store.update_extraction_schema(
        schema_id=schema_id,
        name=body.name.strip(),
        document_type=body.document_type.strip() if isinstance(body.document_type, str) else None,
        fields=fields,
        tables=tables,
    )
    return schema_record_to_out(record)

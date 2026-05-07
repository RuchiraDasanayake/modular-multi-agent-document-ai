"""Documents endpoints."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from docai_core.api.route_helpers import (
    get_db_path,
    get_runs_dir,
    is_path_within_root,
    read_upload_with_limit,
    request_max_upload_bytes,
    sanitize_upload_filename,
)
from docai_core.api.schemas import DocumentCreate, DocumentOut
from docai_core.persistence import SQLiteStore

router = APIRouter()


@router.get("/jobs/{job_id}/documents", response_model=list[DocumentOut])
def list_job_documents(request: Request, job_id: str) -> list[DocumentOut]:
    """List documents for a job."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        job = store.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    documents = store.list_documents_for_job(job_id)
    return [
        DocumentOut(
            document_id=d["document_id"],
            project_id=d["project_id"],
            job_id=d["job_id"],
            original_filename=d["original_filename"],
            file_path=d["file_path"],
            file_hash=d["file_hash"],
            file_type=d["file_type"],
            status=d["status"],
            created_at=d["created_at"],
        )
        for d in documents
    ]


@router.post("/jobs/{job_id}/documents", response_model=DocumentOut)
def create_job_document(request: Request, job_id: str, body: DocumentCreate) -> DocumentOut:
    """Register a document under a job."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        job = store.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    document_id = store.register_document(
        project_id=job.project_id,
        job_id=job_id,
        original_filename=body.original_filename,
        file_path=body.file_path,
        file_hash=body.file_hash,
        file_type=body.file_type,
        status=body.status,
    )

    doc = store.get_document(document_id)
    return DocumentOut(
        document_id=doc["document_id"],
        project_id=doc["project_id"],
        job_id=doc["job_id"],
        original_filename=doc["original_filename"],
        file_path=doc["file_path"],
        file_hash=doc["file_hash"],
        file_type=doc["file_type"],
        status=doc["status"],
        created_at=doc["created_at"],
    )


@router.post("/jobs/{job_id}/documents/upload", response_model=DocumentOut, status_code=201)
async def upload_job_document(
    job_id: str,
    request: Request,
    file: UploadFile = File(...),
    status: str = Form("registered"),
) -> DocumentOut:
    """Upload and register a document under a job."""
    db_path: Path = get_db_path(request)
    runs_dir: Path = get_runs_dir(request)
    store = SQLiteStore(db_path)

    try:
        job = store.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    max_upload_bytes = request_max_upload_bytes(request)
    content = await read_upload_with_limit(file, max_upload_bytes)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file cannot be empty")

    safe_name = sanitize_upload_filename(file.filename)
    stored_name = f"upload-{uuid.uuid4().hex}-{safe_name}"

    upload_dir: Path = runs_dir / "uploads" / "jobs" / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    save_path = upload_dir / stored_name
    if not is_path_within_root(save_path, upload_dir):
        raise HTTPException(status_code=400, detail="Unsafe upload filename path resolution")
    save_path.write_bytes(content)

    file_hash = hashlib.sha256(content).hexdigest()

    file_type: str | None = file.content_type or None
    if not file_type or file_type == "application/octet-stream":
        suffix = Path(safe_name).suffix.lstrip(".")
        file_type = suffix if suffix else None

    document_id = store.register_document(
        project_id=job.project_id,
        job_id=job_id,
        original_filename=safe_name,
        file_path=str(save_path),
        file_hash=file_hash,
        file_type=file_type,
        status=status,
    )

    doc = store.get_document(document_id)
    return DocumentOut(
        document_id=doc["document_id"],
        project_id=doc["project_id"],
        job_id=doc["job_id"],
        original_filename=doc["original_filename"],
        file_path=doc["file_path"],
        file_hash=doc["file_hash"],
        file_type=doc["file_type"],
        status=doc["status"],
        created_at=doc["created_at"],
    )


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(request: Request, document_id: str) -> DocumentOut:
    """Get a document by ID."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    try:
        doc = store.get_document(document_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
    return DocumentOut(
        document_id=doc["document_id"],
        project_id=doc["project_id"],
        job_id=doc["job_id"],
        original_filename=doc["original_filename"],
        file_path=doc["file_path"],
        file_hash=doc["file_hash"],
        file_type=doc["file_type"],
        status=doc["status"],
        created_at=doc["created_at"],
    )


@router.get("/documents/{document_id}/file")
def get_document_file(request: Request, document_id: str):
    """Download or view the original document file."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        doc = store.get_document(document_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    file_path = Path(doc["file_path"])
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Document file not found: {doc['file_path']}")

    content_type = doc.get("file_type") or "application/octet-stream"

    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=doc["original_filename"],
    )

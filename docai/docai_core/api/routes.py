from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from docai_core.api.schemas import (
    AdvisoryRecommendationOut,
    AdvisoryRequest,
    AdvisoryResponse,
    AdaptiveRoutingAdviceOut,
    AdaptiveRoutingRecommendationOut,
    ArtifactIndexRequest,
    ArtifactIndexResponse,
    ArtifactListResponse,
    DocumentCreate,
    DocumentOut,
    ExtractionProfileCreate,
    ExtractionProfileOut,
    ExtractionProfileUpdate,
    ExecuteRunRequest,
    ExecuteRunResponse,
    ExtractionSchemaCreate,
    ExtractionSchemaOut,
    ExtractionSchemaUpdate,
    HealthResponse,
    JobCreate,
    JobOut,
    LearningSampleListOut,
    ProjectCreate,
    ProjectOut,
    ReviewRecordCreate,
    ReviewRecordOut,
    RunCreate,
    RunDocumentCreate,
    RunDocumentOut,
    RunDocumentRoutingUpdate,
    RunOut,
    RunResponse,
)
from docai_core.application.job_run_service import JobRunRequest, JobRunService
from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    Job,
    Project,
)
from docai_core.extraction.qwen_extraction_step import QwenExtractionStep
from docai_core.orchestration.pipeline_config import RuntimePipelineConfig
from docai_core.persistence import ArtifactIndexer, SQLiteStore
from docai_core.orchestration.pipeline_factory import (
    build_local_text_pipeline,
    build_model_pipeline,
    build_pipeline_for_policy,
    build_stub_pipeline,
)
from docai_core.plugins.models.stub_model_plugin import StubModelPlugin
from docai_core.schemas import load_extraction_schema
from docai_core.schemas.schema_loader import load_schema_for_execution
from docai_core.text_acquisition.base import UnsupportedDocumentTypeError
from docai_core.text_acquisition.image_ocr_extractor import ImageOCRDependencyError

router = APIRouter()


def _load_schema_or_404(schema_id: str, db_path: Path) -> "ExtractionSchema":
    """Load schema from built-in configs or SQLite; raise 404 if not found."""
    try:
        return load_schema_for_execution(schema_id, db_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

_VALID_MODES = frozenset({"stub", "local_text", "local_text_model"})
_REVIEW_STATUSES = frozenset({"reviewed", "corrected", "approved"})
_REVIEW_DECISIONS = frozenset({
    "correct",
    "wrong_value",
    "missed_field",
    "hallucinated_field",
    "correctly_skipped",
})
_DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


def _request_max_upload_bytes(request: Request) -> int:
    max_bytes = getattr(request.app.state, "max_upload_bytes", _DEFAULT_MAX_UPLOAD_BYTES)
    try:
        value = int(max_bytes)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_UPLOAD_BYTES
    return value if value > 0 else _DEFAULT_MAX_UPLOAD_BYTES


async def _read_upload_with_limit(upload: UploadFile, max_upload_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload too large: {total} bytes exceeds limit {max_upload_bytes} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _sanitize_upload_filename(filename: str | None) -> str:
    raw_name = (filename or "").strip()
    safe_name = Path(raw_name.replace("\\", "/")).name
    if safe_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Uploaded filename is missing or unsafe")
    return safe_name


def _is_path_within_root(path: Path, allowed_root: Path) -> bool:
    try:
        path.resolve().relative_to(allowed_root.resolve())
        return True
    except ValueError:
        return False


def _validate_artifact_root_containment(
    runs_dir: Path,
    artifact_root: str,
) -> Path:
    artifact_root_path = Path(artifact_root).resolve()
    if not _is_path_within_root(artifact_root_path, runs_dir):
        raise HTTPException(
            status_code=400,
            detail=(
                f"artifact_root must stay under runs_dir {runs_dir.resolve()}; "
                f"got {artifact_root_path}"
            ),
        )
    return artifact_root_path


def _model_plugin_for_env():
    p = os.getenv("DOCAI_MODEL_PROVIDER", "").lower().strip()
    if p not in ("", "stub", "ollama"):
        raise HTTPException(400, f"DOCAI_MODEL_PROVIDER={p!r} unknown. Valid: stub, ollama.")
    if p != "ollama":
        return StubModelPlugin()
    from docai_core.plugins.models.qwen_model_plugin import QwenModelPlugin
    b = os.getenv("DOCAI_OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    m = os.getenv("DOCAI_OLLAMA_MODEL", "qwen")
    t = int(os.getenv("DOCAI_OLLAMA_TIMEOUT_SECONDS", "60"))
    return QwenModelPlugin(model_name=m, endpoint_url=f"{b}/api/generate", timeout_seconds=t)


def _pipeline_config(mode: str) -> RuntimePipelineConfig:
    if mode == "stub":
        return build_stub_pipeline()
    if mode == "local_text":
        return build_local_text_pipeline()
    return build_model_pipeline(model_step=QwenExtractionStep(model_plugin=_model_plugin_for_env()))


def _pipeline_config_for_request(
    mode: str | None,
    policy_id: str | None,
) -> RuntimePipelineConfig:
    if policy_id is not None:
        try:
            return build_pipeline_for_policy(policy_id)
        except ValueError:
            raise HTTPException(400, f"Unknown policy_id {policy_id!r}.")
    if mode is not None:
        return _pipeline_config(mode)
    raise HTTPException(400, "Provide mode or policy_id.")

@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="docai-v2-api")


# ---------------------------------------------------------------------------
# Projects endpoints
# ---------------------------------------------------------------------------

@router.get("/projects", response_model=list[ProjectOut])
def list_projects(request: Request) -> list[ProjectOut]:
    """List all projects."""
    db_path: Path = request.app.state.db_path
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
    db_path: Path = request.app.state.db_path
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
    db_path: Path = request.app.state.db_path
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
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)
    try:
        store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return [_extraction_profile_to_out(record) for record in store.list_extraction_profiles(project_id)]


@router.post("/projects/{project_id}/extraction-profiles", response_model=ExtractionProfileOut)
def create_project_extraction_profile(
    request: Request,
    project_id: str,
    body: ExtractionProfileCreate,
) -> ExtractionProfileOut:
    db_path: Path = request.app.state.db_path
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
    _load_schema_or_404(body.schema_id, db_path)
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
    return _extraction_profile_to_out(record)


@router.get("/extraction-profiles/{profile_id}", response_model=ExtractionProfileOut)
def get_extraction_profile(request: Request, profile_id: str) -> ExtractionProfileOut:
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)
    try:
        record = store.get_extraction_profile(profile_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Extraction profile not found: {profile_id}")
    return _extraction_profile_to_out(record)


@router.put("/extraction-profiles/{profile_id}", response_model=ExtractionProfileOut)
def update_extraction_profile(request: Request, profile_id: str, body: ExtractionProfileUpdate) -> ExtractionProfileOut:
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)
    if body.mode not in _VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"mode must be one of: {', '.join(sorted(_VALID_MODES))}",
        )
    _load_schema_or_404(body.schema_id, db_path)
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
    return _extraction_profile_to_out(record)


# ---------------------------------------------------------------------------
# Extraction Schemas endpoints
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/schemas", response_model=list[ExtractionSchemaOut])
def list_project_schemas(request: Request, project_id: str) -> list[ExtractionSchemaOut]:
    """List extraction schemas for a project."""
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)

    try:
        store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    records = store.list_extraction_schemas(project_id)
    return [_schema_record_to_out(record) for record in records]


@router.post("/projects/{project_id}/schemas", response_model=ExtractionSchemaOut)
def create_project_schema(
    request: Request,
    project_id: str,
    body: ExtractionSchemaCreate,
) -> ExtractionSchemaOut:
    """Create extraction schema under a project."""
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)

    try:
        store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    fields, tables = _validate_schema_payload(body.name, body.fields, body.tables)
    record = store.create_extraction_schema(
        project_id=project_id,
        name=body.name.strip(),
        document_type=body.document_type.strip() if isinstance(body.document_type, str) else None,
        fields=fields,
        tables=tables,
    )
    return _schema_record_to_out(record)


@router.get("/schemas/{schema_id}", response_model=ExtractionSchemaOut)
def get_schema(request: Request, schema_id: str) -> ExtractionSchemaOut:
    """Get extraction schema by ID."""
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)
    try:
        record = store.get_extraction_schema(schema_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Schema not found: {schema_id}")
    return _schema_record_to_out(record)


@router.put("/schemas/{schema_id}", response_model=ExtractionSchemaOut)
def update_schema(request: Request, schema_id: str, body: ExtractionSchemaUpdate) -> ExtractionSchemaOut:
    """Update extraction schema payload and increment version."""
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)
    try:
        store.get_extraction_schema(schema_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Schema not found: {schema_id}")

    fields, tables = _validate_schema_payload(body.name, body.fields, body.tables)
    record = store.update_extraction_schema(
        schema_id=schema_id,
        name=body.name.strip(),
        document_type=body.document_type.strip() if isinstance(body.document_type, str) else None,
        fields=fields,
        tables=tables,
    )
    return _schema_record_to_out(record)


# ---------------------------------------------------------------------------
# Jobs endpoints
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/jobs", response_model=list[JobOut])
def list_project_jobs(request: Request, project_id: str) -> list[JobOut]:
    """List jobs for a project."""
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)

    # Verify project exists
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
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)

    # Verify project exists
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

    # Verify schema exists (built-in or persisted)
    _load_schema_or_404(schema_id, db_path)

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
    db_path: Path = request.app.state.db_path
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


# ---------------------------------------------------------------------------
# Documents endpoints
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}/documents", response_model=list[DocumentOut])
def list_job_documents(request: Request, job_id: str) -> list[DocumentOut]:
    """List documents for a job."""
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)

    # Verify job exists
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
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)

    # Verify job exists and get project_id
    try:
        job = store.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    # Register document (does not process file)
    document_id = store.register_document(
        project_id=job.project_id,
        job_id=job_id,
        original_filename=body.original_filename,
        file_path=body.file_path,
        file_hash=body.file_hash,
        file_type=body.file_type,
        status=body.status,
    )

    # Retrieve and return
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
    db_path: Path = request.app.state.db_path
    runs_dir: Path = request.app.state.runs_dir
    store = SQLiteStore(db_path)

    # Verify job exists
    try:
        job = store.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    # Read uploaded content with bounded size
    max_upload_bytes = _request_max_upload_bytes(request)
    content = await _read_upload_with_limit(file, max_upload_bytes)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file cannot be empty")

    safe_name = _sanitize_upload_filename(file.filename)

    # Unique stored filename prevents overwrites
    stored_name = f"upload-{uuid.uuid4().hex}-{safe_name}"

    # Create upload directory
    upload_dir: Path = runs_dir / "uploads" / "jobs" / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    save_path = upload_dir / stored_name
    if not _is_path_within_root(save_path, upload_dir):
        raise HTTPException(status_code=400, detail="Unsafe upload filename path resolution")
    save_path.write_bytes(content)

    # Compute hash
    file_hash = hashlib.sha256(content).hexdigest()

    # Determine file type
    file_type: str | None = file.content_type or None
    if not file_type or file_type == "application/octet-stream":
        suffix = Path(safe_name).suffix.lstrip(".")
        file_type = suffix if suffix else None

    # Register document
    document_id = store.register_document(
        project_id=job.project_id,
        job_id=job_id,
        original_filename=safe_name,
        file_path=str(save_path),
        file_hash=file_hash,
        file_type=file_type,
        status=status,
    )

    # Retrieve and return
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
    db_path: Path = request.app.state.db_path
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
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)

    # Load document metadata
    try:
        doc = store.get_document(document_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    # Validate file path exists
    file_path = Path(doc["file_path"])
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Document file not found: {doc['file_path']}")

    # Determine content type
    content_type = doc.get("file_type") or "application/octet-stream"

    # Return file response with original filename for download
    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=doc["original_filename"],
    )


# ---------------------------------------------------------------------------
# Runs endpoints (metadata only, no extraction)
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}/runs", response_model=list[RunOut])
def list_job_runs(request: Request, job_id: str) -> list[RunOut]:
    """List runs for a job."""
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)

    # Verify job exists
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
    db_path: Path = request.app.state.db_path
    runs_dir: Path = request.app.state.runs_dir
    store = SQLiteStore(db_path)

    # Verify job exists and get schema_id and project_id
    try:
        job = store.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    # Create run with derived project_id and schema_id
    artifact_root = body.artifact_root
    if artifact_root:
        artifact_root = str(_validate_artifact_root_containment(runs_dir, artifact_root))

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
    db_path: Path = request.app.state.db_path
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
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)

    # Verify run exists
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
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)

    # Verify run exists
    try:
        run = store.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Verify document exists
    try:
        doc = store.get_document(body.document_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Document not found: {body.document_id}")

    # Verify document belongs to same job
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
        _load_schema_or_404(body.schema_id, db_path)

    # Create run_document mapping
    run_document_id = store.create_run_document(
        run_id,
        body.document_id,
        schema_id=body.schema_id,
        mode=body.mode,
        routing_reason=body.routing_reason,
    )

    # Update status if different from default
    if body.status != "processing":
        store.update_run_document_status(run_document_id, body.status)

    # Retrieve and return
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
    db_path: Path = request.app.state.db_path
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
        _load_schema_or_404(body.schema_id, db_path)

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


# ---------------------------------------------------------------------------
# Artifact indexing endpoints
# ---------------------------------------------------------------------------

@router.post("/runs/{run_id}/index-artifacts", response_model=ArtifactIndexResponse)
def index_run_artifacts(request: Request, run_id: str, body: ArtifactIndexRequest) -> ArtifactIndexResponse:
    """Index execution artifacts for a run into SQLite."""
    db_path: Path = request.app.state.db_path
    runs_dir: Path = request.app.state.runs_dir
    store = SQLiteStore(db_path)

    # Verify run exists
    try:
        run = store.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Determine artifact root
    artifact_root = body.artifact_root or run.artifact_root
    if not artifact_root:
        raise HTTPException(
            status_code=400,
            detail="artifact_root must be provided in request or stored in run record",
        )
    artifact_root = str(_validate_artifact_root_containment(runs_dir, artifact_root))

    # Index artifacts
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


# ---------------------------------------------------------------------------
# Run execution endpoints
# ---------------------------------------------------------------------------

@router.post("/runs/{run_id}/execute", response_model=ExecuteRunResponse)
def execute_run(request: Request, run_id: str, body: ExecuteRunRequest) -> ExecuteRunResponse:
    """Execute a run using existing project/job/document metadata."""
    from datetime import datetime

    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)
    runs_dir: Path = request.app.state.runs_dir

    # Step 1: Load run
    try:
        run = store.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Step 2: Check run status - reject if processing or completed
    if run.status == "processing":
        raise HTTPException(status_code=409, detail=f"Run is already processing")
    if run.status == "completed":
        raise HTTPException(status_code=409, detail=f"Run already completed; re-execution not supported in v0")

    # Step 3: Load job and project
    try:
        job = store.get_job(run.job_id)
        project = store.get_project(run.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Job or project not found: {str(e)}")

    # Step 4: Load run_documents
    run_docs = store.list_run_documents(run_id)
    if not run_docs:
        raise HTTPException(status_code=400, detail=f"Run {run_id} has no attached documents")

    # Step 5: Load documents and validate
    documents_dict = []
    for rd in run_docs:
        try:
            doc = store.get_document(rd["document_id"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Document {rd['document_id']} not found")

        # Verify document belongs to same job
        if doc["job_id"] != run.job_id:
            raise HTTPException(status_code=400, detail=f"Document {rd['document_id']} does not belong to job {run.job_id}")

        # Validate file exists
        doc_path = Path(doc["file_path"])
        if not doc_path.exists():
            raise HTTPException(status_code=400, detail=f"Document file not found: {doc['file_path']}")

        documents_dict.append(doc)

    # Step 6: Resolve artifact_root
    artifact_root = body.artifact_root or run.artifact_root
    if not artifact_root:
        artifact_root = str(runs_dir / "artifacts" / run_id)

    artifact_root_path = _validate_artifact_root_containment(runs_dir, artifact_root)
    artifact_root_path.mkdir(parents=True, exist_ok=True)
    artifact_root = str(artifact_root_path)

    # Persist artifact_root to run record
    store.update_run_artifact_root(run_id, artifact_root)

    # Step 7: Convert DB records to domain objects
    from docai_core.contracts.domain import Document, DocumentProfile, Job, Project

    project_obj = Project(
        project_id=project.project_id,
        name=project.name,
        description=project.description,
        created_at=datetime.fromisoformat(project.created_at),
        updated_at=datetime.fromisoformat(project.created_at),
    )

    job_obj = Job(
        job_id=job.job_id,
        project_id=job.project_id,
        schema_id=job.schema_id,
        name=job.name,
        run_type=job.job_type,
        status="processing",
        created_at=datetime.fromisoformat(job.created_at),
    )

    # Step 8: Validate execution configuration exists
    if not run.mode and not run.policy_id:
        raise HTTPException(status_code=400, detail="Run must have mode or policy_id set")

    # Step 9: Atomically claim run for processing
    if not store.claim_run_for_processing(run_id):
        latest = store.get_run(run_id)
        if latest.status == "processing":
            raise HTTPException(status_code=409, detail="Run is already processing")
        if latest.status == "completed":
            raise HTTPException(status_code=409, detail="Run already completed; re-execution not supported in v0")
        raise HTTPException(
            status_code=409,
            detail=f"Run status does not allow execution: {latest.status}",
        )

    # Step 10: Update run_document statuses to "processing"
    for rd in run_docs:
        store.update_run_document_status(rd["run_document_id"], "processing")

    # Step 11: Call JobRunService per document with effective schema/mode routing
    execution_errors = []
    result = None
    policies_used: set[str] = set()
    per_doc_generated_by: set[str] = set()
    any_stub = False
    try:
        artifact_store = ArtifactStore(artifact_root_path.parent)
        completed_count = 0

        for rd in run_docs:
            doc = next(item for item in documents_dict if item["document_id"] == rd["document_id"])
            override_schema_id = rd.get("schema_id")
            override_mode = rd.get("mode")
            routing_source = "document_override" if (override_schema_id or override_mode) else "run_default"
            effective_schema_id = override_schema_id or run.schema_id

            if override_mode is not None and override_mode not in _VALID_MODES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid override mode {override_mode!r} for document {doc['document_id']}. "
                           f"Valid modes: {sorted(_VALID_MODES)}",
                )

            effective_mode = override_mode if override_mode is not None else run.mode
            effective_policy_id = None if override_mode is not None else run.policy_id
            if effective_mode is None and effective_policy_id is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"No effective mode/policy for document {doc['document_id']}. "
                           f"Set run.mode or document override mode.",
                )

            schema = _load_schema_or_404(effective_schema_id, db_path)

            doc_obj = Document(
                document_id=doc["document_id"],
                job_id=run.job_id,
                original_filename=doc["original_filename"],
                file_path=doc["file_path"],
                status="processing",
                uploaded_at=datetime.fromisoformat(doc["created_at"]),
                profile=DocumentProfile(document_id=doc["document_id"]),
            )
            pipeline_config = _pipeline_config_for_request(effective_mode, effective_policy_id)
            doc_result = JobRunService(
                artifact_store=artifact_store,
                pipeline_config=pipeline_config,
            ).run_job(
                JobRunRequest(
                    project=project_obj,
                    schema=schema,
                    job=job_obj,
                    documents=[doc_obj],
                )
            )

            result = doc_result
            completed_count += doc_result.completed_count
            policies_used.update(doc_result.policies_used)
            per_doc_generated_by.add(doc_result.generated_by)
            any_stub = any_stub or doc_result.is_stub

            final_output_path = artifact_store.document_artifact_path(
                run.job_id,
                doc["document_id"],
                "final_output.json",
            )
            if final_output_path.exists():
                final_output = artifact_store.read_json(final_output_path)
                final_output["schema_id"] = effective_schema_id
                final_output["mode"] = effective_mode
                final_output["routing_source"] = routing_source
                routing_reason = rd.get("routing_reason")
                if routing_reason:
                    final_output["routing_reason"] = routing_reason
                elif "routing_reason" in final_output:
                    final_output.pop("routing_reason", None)
                artifact_store.write_json(final_output_path, final_output)

        result = ExecuteRunResponse(
            run_id=run_id,
            project_id=run.project_id,
            job_id=run.job_id,
            status="completed",
            artifact_root=str(artifact_store.job_dir(run.job_id)),
            document_count=len(run_docs),
            completed_count=completed_count,
            generated_by=(
                next(iter(per_doc_generated_by))
                if len(per_doc_generated_by) == 1
                else "mixed_document_modes_v1"
            ),
            is_stub=any_stub,
            artifacts_indexed=0,
            metrics_indexed=False,
            execution_errors=[],
            indexing_warnings=[],
            indexing_errors=[],
        )
    except HTTPException as e:
        execution_errors.append(str(e.detail))
        store.update_run_status(run_id, "failed")
        for rd in run_docs:
            store.update_run_document_status(rd["run_document_id"], "failed")
        raise
    except UnsupportedDocumentTypeError as e:
        execution_errors.append(str(e))
        store.update_run_status(run_id, "failed")
        for rd in run_docs:
            store.update_run_document_status(rd["run_document_id"], "failed")
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        execution_errors.append(str(e))
        store.update_run_status(run_id, "failed")
        for rd in run_docs:
            store.update_run_document_status(rd["run_document_id"], "failed")
        raise HTTPException(status_code=400, detail=str(e))
    except ImageOCRDependencyError as e:
        execution_errors.append(str(e))
        store.update_run_status(run_id, "failed")
        for rd in run_docs:
            store.update_run_document_status(rd["run_document_id"], "failed")
        raise HTTPException(status_code=424, detail=str(e))
    except Exception as e:
        execution_errors.append(str(e))
        store.update_run_status(run_id, "failed")
        for rd in run_docs:
            store.update_run_document_status(rd["run_document_id"], "failed")
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")

    # Step 11: Update run and run_document statuses to "completed"
    store.update_run_status(run_id, "completed", completed_at=store._now())
    for rd in run_docs:
        store.update_run_document_status(rd["run_document_id"], "completed", completed_at=store._now())

    # Step 12: Index artifacts if requested
    artifacts_indexed = 0
    metrics_indexed = False
    indexing_warnings = []
    indexing_errors = []

    if body.index_artifacts:
        indexer = ArtifactIndexer(store)
        index_result = indexer.index_run_artifacts(run_id, result.artifact_root)
        artifacts_indexed = index_result["artifacts_indexed"]
        metrics_indexed = index_result["metrics_indexed"]
        indexing_warnings = index_result["warnings"]
        indexing_errors = index_result["errors"]

    # Step 13: Return response
    return ExecuteRunResponse(
        run_id=run_id,
        project_id=run.project_id,
        job_id=run.job_id,
        status="completed",
        artifact_root=result.artifact_root,
        document_count=result.document_count,
        completed_count=result.completed_count,
        generated_by=result.generated_by,
        is_stub=result.is_stub,
        artifacts_indexed=artifacts_indexed,
        metrics_indexed=metrics_indexed,
        execution_errors=execution_errors,
        indexing_warnings=indexing_warnings,
        indexing_errors=indexing_errors,
    )


@router.post("/runs", response_model=RunResponse)
async def post_run(
    request: Request,
    mode: str | None = Form(None),
    policy_id: str | None = Form(None),
    schema_id: str | None = Form(None),
    files: list[UploadFile] = File(...),
) -> RunResponse:
    if mode is None and policy_id is None:
        raise HTTPException(400, "Provide mode or policy_id.")
    if mode is not None and mode not in _VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown mode {mode!r}. Valid modes: {sorted(_VALID_MODES)}",
        )

    try:
        extraction_schema = load_extraction_schema(schema_id or "invoice_basic")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    runs_dir: Path = request.app.state.runs_dir
    run_id = uuid.uuid4().hex[:12]

    upload_dir = runs_dir / "uploads" / run_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    max_upload_bytes = _request_max_upload_bytes(request)

    saved: list[Path] = []
    for upload in files:
        filename = _sanitize_upload_filename(upload.filename)
        stored_name = f"upload-{uuid.uuid4().hex}-{filename}"
        dest = upload_dir / stored_name
        if not _is_path_within_root(dest, upload_dir):
            raise HTTPException(status_code=400, detail="Unsafe upload filename path resolution")
        payload = await _read_upload_with_limit(upload, max_upload_bytes)
        if not payload:
            raise HTTPException(status_code=400, detail="Uploaded file cannot be empty")
        dest.write_bytes(payload)
        saved.append(dest)

    now = datetime.now(timezone.utc)
    project = Project(
        project_id="default",
        name="Default Project",
        description=None,
        created_at=now,
        updated_at=now,
    )
    job = Job(
        job_id=run_id,
        project_id="default",
        schema_id=extraction_schema.schema_id,
        name=f"run-{run_id}",
        run_type="training",
        status="queued",
        created_at=now,
    )
    documents = [
        Document(
            document_id=f"doc-{i}",
            job_id=run_id,
            original_filename=p.name,
            file_path=str(p),
            status="processing",
            uploaded_at=now,
            profile=DocumentProfile(document_id=f"doc-{i}"),
        )
        for i, p in enumerate(saved)
    ]

    store = ArtifactStore(runs_dir / "artifacts")
    result = JobRunService(
        artifact_store=store,
        pipeline_config=_pipeline_config_for_request(mode, policy_id),
    ).run_job(JobRunRequest(project=project, schema=extraction_schema, job=job, documents=documents))

    return RunResponse(
        run_id=run_id,
        job_id=result.job_id,
        is_stub=result.is_stub,
        generated_by=result.generated_by,
        document_count=result.document_count,
        completed_count=result.completed_count,
        artifact_root=result.artifact_root,
        policies_used=result.policies_used,
        note=result.note,
    )


@router.get("/runs/{run_id}/artifacts", response_model=ArtifactListResponse)
def get_run_artifacts(run_id: str, request: Request) -> ArtifactListResponse:
    _, _, job_dir, _ = _resolve_artifact_job_dir(request, run_id)
    artifacts = sorted(
        str(p.relative_to(job_dir)) for p in job_dir.rglob("*") if p.is_file()
    )
    return ArtifactListResponse(run_id=run_id, artifact_count=len(artifacts), artifacts=artifacts)


@router.get("/runs/{run_id}/documents/{doc_id}/final-output")
def get_final_output(run_id: str, doc_id: str, request: Request) -> dict[str, Any]:
    return _read_doc_artifact(request, run_id, doc_id, "final_output.json")


@router.get("/runs/{run_id}/documents/{doc_id}/validation-report")
def get_validation_report(run_id: str, doc_id: str, request: Request) -> dict[str, Any]:
    return _read_doc_artifact(request, run_id, doc_id, "validation_report.json")


@router.post("/runs/{run_id}/documents/{doc_id}/review-record", response_model=ReviewRecordOut)
def create_review_record(
    run_id: str,
    doc_id: str,
    body: ReviewRecordCreate,
    request: Request,
) -> ReviewRecordOut:
    store, run = _resolve_run_for_review(request, run_id)
    _ensure_run_document_mapping(store, run_id, doc_id)

    final_output = _read_doc_artifact(request, run_id, doc_id, "final_output.json")
    snapshot_by_field = _final_output_field_snapshot_by_name(final_output)
    corrections = _validate_and_build_corrections(body, snapshot_by_field)

    record = store.create_review_record(
        run_id=run_id,
        job_id=run.job_id,
        document_id=doc_id,
        schema_id=run.schema_id,
        review_status=body.review_status,
        reviewer_id=body.reviewer_id,
        review_note=body.review_note,
        source="human_review",
        corrections=corrections,
    )
    return ReviewRecordOut(**record)


@router.get("/runs/{run_id}/documents/{doc_id}/review-records", response_model=list[ReviewRecordOut])
def list_review_records(run_id: str, doc_id: str, request: Request) -> list[ReviewRecordOut]:
    store, _ = _resolve_run_for_review(request, run_id)
    _ensure_run_document_mapping(store, run_id, doc_id)
    records = store.list_review_records(run_id, doc_id)
    return [ReviewRecordOut(**record) for record in records]


@router.get("/runs/{run_id}/documents/{doc_id}/latest-review-record", response_model=ReviewRecordOut)
def get_latest_review_record(run_id: str, doc_id: str, request: Request) -> ReviewRecordOut:
    store, _ = _resolve_run_for_review(request, run_id)
    _ensure_run_document_mapping(store, run_id, doc_id)
    record = store.get_latest_review_record(run_id, doc_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No review records found for run={run_id} doc={doc_id}")
    return ReviewRecordOut(**record)


@router.get("/runs/{run_id}/learning-samples", response_model=LearningSampleListOut)
def list_learning_samples(run_id: str, request: Request) -> LearningSampleListOut:
    """Get learning samples derived from human review corrections for a run.

    Each correction in a review record becomes one learning sample for future
    training/evaluation. Samples are derived evidence only; no automatic
    training or model updates occur.

    Returns empty list if no reviews exist for the run.
    """
    from docai_core.api.schemas import LearningSampleOut

    store, _ = _resolve_run_for_review(request, run_id)

    # Get all review records for this run with corrections
    reviews = store.list_reviews_for_run(run_id)

    samples: list[LearningSampleOut] = []

    for review in reviews:
        review_id = review["review_id"]
        document_id = review["document_id"]
        corrections = review.get("corrections", [])

        for correction in corrections:
            correction_id = correction["correction_id"]
            field_name = correction["field_name"]
            extracted_value_snapshot = correction["extracted_value_snapshot"]
            corrected_value = correction["corrected_value"]
            decision = correction["decision"]
            evidence_text_snapshot = correction["evidence_text_snapshot"]
            validation_status_snapshot = correction["validation_status_snapshot"]
            created_at = correction["created_at"]

            sample = LearningSampleOut(
                sample_id=f"{review_id}_{correction_id}",
                run_id=run_id,
                document_id=document_id,
                review_id=review_id,
                field_name=field_name,
                decision=decision,
                original_value=extracted_value_snapshot,
                corrected_value=corrected_value,
                evidence_text=evidence_text_snapshot,
                validation_status=validation_status_snapshot,
                source="human_review",
                created_at=created_at,
            )
            samples.append(sample)

    return LearningSampleListOut(run_id=run_id, samples=samples)


@router.post("/advisory/recommend", response_model=AdvisoryResponse)
def advisory_recommend(body: AdvisoryRequest) -> AdvisoryResponse:
    """Read-only advisory endpoint.

    Accepts reviewed PolicyPerformanceRecord evidence and returns a policy
    recommendation. Does not mutate policies, create run artifacts, or affect
    runtime selection. Thompson Sampling / RABI / DAAF are not implemented here.
    """
    from docai_core.application.ahmn_advisory_service import (
        AHMNAdvisoryRequest,
        AHMNAdvisoryService,
    )
    from docai_core.metrics.policy_performance import PolicyPerformanceRecord

    records = [
        PolicyPerformanceRecord(
            policy_id=r.policy_id,
            policy_version=r.policy_version,
            document_type=r.document_type,
            quality_bin=r.quality_bin,
            document_count=r.document_count,
            field_accuracy=r.field_accuracy,
            field_precision=r.field_precision,
            field_recall=r.field_recall,
            field_f1=r.field_f1,
            missing_rate=r.missing_rate,
            correction_rate=r.correction_rate,
            evaluated_at=r.evaluated_at,
        )
        for r in body.records
    ]
    result = AHMNAdvisoryService().recommend(
        AHMNAdvisoryRequest(
            records=records,
            document_type=body.document_type,
            quality_bin=body.quality_bin,
            min_document_count=body.min_document_count,
        )
    )
    rec_out = None
    if result.recommendation is not None:
        rec = result.recommendation
        rec_out = AdvisoryRecommendationOut(
            policy_id=rec.policy_id,
            policy_version=rec.policy_version,
            document_type=rec.document_type,
            quality_bin=rec.quality_bin,
            score=rec.score,
            reason=rec.reason,
            evidence_document_count=rec.evidence_document_count,
            field_f1=rec.field_f1,
            field_accuracy=rec.field_accuracy,
            missing_rate=rec.missing_rate,
            correction_rate=rec.correction_rate,
        )
    return AdvisoryResponse(status=result.status, reason=result.reason, recommendation=rec_out)


@router.get("/projects/{project_id}/adaptive-routing/advice", response_model=AdaptiveRoutingAdviceOut)
def get_adaptive_routing_advice(
    project_id: str,
    request: Request,
    min_evidence: int = 10,
    strategy: str | None = None,
    apply_drift_decay: bool = True,
    half_life_days: int = 30,
) -> AdaptiveRoutingAdviceOut:
    """Get read-only Review-Based Adaptive Routing advice from reviewed evidence."""
    from docai_core.adaptive_routing.advisor import AdaptiveRoutingAdvisor
    from docai_core.adaptive_routing.advisor import ALLOWED_STRATEGIES
    from docai_core.adaptive_routing.evidence import collect_evidence_from_samples

    if strategy is not None and strategy not in ALLOWED_STRATEGIES:
        raise HTTPException(
            status_code=422,
            detail=f"strategy must be one of: {', '.join(sorted(ALLOWED_STRATEGIES))}",
        )

    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)

    # Check project exists
    try:
        store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    # Build review-derived learning samples at read time.
    all_runs = []
    for job in store.list_jobs(project_id):
        all_runs.extend(store.list_runs_for_job(job.job_id))
    all_learning_samples: list[dict[str, Any]] = []

    for run in all_runs:
        run_id = run.run_id
        reviews = store.list_reviews_for_run(run_id)
        run_schema_id = run.schema_id

        for review in reviews:
            review_id = review["review_id"]
            document_id = review["document_id"]
            corrections = review.get("corrections", [])
            for correction in corrections:
                all_learning_samples.append({
                    "sample_id": f"{review_id}_{correction['correction_id']}",
                    "run_id": run_id,
                    "document_id": document_id,
                    "review_id": review_id,
                    "field_name": correction.get("field_name", ""),
                    "decision": correction.get("decision", ""),
                    "schema_id": run_schema_id,
                    "created_at": correction.get("created_at"),
                })

    evidence = collect_evidence_from_samples(project_id, all_learning_samples)

    advisor = AdaptiveRoutingAdvisor(
        min_evidence=min_evidence,
        apply_drift_decay=apply_drift_decay,
        half_life_days=half_life_days,
    )
    advice = advisor.advise(evidence, strategy=strategy, evaluation_time=datetime.now(timezone.utc))

    recommendations = [
        AdaptiveRoutingRecommendationOut(
            recommendation_id=rec.recommendation_id,
            type=rec.type,
            severity=rec.severity,
            schema_id=rec.schema_id,
            field_name=rec.field_name,
            evidence_count=rec.evidence_count,
            correction_rate=rec.correction_rate,
            message=rec.message,
            suggested_action=rec.suggested_action,
            automatic_action_taken=rec.automatic_action_taken,
        )
        for rec in advice.recommendations
    ]

    return AdaptiveRoutingAdviceOut(
        project_id=advice.project_id,
        evidence_count=advice.evidence_count,
        minimum_required=advice.minimum_required,
        status=advice.status,
        generated_by=advice.generated_by,
        is_read_only=advice.is_read_only,
        automatic_action_taken=advice.automatic_action_taken,
        recommendations=recommendations,
        diagnostics=advice.diagnostics,
    )


def _extraction_profile_to_out(record: Any) -> ExtractionProfileOut:
    return ExtractionProfileOut(
        profile_id=record.profile_id,
        project_id=record.project_id,
        name=record.name,
        schema_id=record.schema_id,
        mode=record.mode,
        ocr_strategy=record.ocr_strategy,
        validation_level=record.validation_level,
        is_default=bool(record.is_default),
        created_from_advice_id=record.created_from_advice_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _schema_record_to_out(record: Any) -> ExtractionSchemaOut:
    parsed: dict[str, Any]
    try:
        parsed = json.loads(record.schema_json)
    except Exception:
        parsed = {}
    fields = parsed.get("fields")
    tables = parsed.get("tables")
    return ExtractionSchemaOut(
        schema_id=record.schema_id,
        project_id=record.project_id,
        name=record.name,
        document_type=record.document_type,
        version=record.version,
        fields=fields if isinstance(fields, list) else [],
        tables=tables if isinstance(tables, list) else [],
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _validate_schema_payload(
    schema_name: str,
    fields_in: list[Any],
    tables_in: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    name = schema_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Schema name must be non-empty")

    field_names: set[str] = set()
    fields_out: list[dict[str, Any]] = []
    for field in fields_in:
        item = field.model_dump() if hasattr(field, "model_dump") else dict(field)
        raw_name = item.get("name")
        field_name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not field_name:
            raise HTTPException(status_code=422, detail="Field name must be non-empty")
        folded = field_name.lower()
        if folded in field_names:
            raise HTTPException(status_code=422, detail=f"Duplicate field name: {field_name}")
        field_names.add(folded)
        item["name"] = field_name
        fields_out.append(item)

    table_names: set[str] = set()
    tables_out: list[dict[str, Any]] = []
    for table in tables_in:
        table_item = table.model_dump() if hasattr(table, "model_dump") else dict(table)
        raw_table_name = table_item.get("name")
        table_name = raw_table_name.strip() if isinstance(raw_table_name, str) else ""
        if not table_name:
            raise HTTPException(status_code=422, detail="Table name must be non-empty")
        folded_table = table_name.lower()
        if folded_table in table_names:
            raise HTTPException(status_code=422, detail=f"Duplicate table name: {table_name}")
        table_names.add(folded_table)
        table_item["name"] = table_name

        columns_value = table_item.get("columns")
        columns_in = columns_value if isinstance(columns_value, list) else []
        column_names: set[str] = set()
        columns_out: list[dict[str, Any]] = []
        for column in columns_in:
            column_item = column.model_dump() if hasattr(column, "model_dump") else dict(column)
            raw_column_name = column_item.get("name")
            column_name = raw_column_name.strip() if isinstance(raw_column_name, str) else ""
            if not column_name:
                raise HTTPException(status_code=422, detail=f"Column name must be non-empty in table {table_name}")
            folded_column = column_name.lower()
            if folded_column in column_names:
                raise HTTPException(
                    status_code=422,
                    detail=f"Duplicate column name {column_name} in table {table_name}",
                )
            column_names.add(folded_column)
            column_item["name"] = column_name
            columns_out.append(column_item)

        table_item["columns"] = columns_out
        tables_out.append(table_item)

    return fields_out, tables_out


def _resolve_run_for_review(request: Request, run_id: str) -> tuple[SQLiteStore, Any]:
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)
    try:
        run = store.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return store, run


def _ensure_run_document_mapping(store: SQLiteStore, run_id: str, doc_id: str) -> None:
    mapped = any(rd["document_id"] == doc_id for rd in store.list_run_documents(run_id))
    if not mapped:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} is not attached to run {run_id}")


def _final_output_field_snapshot_by_name(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fields = payload.get("fields")
    if not isinstance(fields, list):
        nested = payload.get("final_output")
        fields = nested.get("fields") if isinstance(nested, dict) else None
    if not isinstance(fields, list):
        return {}

    snapshots: dict[str, dict[str, Any]] = {}
    for item in fields:
        if not isinstance(item, dict):
            continue
        field_name = item.get("field_name")
        if isinstance(field_name, str) and field_name.strip():
            snapshots[field_name] = item
    return snapshots


def _snapshot_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return str(value)


def _validate_and_build_corrections(
    body: ReviewRecordCreate,
    snapshot_by_field: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if body.review_status not in _REVIEW_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"review_status must be one of: {', '.join(sorted(_REVIEW_STATUSES))}",
        )

    corrections: list[dict[str, Any]] = []
    for correction in body.corrections:
        field_name = correction.field_name.strip()
        decision = correction.decision.strip()
        corrected_value = correction.corrected_value.strip() if isinstance(correction.corrected_value, str) else None

        if not field_name:
            raise HTTPException(status_code=422, detail="field_name must be non-empty")
        if decision not in _REVIEW_DECISIONS:
            raise HTTPException(
                status_code=422,
                detail=f"decision must be one of: {', '.join(sorted(_REVIEW_DECISIONS))}",
            )

        if decision in {"wrong_value", "missed_field"} and not corrected_value:
            raise HTTPException(
                status_code=422,
                detail=f"corrected_value is required when decision is {decision}",
            )
        if decision in {"correct", "hallucinated_field", "correctly_skipped"} and corrected_value:
            raise HTTPException(
                status_code=422,
                detail=f"corrected_value must be empty when decision is {decision}",
            )
        if decision != "missed_field" and field_name not in snapshot_by_field:
            raise HTTPException(
                status_code=422,
                detail=f"field_name {field_name!r} was not found in final_output.fields",
            )

        snapshot = snapshot_by_field.get(field_name, {})
        corrections.append({
            "field_name": field_name,
            "extracted_value_snapshot": _snapshot_value(snapshot.get("value")),
            "corrected_value": corrected_value,
            "decision": decision,
            "evidence_text_snapshot": _snapshot_value(snapshot.get("evidence_text")),
            "validation_status_snapshot": _snapshot_value(snapshot.get("validation_status")),
        })
    return corrections


def _read_doc_artifact(
    request: Request, run_id: str, doc_id: str, filename: str
) -> dict[str, Any]:
    store = ArtifactStore(request.app.state.runs_dir / "artifacts")
    checked_keys = _artifact_run_keys(request, run_id)
    for key in checked_keys:
        path = store.document_artifact_path(key, doc_id, filename)
        if path.exists():
            return store.read_json(path)

    raise HTTPException(
        status_code=404,
        detail=(
            f"{filename} not found for run={run_id!r} doc={doc_id!r}. "
            f"Checked keys: {', '.join(checked_keys)}"
        ),
    )


def _artifact_run_keys(request: Request, run_id: str) -> list[str]:
    """Resolve artifact key candidates for a run.

    Legacy POST /runs writes artifacts under run_id without DB metadata.
    Newer execute flow writes artifacts under job_id while run_id is distinct.
    """
    keys = [run_id]
    db_path: Path = request.app.state.db_path
    store = SQLiteStore(db_path)
    try:
        run = store.get_run(run_id)
    except ValueError:
        return keys
    if run.job_id not in keys:
        keys.append(run.job_id)
    return keys


def _resolve_artifact_job_dir(
    request: Request, run_id: str
) -> tuple[ArtifactStore, str, Path, list[str]]:
    store = ArtifactStore(request.app.state.runs_dir / "artifacts")
    checked_keys = _artifact_run_keys(request, run_id)
    for key in checked_keys:
        job_dir = store.job_dir(key)
        if job_dir.exists():
            return store, key, job_dir, checked_keys
    raise HTTPException(
        status_code=404,
        detail=f"Run artifacts not found for run={run_id!r}. Checked keys: {', '.join(checked_keys)}",
    )

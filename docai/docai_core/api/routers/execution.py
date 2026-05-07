"""Run execution endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from docai_core.api.route_helpers import (
    get_db_path,
    get_runs_dir,
    load_schema_or_404,
    pipeline_config_for_request,
    read_upload_with_limit,
    request_max_upload_bytes,
    sanitize_upload_filename,
    is_path_within_root,
    validate_artifact_root_containment,
)
from docai_core.api.schemas import ExecuteRunRequest, ExecuteRunResponse, RunResponse
from docai_core.application.job_run_service import JobRunRequest, JobRunService
from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import Document, DocumentProfile, Job, Project
from docai_core.persistence import ArtifactIndexer, SQLiteStore
from docai_core.schemas import load_extraction_schema
from docai_core.text_acquisition.base import UnsupportedDocumentTypeError
from docai_core.text_acquisition.image_ocr_extractor import ImageOCRDependencyError

_VALID_MODES = frozenset({"stub", "local_text", "local_text_model"})

router = APIRouter()


@router.post("/runs/{run_id}/execute", response_model=ExecuteRunResponse)
def execute_run(request: Request, run_id: str, body: ExecuteRunRequest) -> ExecuteRunResponse:
    """Execute a run using existing project/job/document metadata."""
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    runs_dir: Path = get_runs_dir(request)

    try:
        run = store.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    if run.status == "processing":
        raise HTTPException(status_code=409, detail=f"Run is already processing")
    if run.status == "completed":
        raise HTTPException(status_code=409, detail=f"Run already completed; re-execution not supported in v0")

    try:
        job = store.get_job(run.job_id)
        project = store.get_project(run.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Job or project not found: {str(e)}")

    run_docs = store.list_run_documents(run_id)
    if not run_docs:
        raise HTTPException(status_code=400, detail=f"Run {run_id} has no attached documents")

    documents_dict = []
    for rd in run_docs:
        try:
            doc = store.get_document(rd["document_id"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Document {rd['document_id']} not found")

        if doc["job_id"] != run.job_id:
            raise HTTPException(status_code=400, detail=f"Document {rd['document_id']} does not belong to job {run.job_id}")

        doc_path = Path(doc["file_path"])
        if not doc_path.exists():
            raise HTTPException(status_code=400, detail=f"Document file not found: {doc['file_path']}")

        documents_dict.append(doc)

    artifact_root = body.artifact_root or run.artifact_root
    if not artifact_root:
        artifact_root = str(runs_dir / "artifacts" / run_id)

    artifact_root_path = validate_artifact_root_containment(runs_dir, artifact_root)
    artifact_root_path.mkdir(parents=True, exist_ok=True)
    artifact_root = str(artifact_root_path)

    store.update_run_artifact_root(run_id, artifact_root)

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

    if not run.mode and not run.policy_id:
        raise HTTPException(status_code=400, detail="Run must have mode or policy_id set")

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

    for rd in run_docs:
        store.update_run_document_status(rd["run_document_id"], "processing")

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

            schema = load_schema_or_404(effective_schema_id, db_path)

            doc_obj = Document(
                document_id=doc["document_id"],
                job_id=run.job_id,
                original_filename=doc["original_filename"],
                file_path=doc["file_path"],
                status="processing",
                uploaded_at=datetime.fromisoformat(doc["created_at"]),
                profile=DocumentProfile(document_id=doc["document_id"]),
            )
            pipeline_config = pipeline_config_for_request(effective_mode, effective_policy_id)
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

    store.update_run_status(run_id, "completed", completed_at=store._now())
    for rd in run_docs:
        store.update_run_document_status(rd["run_document_id"], "completed", completed_at=store._now())

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
    """Execute a quick run (legacy endpoint)."""
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

    runs_dir: Path = get_runs_dir(request)
    run_id = uuid.uuid4().hex[:12]

    upload_dir = runs_dir / "uploads" / run_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    max_upload_bytes = request_max_upload_bytes(request)

    saved: list[Path] = []
    for upload in files:
        filename = sanitize_upload_filename(upload.filename)
        stored_name = f"upload-{uuid.uuid4().hex}-{filename}"
        dest = upload_dir / stored_name
        if not is_path_within_root(dest, upload_dir):
            raise HTTPException(status_code=400, detail="Unsafe upload filename path resolution")
        payload = await read_upload_with_limit(upload, max_upload_bytes)
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
        pipeline_config=pipeline_config_for_request(mode, policy_id),
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

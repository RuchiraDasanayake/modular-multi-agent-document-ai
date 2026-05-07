"""Shared route helpers and validation utilities."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, UploadFile

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


def get_db_path(request: Request) -> Path:
    """Extract db_path from request context."""
    return request.app.state.db_path


def get_runs_dir(request: Request) -> Path:
    """Extract runs_dir from request context."""
    return request.app.state.runs_dir


def request_max_upload_bytes(request: Request) -> int:
    """Get configured max upload size from request state."""
    max_bytes = getattr(request.app.state, "max_upload_bytes", _DEFAULT_MAX_UPLOAD_BYTES)
    try:
        value = int(max_bytes)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_UPLOAD_BYTES
    return value if value > 0 else _DEFAULT_MAX_UPLOAD_BYTES


async def read_upload_with_limit(upload: UploadFile, max_upload_bytes: int) -> bytes:
    """Read uploaded file in chunks with size limit."""
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


def sanitize_upload_filename(filename: str | None) -> str:
    """Sanitize uploaded filename for safe filesystem storage."""
    raw_name = (filename or "").strip()
    safe_name = Path(raw_name.replace("\\", "/")).name
    if safe_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Uploaded filename is missing or unsafe")
    return safe_name


def is_path_within_root(path: Path, allowed_root: Path) -> bool:
    """Check if path is contained within allowed_root."""
    try:
        path.resolve().relative_to(allowed_root.resolve())
        return True
    except ValueError:
        return False


def validate_artifact_root_containment(
    runs_dir: Path,
    artifact_root: str,
) -> Path:
    """Validate artifact_root is within runs_dir; raise 400 if not."""
    artifact_root_path = Path(artifact_root).resolve()
    if not is_path_within_root(artifact_root_path, runs_dir):
        raise HTTPException(
            status_code=400,
            detail=(
                f"artifact_root must stay under runs_dir {runs_dir.resolve()}; "
                f"got {artifact_root_path}"
            ),
        )
    return artifact_root_path


def model_plugin_for_env():
    """Get configured model plugin from environment."""
    p = os.getenv("DOCAI_MODEL_PROVIDER", "").lower().strip()
    if p not in ("", "stub", "ollama"):
        raise HTTPException(400, f"DOCAI_MODEL_PROVIDER={p!r} unknown. Valid: stub, ollama.")
    if p != "ollama":
        from docai_core.plugins.models.stub_model_plugin import StubModelPlugin
        return StubModelPlugin()
    from docai_core.plugins.models.qwen_model_plugin import QwenModelPlugin
    b = os.getenv("DOCAI_OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    m = os.getenv("DOCAI_OLLAMA_MODEL", "qwen")
    t = int(os.getenv("DOCAI_OLLAMA_TIMEOUT_SECONDS", "60"))
    return QwenModelPlugin(model_name=m, endpoint_url=f"{b}/api/generate", timeout_seconds=t)


def pipeline_config(mode: str):
    """Build pipeline config for mode."""
    from docai_core.extraction.qwen_extraction_step import QwenExtractionStep
    from docai_core.orchestration.pipeline_factory import (
        build_local_text_pipeline,
        build_model_pipeline,
        build_stub_pipeline,
    )

    if mode == "stub":
        return build_stub_pipeline()
    if mode == "local_text":
        return build_local_text_pipeline()
    return build_model_pipeline(model_step=QwenExtractionStep(model_plugin=model_plugin_for_env()))


def pipeline_config_for_request(
    mode: str | None,
    policy_id: str | None,
):
    """Resolve pipeline config from mode or policy_id."""
    from docai_core.orchestration.pipeline_factory import build_pipeline_for_policy

    if policy_id is not None:
        try:
            return build_pipeline_for_policy(policy_id)
        except ValueError:
            raise HTTPException(400, f"Unknown policy_id {policy_id!r}.")
    if mode is not None:
        return pipeline_config(mode)
    raise HTTPException(400, "Provide mode or policy_id.")


def load_schema_or_404(schema_id: str, db_path: Path):
    """Load schema from built-in configs or SQLite; raise 404 if not found."""
    from docai_core.schemas.schema_loader import load_schema_for_execution
    try:
        return load_schema_for_execution(schema_id, db_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def extraction_profile_to_out(record: Any):
    """Convert DB extraction profile record to output schema."""
    from docai_core.api.schemas import ExtractionProfileOut
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


def schema_record_to_out(record: Any):
    """Convert DB schema record to output schema."""
    from docai_core.api.schemas import ExtractionSchemaOut
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


def validate_schema_payload(
    schema_name: str,
    fields_in: list[Any],
    tables_in: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate and normalize schema fields and tables."""
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


def final_output_field_snapshot_by_name(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract field snapshots from final_output payload."""
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


def snapshot_value(value: Any) -> str | None:
    """Convert value to snapshot string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return str(value)


def validate_and_build_corrections(
    body,
    snapshot_by_field: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate review corrections and build standardized records."""
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
            "extracted_value_snapshot": snapshot_value(snapshot.get("value")),
            "corrected_value": corrected_value,
            "decision": decision,
            "evidence_text_snapshot": snapshot_value(snapshot.get("evidence_text")),
            "validation_status_snapshot": snapshot_value(snapshot.get("validation_status")),
        })
    return corrections


def resolve_run_for_review(request: Request, run_id: str) -> tuple:
    """Load run for review endpoint; raise 404 if not found."""
    from docai_core.persistence import SQLiteStore
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    try:
        run = store.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return store, run


def ensure_run_document_mapping(store, run_id: str, doc_id: str) -> None:
    """Verify document is attached to run; raise 404 if not."""
    mapped = any(rd["document_id"] == doc_id for rd in store.list_run_documents(run_id))
    if not mapped:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} is not attached to run {run_id}")


def read_doc_artifact(
    request: Request, run_id: str, doc_id: str, filename: str
) -> dict[str, Any]:
    """Read artifact JSON for a document in a run."""
    from docai_core.artifacts.store import ArtifactStore
    store = ArtifactStore(get_runs_dir(request) / "artifacts")
    checked_keys = artifact_run_keys(request, run_id)
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


def artifact_run_keys(request: Request, run_id: str) -> list[str]:
    """Resolve artifact key candidates for a run.

    Legacy POST /runs writes artifacts under run_id without DB metadata.
    Newer execute flow writes artifacts under job_id while run_id is distinct.
    """
    from docai_core.persistence import SQLiteStore
    keys = [run_id]
    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)
    try:
        run = store.get_run(run_id)
    except ValueError:
        return keys
    if run.job_id not in keys:
        keys.append(run.job_id)
    return keys


def resolve_artifact_job_dir(
    request: Request, run_id: str
) -> tuple:
    """Resolve artifact job directory for run; raise 404 if not found."""
    from docai_core.artifacts.store import ArtifactStore
    store = ArtifactStore(get_runs_dir(request) / "artifacts")
    checked_keys = artifact_run_keys(request, run_id)
    for key in checked_keys:
        job_dir = store.job_dir(key)
        if job_dir.exists():
            return store, key, job_dir, checked_keys
    raise HTTPException(
        status_code=404,
        detail=f"Run artifacts not found for run={run_id!r}. Checked keys: {', '.join(checked_keys)}",
    )

"""SQLite persistence store for DocAI v2 platform.

Simple append-only evidence/control-plane store. No business logic, no ORM.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ProjectRecord:
    project_id: str
    name: str
    description: str | None
    status: str
    created_at: str


@dataclass(slots=True)
class JobRecord:
    job_id: str
    project_id: str
    schema_id: str
    profile_id: str | None
    default_mode: str | None
    name: str
    job_type: str
    status: str
    created_at: str


@dataclass(slots=True)
class ExtractionSchemaRecord:
    schema_id: str
    project_id: str
    name: str
    document_type: str | None
    version: int
    schema_json: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class RunRecord:
    run_id: str
    project_id: str
    job_id: str
    schema_id: str
    policy_id: str | None
    mode: str | None
    run_type: str
    status: str
    artifact_root: str | None
    created_at: str
    completed_at: str | None


@dataclass(slots=True)
class ExtractionProfileRecord:
    profile_id: str
    project_id: str
    name: str
    schema_id: str
    mode: str
    ocr_strategy: str
    validation_level: str
    is_default: int
    created_from_advice_id: str | None
    created_at: str
    updated_at: str


def ensure_database_schema(db_path: Path) -> None:
    """Ensure SQLite database has current schema applied (idempotent)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_file = Path(__file__).parent / "schema.sql"
    with open(schema_file, "r") as f:
        schema = f.read()

    with sqlite3.connect(db_path) as conn:
        # Pre-migrate legacy jobs table before schema indexes are applied.
        _ensure_job_profile_columns(conn)
        conn.executescript(schema)
        _ensure_job_profile_columns(conn)
        _ensure_run_document_routing_columns(conn)
        conn.commit()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row[1]) == column_name for row in rows)


def _ensure_run_document_routing_columns(conn: sqlite3.Connection) -> None:
    # Idempotent column upgrades for older databases.
    if not _column_exists(conn, "run_documents", "schema_id"):
        conn.execute("ALTER TABLE run_documents ADD COLUMN schema_id TEXT")
    if not _column_exists(conn, "run_documents", "mode"):
        conn.execute("ALTER TABLE run_documents ADD COLUMN mode TEXT")
    if not _column_exists(conn, "run_documents", "routing_reason"):
        conn.execute("ALTER TABLE run_documents ADD COLUMN routing_reason TEXT")


def _ensure_job_profile_columns(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "jobs"):
        return
    if not _column_exists(conn, "jobs", "profile_id"):
        conn.execute("ALTER TABLE jobs ADD COLUMN profile_id TEXT")
    if not _column_exists(conn, "jobs", "default_mode"):
        conn.execute("ALTER TABLE jobs ADD COLUMN default_mode TEXT")


class SQLiteStore:
    """Simple SQLite persistence store."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        ensure_database_schema(self.db_path)

    def _conn(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _now(self) -> str:
        """ISO timestamp."""
        return datetime.now(timezone.utc).isoformat()

    def _hash_json(self, obj: Any) -> str:
        """Hash JSON payload."""
        json_str = json.dumps(obj, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()

    # Projects
    def create_project(self, project_id: str, name: str, description: str | None = None) -> ProjectRecord:
        """Create a project."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO projects (project_id, name, description, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (project_id, name, description, "active", self._now()),
            )
            conn.commit()
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> ProjectRecord:
        """Get a project."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        if not row:
            raise ValueError(f"Project not found: {project_id}")
        return ProjectRecord(**dict(row))

    def list_projects(self) -> list[ProjectRecord]:
        """List all projects."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [ProjectRecord(**dict(row)) for row in rows]

    # Extraction Schemas
    def create_extraction_schema(
        self,
        project_id: str,
        name: str,
        document_type: str | None,
        fields: list[dict[str, Any]],
        tables: list[dict[str, Any]],
    ) -> ExtractionSchemaRecord:
        """Create an extraction schema for a project."""
        schema_id = f"schema-{uuid.uuid4().hex[:12]}"
        now = self._now()
        schema_json = json.dumps({"fields": fields, "tables": tables}, ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO extraction_schemas (schema_id, project_id, name, document_type, version, schema_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (schema_id, project_id, name, document_type, 1, schema_json, now, now),
            )
            conn.commit()
        return self.get_extraction_schema(schema_id)

    def list_extraction_schemas(self, project_id: str) -> list[ExtractionSchemaRecord]:
        """List extraction schemas for one project, newest updated first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM extraction_schemas WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        return [ExtractionSchemaRecord(**dict(row)) for row in rows]

    def get_extraction_schema(self, schema_id: str) -> ExtractionSchemaRecord:
        """Get extraction schema by ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM extraction_schemas WHERE schema_id = ?",
                (schema_id,),
            ).fetchone()
        if not row:
            raise ValueError(f"Extraction schema not found: {schema_id}")
        return ExtractionSchemaRecord(**dict(row))

    def update_extraction_schema(
        self,
        schema_id: str,
        name: str,
        document_type: str | None,
        fields: list[dict[str, Any]],
        tables: list[dict[str, Any]],
    ) -> ExtractionSchemaRecord:
        """Update extraction schema payload and increment version."""
        current = self.get_extraction_schema(schema_id)
        next_version = current.version + 1
        now = self._now()
        schema_json = json.dumps({"fields": fields, "tables": tables}, ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                "UPDATE extraction_schemas SET name = ?, document_type = ?, version = ?, schema_json = ?, updated_at = ? WHERE schema_id = ?",
                (name, document_type, next_version, schema_json, now, schema_id),
            )
            conn.commit()
        return self.get_extraction_schema(schema_id)

    # Jobs
    def create_job(
        self,
        project_id: str,
        schema_id: str,
        name: str,
        job_type: str = "training",
        profile_id: str | None = None,
        default_mode: str | None = None,
    ) -> JobRecord:
        """Create a job."""
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, project_id, schema_id, profile_id, default_mode, name, job_type, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (job_id, project_id, schema_id, profile_id, default_mode, name, job_type, "queued", self._now()),
            )
            conn.commit()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> JobRecord:
        """Get a job."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            raise ValueError(f"Job not found: {job_id}")
        return JobRecord(**dict(row))

    def list_jobs(self, project_id: str) -> list[JobRecord]:
        """List jobs by project."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC", (project_id,)
            ).fetchall()
        return [JobRecord(**dict(row)) for row in rows]

    # Extraction Profiles
    def create_extraction_profile(
        self,
        project_id: str,
        name: str,
        schema_id: str,
        mode: str,
        ocr_strategy: str,
        validation_level: str,
        is_default: int = 0,
        created_from_advice_id: str | None = None,
    ) -> ExtractionProfileRecord:
        profile_id = f"profile-{uuid.uuid4().hex[:12]}"
        now = self._now()
        with self._conn() as conn:
            if is_default:
                conn.execute(
                    "UPDATE extraction_profiles SET is_default = 0 WHERE project_id = ?",
                    (project_id,),
                )
            conn.execute(
                "INSERT INTO extraction_profiles (profile_id, project_id, name, schema_id, mode, ocr_strategy, validation_level, is_default, created_from_advice_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    profile_id,
                    project_id,
                    name,
                    schema_id,
                    mode,
                    ocr_strategy,
                    validation_level,
                    1 if is_default else 0,
                    created_from_advice_id,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get_extraction_profile(profile_id)

    def list_extraction_profiles(self, project_id: str) -> list[ExtractionProfileRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM extraction_profiles WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [ExtractionProfileRecord(**dict(row)) for row in rows]

    def get_extraction_profile(self, profile_id: str) -> ExtractionProfileRecord:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM extraction_profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        if not row:
            raise ValueError(f"Extraction profile not found: {profile_id}")
        return ExtractionProfileRecord(**dict(row))

    def update_extraction_profile(
        self,
        profile_id: str,
        name: str,
        schema_id: str,
        mode: str,
        ocr_strategy: str,
        validation_level: str,
        is_default: int,
        created_from_advice_id: str | None = None,
    ) -> ExtractionProfileRecord:
        existing = self.get_extraction_profile(profile_id)
        now = self._now()
        with self._conn() as conn:
            if is_default:
                conn.execute(
                    "UPDATE extraction_profiles SET is_default = 0 WHERE project_id = ?",
                    (existing.project_id,),
                )
            conn.execute(
                "UPDATE extraction_profiles SET name = ?, schema_id = ?, mode = ?, ocr_strategy = ?, validation_level = ?, is_default = ?, created_from_advice_id = ?, updated_at = ? WHERE profile_id = ?",
                (
                    name,
                    schema_id,
                    mode,
                    ocr_strategy,
                    validation_level,
                    1 if is_default else 0,
                    created_from_advice_id,
                    now,
                    profile_id,
                ),
            )
            conn.commit()
        return self.get_extraction_profile(profile_id)

    # Documents
    def create_document(
        self, project_id: str, job_id: str, original_filename: str, file_path: str,
        file_type: str | None = None,
    ) -> str:
        """Create a document record. Returns document_id."""
        document_id = f"doc-{uuid.uuid4().hex[:12]}"
        file_hash = hashlib.sha256(Path(file_path).read_bytes()).hexdigest() if Path(file_path).exists() else None

        with self._conn() as conn:
            conn.execute(
                "INSERT INTO documents (document_id, project_id, job_id, original_filename, file_path, file_hash, file_type, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (document_id, project_id, job_id, original_filename, file_path, file_hash, file_type, "uploaded", self._now()),
            )
            conn.commit()
        return document_id

    def get_document(self, document_id: str) -> dict[str, Any]:
        """Get a document."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()
        if not row:
            raise ValueError(f"Document not found: {document_id}")
        return dict(row)

    def register_document(
        self, project_id: str, job_id: str, original_filename: str, file_path: str,
        file_hash: str | None = None, file_type: str | None = None, status: str = "registered",
    ) -> str:
        """Register a document metadata record without processing the file. Returns document_id."""
        document_id = f"doc-{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO documents (document_id, project_id, job_id, original_filename, file_path, file_hash, file_type, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (document_id, project_id, job_id, original_filename, file_path, file_hash, file_type, status, self._now()),
            )
            conn.commit()
        return document_id

    def list_documents_for_job(self, job_id: str) -> list[dict[str, Any]]:
        """List all documents for a job."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM documents WHERE job_id = ?", (job_id,)).fetchall()
        return [dict(row) for row in rows]

    # Runs
    def create_run(
        self, project_id: str, job_id: str, schema_id: str, run_type: str = "training",
        policy_id: str | None = None, mode: str | None = None, artifact_root: str | None = None,
        status: str = "created",
    ) -> RunRecord:
        """Create a run."""
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO runs (run_id, project_id, job_id, schema_id, policy_id, mode, run_type, status, artifact_root, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, project_id, job_id, schema_id, policy_id, mode, run_type, status, artifact_root, self._now()),
            )
            conn.commit()
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> RunRecord:
        """Get a run."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            raise ValueError(f"Run not found: {run_id}")
        return RunRecord(**dict(row))

    def update_run_status(self, run_id: str, status: str, completed_at: str | None = None) -> None:
        """Update run status."""
        with self._conn() as conn:
            if completed_at:
                conn.execute("UPDATE runs SET status = ?, completed_at = ? WHERE run_id = ?",
                           (status, completed_at, run_id))
            else:
                conn.execute("UPDATE runs SET status = ? WHERE run_id = ?", (status, run_id))
            conn.commit()

    def update_run_artifact_root(self, run_id: str, artifact_root: str) -> None:
        """Update run artifact_root."""
        with self._conn() as conn:
            conn.execute("UPDATE runs SET artifact_root = ? WHERE run_id = ?", (artifact_root, run_id))
            conn.commit()

    def claim_run_for_processing(self, run_id: str) -> bool:
        """Atomically claim a run for execution by setting status to processing once."""
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE runs SET status = ? WHERE run_id = ? AND status NOT IN (?, ?)",
                ("processing", run_id, "processing", "completed"),
            )
            conn.commit()
            return cursor.rowcount > 0

    # Run documents
    def create_run_document(
        self,
        run_id: str,
        document_id: str,
        schema_id: str | None = None,
        mode: str | None = None,
        routing_reason: str | None = None,
    ) -> str:
        """Create a run_document record. Returns run_document_id."""
        run_document_id = f"rd-{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO run_documents (run_document_id, run_id, document_id, schema_id, mode, routing_reason, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_document_id, run_id, document_id, schema_id, mode, routing_reason, "pending", self._now()),
            )
            conn.commit()
        return run_document_id

    def update_run_document_status(self, run_document_id: str, status: str, completed_at: str | None = None) -> None:
        """Update run_document status."""
        with self._conn() as conn:
            if completed_at:
                conn.execute("UPDATE run_documents SET status = ?, completed_at = ? WHERE run_document_id = ?",
                           (status, completed_at, run_document_id))
            else:
                conn.execute("UPDATE run_documents SET status = ? WHERE run_document_id = ?", (status, run_document_id))
            conn.commit()

    def list_runs_for_job(self, job_id: str) -> list[RunRecord]:
        """List all runs for a job."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM runs WHERE job_id = ?", (job_id,)).fetchall()
        return [RunRecord(**dict(row)) for row in rows]

    def list_run_documents(self, run_id: str) -> list[dict[str, Any]]:
        """List all run_documents for a run."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM run_documents WHERE run_id = ?", (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_run_document(self, run_document_id: str) -> dict[str, Any]:
        """Get a run_document."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM run_documents WHERE run_document_id = ?", (run_document_id,)).fetchone()
        if not row:
            raise ValueError(f"Run document not found: {run_document_id}")
        return dict(row)

    def get_run_document_by_run_and_document(self, run_id: str, document_id: str) -> dict[str, Any]:
        """Get run_document mapping for a run/document pair."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM run_documents WHERE run_id = ? AND document_id = ? ORDER BY created_at DESC LIMIT 1",
                (run_id, document_id),
            ).fetchone()
        if not row:
            raise ValueError(f"Run document not found: run={run_id}, document={document_id}")
        return dict(row)

    def update_run_document_routing(
        self,
        run_id: str,
        document_id: str,
        schema_id: str | None,
        mode: str | None,
        routing_reason: str | None,
    ) -> None:
        """Update schema/mode routing override for a run/document mapping."""
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE run_documents SET schema_id = ?, mode = ?, routing_reason = ? WHERE run_id = ? AND document_id = ?",
                (schema_id, mode, routing_reason, run_id, document_id),
            )
            if cursor.rowcount <= 0:
                raise ValueError(f"Run document not found: run={run_id}, document={document_id}")
            conn.commit()

    # Run artifacts (append-only)
    def add_run_artifact(
        self, run_id: str, document_id: str | None, artifact_type: str, schema_version: str,
        payload: dict[str, Any] | None = None, file_path: str | None = None,
    ) -> str:
        """Add a run artifact. Always creates new record (append-only). Returns artifact_id."""
        artifact_id = f"art-{uuid.uuid4().hex[:12]}"
        payload_json = None
        payload_hash = None
        if payload:
            payload_json = json.dumps(payload, default=str)
            payload_hash = self._hash_json(payload)

        with self._conn() as conn:
            conn.execute(
                "INSERT INTO run_artifacts (artifact_id, run_id, document_id, artifact_type, schema_version, payload_json, payload_hash, file_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, run_id, document_id, artifact_type, schema_version, payload_json, payload_hash, file_path, self._now()),
            )
            conn.commit()
        return artifact_id

    def list_run_artifacts(self, run_id: str, document_id: str | None = None, artifact_type: str | None = None) -> list[dict[str, Any]]:
        """List run artifacts (append-only: all versions returned)."""
        with self._conn() as conn:
            if document_id and artifact_type:
                rows = conn.execute(
                    "SELECT * FROM run_artifacts WHERE run_id = ? AND document_id = ? AND artifact_type = ? ORDER BY created_at ASC",
                    (run_id, document_id, artifact_type),
                ).fetchall()
            elif document_id:
                rows = conn.execute(
                    "SELECT * FROM run_artifacts WHERE run_id = ? AND document_id = ? ORDER BY created_at ASC",
                    (run_id, document_id),
                ).fetchall()
            elif artifact_type:
                rows = conn.execute(
                    "SELECT * FROM run_artifacts WHERE run_id = ? AND artifact_type = ? ORDER BY created_at ASC",
                    (run_id, artifact_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM run_artifacts WHERE run_id = ? ORDER BY created_at ASC",
                    (run_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    # Metrics (append-only)
    def add_document_metrics_index(
        self, project_id: str, job_id: str, run_id: str, document_id: str, schema_id: str,
        evidence_source: str, is_human_review: int, policy_id: str | None = None,
        field_precision: float | None = None, field_recall: float | None = None,
        field_f1: float | None = None, accuracy: float | None = None,
        missing_rate: float | None = None, correction_rate: float | None = None,
        metrics_artifact_id: str | None = None,
    ) -> str:
        """Add document metrics. Always creates new record (append-only). Returns metrics_id."""
        metrics_id = f"metrics-{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO document_metrics_index (metrics_id, project_id, job_id, run_id, document_id, schema_id, policy_id, evidence_source, is_human_review, field_precision, field_recall, field_f1, accuracy, missing_rate, correction_rate, metrics_artifact_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (metrics_id, project_id, job_id, run_id, document_id, schema_id, policy_id, evidence_source, is_human_review, field_precision, field_recall, field_f1, accuracy, missing_rate, correction_rate, metrics_artifact_id, self._now()),
            )
            conn.commit()
        return metrics_id

    def list_document_metrics(self, run_id: str, document_id: str | None = None) -> list[dict[str, Any]]:
        """List document metrics for a run or document."""
        with self._conn() as conn:
            if document_id:
                rows = conn.execute(
                    "SELECT * FROM document_metrics_index WHERE run_id = ? AND document_id = ? ORDER BY created_at DESC",
                    (run_id, document_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM document_metrics_index WHERE run_id = ? ORDER BY created_at DESC",
                    (run_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    # Field results (append-only)
    def add_field_result(
        self, project_id: str, job_id: str, run_id: str, document_id: str, schema_id: str,
        field_name: str, evidence_source: str, is_human_review: int,
        policy_id: str | None = None, expected_value: str | None = None,
        extracted_value: str | None = None, is_correct: int | None = None,
        is_missing: int | None = None, is_grounded: int | None = None,
        confidence: float | None = None, extraction_method: str | None = None,
    ) -> str:
        """Add field result. Always creates new record (append-only). Returns field_result_id."""
        field_result_id = f"fr-{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO field_results (field_result_id, project_id, job_id, run_id, document_id, schema_id, policy_id, field_name, expected_value, extracted_value, is_correct, is_missing, is_grounded, confidence, extraction_method, evidence_source, is_human_review, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (field_result_id, project_id, job_id, run_id, document_id, schema_id, policy_id, field_name, expected_value, extracted_value, is_correct, is_missing, is_grounded, confidence, extraction_method, evidence_source, is_human_review, self._now()),
            )
            conn.commit()
        return field_result_id

    def list_field_results(self, document_id: str) -> list[dict[str, Any]]:
        """List field results for a document."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM field_results WHERE document_id = ? ORDER BY created_at DESC",
                (document_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # Project metrics (chart-ready query)
    def list_project_metrics(self, project_id: str) -> list[dict[str, Any]]:
        """List project metrics for charts. Returns latest metrics per (schema, policy)."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT
                    dmi.schema_id,
                    dmi.policy_id,
                    dmi.evidence_source,
                    dmi.is_human_review,
                    COUNT(DISTINCT dmi.document_id) as document_count,
                    AVG(dmi.accuracy) as avg_accuracy,
                    AVG(dmi.field_f1) as avg_field_f1,
                    AVG(dmi.field_precision) as avg_field_precision,
                    AVG(dmi.field_recall) as avg_field_recall,
                    AVG(dmi.missing_rate) as avg_missing_rate,
                    AVG(dmi.correction_rate) as avg_correction_rate,
                    MAX(dmi.created_at) as last_updated
                FROM document_metrics_index dmi
                WHERE dmi.project_id = ?
                GROUP BY dmi.schema_id, dmi.policy_id, dmi.evidence_source, dmi.is_human_review
                ORDER BY dmi.created_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # Events
    def add_run_event(
        self, run_id: str, event_type: str, message: str | None = None,
        document_id: str | None = None, payload: dict[str, Any] | None = None,
    ) -> str:
        """Add a run event. Returns event_id."""
        event_id = f"evt-{uuid.uuid4().hex[:12]}"
        payload_json = json.dumps(payload, default=str) if payload else None
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO run_events (event_id, run_id, document_id, event_type, message, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, run_id, document_id, event_type, message, payload_json, self._now()),
            )
            conn.commit()
        return event_id

    def list_run_events(self, run_id: str, document_id: str | None = None) -> list[dict[str, Any]]:
        """List run events."""
        with self._conn() as conn:
            if document_id:
                rows = conn.execute(
                    "SELECT * FROM run_events WHERE run_id = ? AND document_id = ? ORDER BY created_at ASC",
                    (run_id, document_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM run_events WHERE run_id = ? ORDER BY created_at ASC",
                    (run_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    # Review records (append-only)
    def create_review_record(
        self,
        run_id: str,
        job_id: str,
        document_id: str,
        schema_id: str | None,
        review_status: str,
        reviewer_id: str | None,
        review_note: str | None,
        source: str,
        corrections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create immutable review record with correction rows in one transaction."""
        review_id = f"review-{uuid.uuid4().hex[:12]}"
        created_at = self._now()

        stored_corrections: list[dict[str, Any]] = []
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO review_records (review_id, run_id, job_id, document_id, schema_id, review_status, reviewer_id, review_note, source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    review_id,
                    run_id,
                    job_id,
                    document_id,
                    schema_id,
                    review_status,
                    reviewer_id,
                    review_note,
                    source,
                    created_at,
                ),
            )

            for correction in corrections:
                correction_id = f"corr-{uuid.uuid4().hex[:12]}"
                correction_created_at = self._now()
                conn.execute(
                    "INSERT INTO review_field_corrections (correction_id, review_id, field_name, extracted_value_snapshot, corrected_value, decision, evidence_text_snapshot, validation_status_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        correction_id,
                        review_id,
                        correction["field_name"],
                        correction.get("extracted_value_snapshot"),
                        correction.get("corrected_value"),
                        correction["decision"],
                        correction.get("evidence_text_snapshot"),
                        correction.get("validation_status_snapshot"),
                        correction_created_at,
                    ),
                )
                stored_corrections.append({
                    "correction_id": correction_id,
                    "field_name": correction["field_name"],
                    "extracted_value_snapshot": correction.get("extracted_value_snapshot"),
                    "corrected_value": correction.get("corrected_value"),
                    "decision": correction["decision"],
                    "evidence_text_snapshot": correction.get("evidence_text_snapshot"),
                    "validation_status_snapshot": correction.get("validation_status_snapshot"),
                    "created_at": correction_created_at,
                })
            conn.commit()

        return {
            "review_id": review_id,
            "run_id": run_id,
            "job_id": job_id,
            "document_id": document_id,
            "schema_id": schema_id,
            "review_status": review_status,
            "reviewer_id": reviewer_id,
            "review_note": review_note,
            "source": source,
            "created_at": created_at,
            "corrections": stored_corrections,
        }

    def list_review_records(self, run_id: str, document_id: str) -> list[dict[str, Any]]:
        """List review records for one run/document newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM review_records WHERE run_id = ? AND document_id = ? ORDER BY created_at DESC",
                (run_id, document_id),
            ).fetchall()

        records = [dict(row) for row in rows]
        correction_map = self._list_review_corrections_by_review_ids([r["review_id"] for r in records])
        for record in records:
            record["corrections"] = correction_map.get(record["review_id"], [])
        return records

    def list_reviews_for_run(self, run_id: str) -> list[dict[str, Any]]:
        """List all review records for a run, with corrections included."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM review_records WHERE run_id = ? ORDER BY created_at DESC",
                (run_id,),
            ).fetchall()

        records = [dict(row) for row in rows]
        correction_map = self._list_review_corrections_by_review_ids([r["review_id"] for r in records])
        for record in records:
            record["corrections"] = correction_map.get(record["review_id"], [])
        return records

    def get_latest_review_record(self, run_id: str, document_id: str) -> dict[str, Any] | None:
        """Return latest review record for run/document, or None when absent."""
        records = self.list_review_records(run_id, document_id)
        return records[0] if records else None

    def _list_review_corrections_by_review_ids(self, review_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not review_ids:
            return {}

        placeholders = ", ".join("?" for _ in review_ids)
        query = (
            "SELECT * FROM review_field_corrections "
            f"WHERE review_id IN ({placeholders}) "
            "ORDER BY created_at ASC"
        )
        with self._conn() as conn:
            rows = conn.execute(query, review_ids).fetchall()

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row)
            grouped.setdefault(item["review_id"], []).append(item)
        return grouped

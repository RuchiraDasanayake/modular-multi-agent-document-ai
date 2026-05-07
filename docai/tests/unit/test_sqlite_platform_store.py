"""Unit tests for SQLite platform store.

Tests persistence layer only. No extraction runtime, no orchestrator imports.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from docai_core.persistence import SQLiteStore, ensure_database_schema


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture()
def store(db_path: Path) -> SQLiteStore:
    """Initialize store with schema."""
    ensure_database_schema(db_path)
    return SQLiteStore(db_path)


# ---------------------------------------------------------------------------
# Test 1: Database initializes with schema
# ---------------------------------------------------------------------------

def test_database_initialized(db_path: Path) -> None:
    """Verify schema is created on initialization."""
    ensure_database_schema(db_path)
    assert db_path.exists()

    # Verify tables exist
    store = SQLiteStore(db_path)
    with store._conn() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    table_names = {row[0] for row in tables}
    expected = {
        "projects", "extraction_schemas_index", "jobs", "documents",
        "runs", "run_documents", "run_artifacts", "document_metrics_index",
        "field_results", "run_events",
    }
    assert expected.issubset(table_names)


def test_schema_upgrade_applies_missing_review_tables(db_path: Path) -> None:
    """Verify existing database missing review tables is upgraded."""
    ensure_database_schema(db_path)
    # Simulate older DB by dropping review tables if they were created.
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS review_field_corrections")
        conn.execute("DROP TABLE IF EXISTS review_records")
        conn.commit()

    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'review%'").fetchall()
    assert tables == []

    ensure_database_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'review%'").fetchall()}
    assert {"review_records", "review_field_corrections"}.issubset(tables)


def test_schema_upgrade_adds_missing_job_profile_columns_and_preserves_data(db_path: Path) -> None:
    """Verify legacy jobs table is upgraded in-place and remains readable."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE extraction_schemas_index (
                schema_id TEXT PRIMARY KEY,
                project_id TEXT,
                name TEXT NOT NULL,
                document_type TEXT NOT NULL,
                version TEXT NOT NULL,
                schema_path TEXT,
                is_builtin INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                schema_id TEXT NOT NULL,
                name TEXT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO projects (project_id, name, description, status, created_at) VALUES (?, ?, ?, ?, ?)",
            ("proj-legacy", "Legacy Project", None, "active", "2026-01-01T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, project_id, name, document_type, version, schema_path, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("invoice_basic", "proj-legacy", "Invoice", "invoice", "v1", None, 0, "2026-01-01T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO jobs (job_id, project_id, schema_id, name, job_type, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("job-legacy-001", "proj-legacy", "invoice_basic", "Legacy Job", "training", "queued", "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()

    ensure_database_schema(db_path)
    ensure_database_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
    assert "profile_id" in columns
    assert "default_mode" in columns

    store = SQLiteStore(db_path)
    existing = store.get_job("job-legacy-001")
    assert existing.name == "Legacy Job"
    assert existing.profile_id is None
    assert existing.default_mode is None

    profile = store.create_extraction_profile(
        project_id="proj-legacy",
        name="legacy-profile",
        schema_id="invoice_basic",
        mode="local_text",
        ocr_strategy="router_default",
        validation_level="standard",
        is_default=1,
    )
    upgraded_job = store.create_job(
        project_id="proj-legacy",
        schema_id=profile.schema_id,
        name="Upgraded Job",
        profile_id=profile.profile_id,
        default_mode=profile.mode,
    )
    assert upgraded_job.profile_id == profile.profile_id
    assert upgraded_job.default_mode == "local_text"


# ---------------------------------------------------------------------------
# Test 2: Create and list projects
# ---------------------------------------------------------------------------

def test_create_and_list_projects(store: SQLiteStore) -> None:
    """Verify project CRUD."""
    proj1 = store.create_project("proj-001", "Test Project 1", "First test")
    proj2 = store.create_project("proj-002", "Test Project 2")

    assert proj1.project_id == "proj-001"
    assert proj1.name == "Test Project 1"
    assert proj1.description == "First test"

    projects = store.list_projects()
    assert len(projects) == 2
    assert proj1.project_id in {p.project_id for p in projects}
    assert proj2.project_id in {p.project_id for p in projects}


# ---------------------------------------------------------------------------
# Test 3: Create project → job → document → run → run_document
# ---------------------------------------------------------------------------

def test_full_hierarchy(store: SQLiteStore, tmp_path: Path) -> None:
    """Verify hierarchy creation."""
    # Project
    proj = store.create_project("proj-hierarchy", "Hierarchy Test")
    assert proj.project_id == "proj-hierarchy"

    # Schema (create in DB via direct insert for test)
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("schema-test", "Test Schema", "invoice", "v1", 0, store._now()),
        )
        conn.commit()

    # Job
    job = store.create_job(proj.project_id, "schema-test", "Test Job")
    assert job.job_id.startswith("job-")
    assert job.project_id == proj.project_id

    # Document
    doc_file = tmp_path / "test.txt"
    doc_file.write_text("test content")
    doc_id = store.create_document(proj.project_id, job.job_id, "test.txt", str(doc_file))
    assert doc_id.startswith("doc-")

    # Run
    run = store.create_run(proj.project_id, job.job_id, "schema-test")
    assert run.run_id.startswith("run-")
    assert run.status == "created"

    # Run document
    run_doc_id = store.create_run_document(run.run_id, doc_id)
    assert run_doc_id.startswith("rd-")


# ---------------------------------------------------------------------------
# Test 4: Add run artifact with payload and hash
# ---------------------------------------------------------------------------

def test_add_run_artifact_with_payload(store: SQLiteStore) -> None:
    """Verify artifact addition with JSON payload and hash."""
    proj = store.create_project("proj-artifact", "Artifact Test")
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("schema-test", "Test Schema", "invoice", "v1", 0, store._now()),
        )
        conn.commit()
    job = store.create_job(proj.project_id, "schema-test", "Test Job")
    run = store.create_run(proj.project_id, job.job_id, "schema-test")

    payload = {"field1": "value1", "field2": 42}
    artifact_id = store.add_run_artifact(
        run.run_id, None, "final_output", "v1", payload=payload
    )

    assert artifact_id.startswith("art-")

    artifacts = store.list_run_artifacts(run.run_id)
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_id"] == artifact_id
    assert artifacts[0]["artifact_type"] == "final_output"
    assert artifacts[0]["payload_json"] is not None
    assert artifacts[0]["payload_hash"] is not None


# ---------------------------------------------------------------------------
# Test 5: Add document metrics
# ---------------------------------------------------------------------------

def test_add_document_metrics(store: SQLiteStore) -> None:
    """Verify metrics addition."""
    proj = store.create_project("proj-metrics", "Metrics Test")
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("schema-test", "Test Schema", "invoice", "v1", 0, store._now()),
        )
        conn.commit()
    job = store.create_job(proj.project_id, "schema-test", "Test Job")
    run = store.create_run(proj.project_id, job.job_id, "schema-test")
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO documents (document_id, project_id, job_id, original_filename, file_path, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("doc-001", proj.project_id, job.job_id, "test.txt", "/path/to/test.txt", "completed", store._now()),
        )
        conn.commit()

    metrics_id = store.add_document_metrics_index(
        proj.project_id, job.job_id, run.run_id, "doc-001", "schema-test",
        evidence_source="dataset_label", is_human_review=0,
        field_precision=0.95, field_recall=0.92, field_f1=0.93, accuracy=0.88,
    )

    assert metrics_id.startswith("metrics-")
    metrics = store.list_document_metrics(run.run_id)
    assert len(metrics) == 1
    assert metrics[0]["field_f1"] == 0.93


# ---------------------------------------------------------------------------
# Test 6: Add field results
# ---------------------------------------------------------------------------

def test_add_field_result(store: SQLiteStore) -> None:
    """Verify field result addition."""
    proj = store.create_project("proj-fields", "Field Test")
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("schema-test", "Test Schema", "invoice", "v1", 0, store._now()),
        )
        conn.execute(
            "INSERT INTO documents (document_id, project_id, job_id, original_filename, file_path, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("doc-001", proj.project_id, "job-001", "test.txt", "/path/to/test.txt", "completed", store._now()),
        )
        conn.commit()

    field_id = store.add_field_result(
        proj.project_id, "job-001", "run-001", "doc-001", "schema-test",
        field_name="invoice_number", evidence_source="dataset_label", is_human_review=0,
        expected_value="INV-001", extracted_value="INV-001", is_correct=1,
        confidence=0.98,
    )

    assert field_id.startswith("fr-")
    fields = store.list_field_results("doc-001")
    assert len(fields) == 1
    assert fields[0]["field_name"] == "invoice_number"
    assert fields[0]["is_correct"] == 1


# ---------------------------------------------------------------------------
# Test 7: Project metrics (chart-ready query)
# ---------------------------------------------------------------------------

def test_list_project_metrics(store: SQLiteStore) -> None:
    """Verify project metrics aggregation for charts."""
    proj = store.create_project("proj-chart", "Chart Test")
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("invoice_schema", "Invoice", "invoice", "v1", 0, store._now()),
        )
        conn.commit()
    job = store.create_job(proj.project_id, "invoice_schema", "Test Job")
    run = store.create_run(proj.project_id, job.job_id, "invoice_schema")

    # Add two metrics records (different times)
    with store._conn() as conn:
        for i in range(2):
            conn.execute(
                "INSERT INTO documents (document_id, project_id, job_id, original_filename, file_path, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"doc-{i:03d}", proj.project_id, job.job_id, f"test_{i}.txt", f"/path/test_{i}.txt", "completed", store._now()),
            )
        conn.commit()

    for i in range(2):
        store.add_document_metrics_index(
            proj.project_id, job.job_id, run.run_id, f"doc-{i:03d}", "invoice_schema",
            evidence_source="test_run", is_human_review=0,
            field_f1=0.90 + i*0.01, accuracy=0.85 + i*0.01,
        )

    metrics = store.list_project_metrics(proj.project_id)
    assert len(metrics) >= 1
    # Chart rows should have aggregated values
    assert any("invoice_schema" in str(m) for m in metrics)


# ---------------------------------------------------------------------------
# Test 8: Append-only: multiple final_output artifacts don't overwrite
# ---------------------------------------------------------------------------

def test_append_only_artifacts(store: SQLiteStore) -> None:
    """Verify artifacts are append-only (no overwrites, all versions kept)."""
    proj = store.create_project("proj-append", "Append Test")
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("schema-test", "Test Schema", "invoice", "v1", 0, store._now()),
        )
        conn.commit()
    job = store.create_job(proj.project_id, "schema-test", "Test Job")
    run = store.create_run(proj.project_id, job.job_id, "schema-test")
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO documents (document_id, project_id, job_id, original_filename, file_path, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("doc-001", proj.project_id, job.job_id, "test.txt", "/path/to/test.txt", "completed", store._now()),
        )
        conn.commit()

    # Add first final_output
    art1_id = store.add_run_artifact(
        run.run_id, "doc-001", "final_output", "v1",
        payload={"invoice_number": "INV-001", "status": "first_version"},
    )

    # Add second final_output (different data, same artifact_type)
    art2_id = store.add_run_artifact(
        run.run_id, "doc-001", "final_output", "v1",
        payload={"invoice_number": "INV-001", "status": "second_version"},
    )

    # Both should exist (append-only, not overwritten)
    artifacts = store.list_run_artifacts(run.run_id, document_id="doc-001", artifact_type="final_output")
    assert len(artifacts) == 2
    assert art1_id != art2_id
    assert artifacts[0]["artifact_id"] == art1_id
    assert artifacts[1]["artifact_id"] == art2_id
    # First version should come first (chronologically)
    assert "first_version" in artifacts[0]["payload_json"]
    assert "second_version" in artifacts[1]["payload_json"]


# ---------------------------------------------------------------------------
# Test 9: DB layer does not import runtime modules
# ---------------------------------------------------------------------------

def test_persistence_no_runtime_imports(store: SQLiteStore) -> None:
    """Verify persistence layer does not depend on extraction runtime."""
    import docai_core.persistence.sqlite_store as persist_module

    source = Path(persist_module.__file__).read_text()

    # Should NOT import extraction runners
    assert "from docai_core.extraction" not in source
    assert "from docai_core.orchestration" not in source
    assert "RuntimeOrchestrator" not in source
    assert "JobRunService" not in source

    # Should only use stdlib and contracts
    assert "import sqlite3" in source
    assert "from pathlib import Path" in source


def test_claim_run_for_processing_is_atomic(store: SQLiteStore) -> None:
    """Only first claim can move run to processing."""
    proj = store.create_project("proj-claim", "Claim Test")
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("schema-claim", "Claim Schema", "invoice", "v1", 0, store._now()),
        )
        conn.commit()
    job = store.create_job(proj.project_id, "schema-claim", "Claim Job")
    run = store.create_run(proj.project_id, job.job_id, "schema-claim", status="created")

    assert store.claim_run_for_processing(run.run_id) is True
    assert store.get_run(run.run_id).status == "processing"
    assert store.claim_run_for_processing(run.run_id) is False

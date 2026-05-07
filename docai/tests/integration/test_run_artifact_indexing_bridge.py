"""Integration tests for run artifact indexing bridge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docai_core.persistence import ArtifactIndexer, SQLiteStore, ensure_database_schema


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Temporary database."""
    db = tmp_path / "test.db"
    ensure_database_schema(db)
    return db


@pytest.fixture()
def store(db_path: Path) -> SQLiteStore:
    """Create store."""
    return SQLiteStore(db_path)


@pytest.fixture()
def artifact_root(tmp_path: Path) -> Path:
    """Create realistic artifact structure."""
    return tmp_path / "artifacts"


@pytest.fixture()
def run_setup(store: SQLiteStore, tmp_path: Path) -> tuple[str, str, str]:
    """Set up project, job, document, and run."""
    # Project
    proj = store.create_project("proj-int", "Integration Test")

    # Schema
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("invoice_basic", "Invoice", "invoice", "v1", 0, store._now()),
        )
        conn.commit()

    # Job
    job = store.create_job(proj.project_id, "invoice_basic", "Integration Job")

    # Document
    doc_file = tmp_path / "test.txt"
    doc_file.write_text("test content")
    doc_id = store.register_document(
        proj.project_id, job.job_id, "test.txt", str(doc_file)
    )

    # Run
    run = store.create_run(proj.project_id, job.job_id, "invoice_basic", status="created")

    # Attach document
    store.create_run_document(run.run_id, doc_id)

    return run.run_id, doc_id, proj.project_id


# ---------------------------------------------------------------------------
# Test 1: Create SQLite entries and index artifacts
# ---------------------------------------------------------------------------

def test_end_to_end_artifact_indexing(
    store: SQLiteStore, artifact_root: Path, run_setup: tuple
) -> None:
    """Verify end-to-end artifact indexing."""
    run_id, doc_id, proj_id = run_setup

    # Create realistic artifacts
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    final_output = {
        "invoice_number": "INV-2024-001",
        "amount": 1500.00,
        "vendor": "Acme Corp",
    }
    with (doc_dir / "final_output.json").open("w") as f:
        json.dump(final_output, f)

    validation = {"valid": True, "warnings": []}
    with (doc_dir / "validation_report.json").open("w") as f:
        json.dump(validation, f)

    # Index
    indexer = ArtifactIndexer(store)
    result = indexer.index_run_artifacts(run_id, artifact_root)

    # Verify
    assert result["artifacts_indexed"] >= 2
    assert len(result["errors"]) == 0

    # Verify database entries
    artifacts = store.list_run_artifacts(run_id)
    assert len(artifacts) >= 2
    assert any(a["artifact_type"] == "final_output" for a in artifacts)
    assert any(a["artifact_type"] == "validation_report" for a in artifacts)


# ---------------------------------------------------------------------------
# Test 2: Index document metrics when present
# ---------------------------------------------------------------------------

def test_index_document_metrics(
    store: SQLiteStore, artifact_root: Path, run_setup: tuple
) -> None:
    """Verify document metrics are indexed when present."""
    run_id, doc_id, proj_id = run_setup

    # Create metrics artifacts
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    metrics = {
        "accuracy": 0.92,
        "field_f1": 0.90,
        "field_precision": 0.94,
        "field_recall": 0.88,
    }
    with (doc_dir / "document_metrics.json").open("w") as f:
        json.dump(metrics, f)

    expected_values = {"source": "dataset_label", "is_human_review": False}
    with (doc_dir / "expected_values.json").open("w") as f:
        json.dump(expected_values, f)

    # Index
    indexer = ArtifactIndexer(store)
    result = indexer.index_run_artifacts(run_id, artifact_root)

    # Verify
    assert result["metrics_indexed"] is True

    # Check database
    metrics_records = store.list_document_metrics(run_id, doc_id)
    assert len(metrics_records) > 0
    assert metrics_records[0]["accuracy"] == 0.92
    assert metrics_records[0]["field_f1"] == 0.90


# ---------------------------------------------------------------------------
# Test 3: Missing run returns error
# ---------------------------------------------------------------------------

def test_missing_run_returns_error(store: SQLiteStore, artifact_root: Path) -> None:
    """Verify missing run is caught."""
    indexer = ArtifactIndexer(store)
    result = indexer.index_run_artifacts("run-nonexistent", artifact_root)

    assert len(result["errors"]) > 0
    assert "not found" in result["errors"][0].lower()


# ---------------------------------------------------------------------------
# Test 4: Missing artifact root returns error
# ---------------------------------------------------------------------------

def test_missing_artifact_root_returns_error(store: SQLiteStore, run_setup: tuple) -> None:
    """Verify missing artifact root is caught."""
    run_id, doc_id, proj_id = run_setup
    nonexistent_root = Path("/nonexistent/path")

    indexer = ArtifactIndexer(store)
    result = indexer.index_run_artifacts(run_id, nonexistent_root)

    assert len(result["errors"]) > 0
    assert "not exist" in result["errors"][0].lower()


# ---------------------------------------------------------------------------
# Test 5: Run-level artifacts (selected_policy, run_plan)
# ---------------------------------------------------------------------------

def test_index_run_level_artifacts(
    store: SQLiteStore, artifact_root: Path, run_setup: tuple
) -> None:
    """Verify run-level artifacts are indexed."""
    run_id, doc_id, proj_id = run_setup

    artifact_root.mkdir(parents=True, exist_ok=True)

    # Create run-level artifacts
    selected_policy = {"policy_id": "policy-v1", "timestamp": "2024-01-01"}
    with (artifact_root / "selected_policy.json").open("w") as f:
        json.dump(selected_policy, f)

    run_plan = {"steps": ["parse", "extract", "validate"]}
    with (artifact_root / "run_plan.json").open("w") as f:
        json.dump(run_plan, f)

    # Index
    indexer = ArtifactIndexer(store)
    result = indexer.index_run_artifacts(run_id, artifact_root)

    # Verify
    assert result["artifacts_indexed"] >= 2

    # Check database for run-level artifacts
    artifacts = store.list_run_artifacts(run_id, artifact_type="selected_policy")
    assert len(artifacts) > 0


# ---------------------------------------------------------------------------
# Test 6: No extraction runtime is invoked
# ---------------------------------------------------------------------------

def test_no_extraction_runtime_invoked(
    store: SQLiteStore, artifact_root: Path, run_setup: tuple
) -> None:
    """Verify extraction runtime modules are not imported."""
    import sys

    # Record initial modules
    initial_modules = set(sys.modules.keys())

    run_id, doc_id, proj_id = run_setup
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    final_output = {"test": "data"}
    with (doc_dir / "final_output.json").open("w") as f:
        json.dump(final_output, f)

    # Index
    indexer = ArtifactIndexer(store)
    result = indexer.index_run_artifacts(run_id, artifact_root)

    # Check modules imported
    new_modules = set(sys.modules.keys())
    forbidden_modules = {"docai_core.extraction", "docai_core.orchestration", "docai_core.application.job_run_service"}

    for mod in new_modules - initial_modules:
        for forbidden in forbidden_modules:
            assert not mod.startswith(forbidden), f"Forbidden module imported: {mod}"


# ---------------------------------------------------------------------------
# Test 7: No policy mutation
# ---------------------------------------------------------------------------

def test_no_policy_mutation(
    store: SQLiteStore, artifact_root: Path, run_setup: tuple
) -> None:
    """Verify policies are not mutated."""
    run_id, doc_id, proj_id = run_setup
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    final_output = {"test": "data"}
    with (doc_dir / "final_output.json").open("w") as f:
        json.dump(final_output, f)

    # Get run before indexing
    run_before = store.get_run(run_id)
    policy_id_before = run_before.policy_id

    # Index
    indexer = ArtifactIndexer(store)
    result = indexer.index_run_artifacts(run_id, artifact_root)

    # Verify policy unchanged
    run_after = store.get_run(run_id)
    assert run_after.policy_id == policy_id_before

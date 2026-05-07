"""Unit tests for artifact indexing."""

from __future__ import annotations

from pathlib import Path

import pytest

from docai_core.persistence import ArtifactIndexer, SQLiteStore, ensure_database_schema


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Temporary database path."""
    db_path = tmp_path / "test.db"
    ensure_database_schema(db_path)
    return db_path


@pytest.fixture()
def store(db_path: Path) -> SQLiteStore:
    """Initialize store with schema."""
    return SQLiteStore(db_path)


@pytest.fixture()
def indexer(store: SQLiteStore) -> ArtifactIndexer:
    """Create artifact indexer."""
    return ArtifactIndexer(store)


@pytest.fixture()
def run_context(store: SQLiteStore, tmp_path: Path) -> tuple[str, str, str, str]:
    """Create project, job, document, and run."""
    # Project
    proj = store.create_project("proj-test", "Test Project")

    # Schema
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("invoice_basic", "Invoice", "invoice", "v1", 0, store._now()),
        )
        conn.commit()

    # Job
    job = store.create_job(proj.project_id, "invoice_basic", "Test Job")

    # Document
    doc_file = tmp_path / "test.txt"
    doc_file.write_text("test content")
    doc_id = store.register_document(
        proj.project_id, job.job_id, "test.txt", str(doc_file)
    )

    # Run
    run = store.create_run(proj.project_id, job.job_id, "invoice_basic", status="created")

    # Attach document to run
    store.create_run_document(run.run_id, doc_id)

    return run.run_id, doc_id, job.job_id, proj.project_id


# ---------------------------------------------------------------------------
# Test 1: Index final_output/validation/selected_policy artifacts
# ---------------------------------------------------------------------------

def test_indexes_standard_artifacts(indexer: ArtifactIndexer, run_context: tuple, tmp_path: Path) -> None:
    """Verify standard artifacts are indexed."""
    run_id, doc_id, job_id, proj_id = run_context

    # Create artifact directory structure
    artifact_root = tmp_path / "artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Write artifacts
    final_output = {"invoice_number": "INV-001", "amount": 100.0}
    with (doc_dir / "final_output.json").open("w") as f:
        import json

        json.dump(final_output, f)

    validation = {"valid": True}
    with (doc_dir / "validation_report.json").open("w") as f:
        json.dump(validation, f)

    expected_values = {"source": "dataset_label", "is_human_review": False}
    with (doc_dir / "expected_values.json").open("w") as f:
        json.dump(expected_values, f)

    selected_policy = {"policy_id": "policy-v1"}
    with (artifact_root / "selected_policy.json").open("w") as f:
        json.dump(selected_policy, f)

    # Index
    result = indexer.index_run_artifacts(run_id, artifact_root)

    # Verify
    assert result["artifacts_indexed"] >= 3
    assert len(result["errors"]) == 0
    assert len(result["warnings"]) == 0


# ---------------------------------------------------------------------------
# Test 2: Computes and stores payload_hash
# ---------------------------------------------------------------------------

def test_computes_payload_hash(indexer: ArtifactIndexer, run_context: tuple, tmp_path: Path, store: SQLiteStore) -> None:
    """Verify payload hash is computed."""
    run_id, doc_id, job_id, proj_id = run_context

    # Create artifact directory structure
    artifact_root = tmp_path / "artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Write artifact
    final_output = {"test": "data"}
    with (doc_dir / "final_output.json").open("w") as f:
        import json

        json.dump(final_output, f)

    # Index
    result = indexer.index_run_artifacts(run_id, artifact_root)

    # Verify hash exists
    artifacts = store.list_run_artifacts(run_id, doc_id, "final_output")
    assert len(artifacts) > 0
    assert artifacts[0]["payload_hash"] is not None
    assert len(artifacts[0]["payload_hash"]) == 64  # SHA256 hex


# ---------------------------------------------------------------------------
# Test 3: Does not create fake missing artifacts
# ---------------------------------------------------------------------------

def test_does_not_create_fake_artifacts(indexer: ArtifactIndexer, run_context: tuple, tmp_path: Path, store: SQLiteStore) -> None:
    """Verify missing artifacts are not created."""
    run_id, doc_id, job_id, proj_id = run_context

    # Create only artifact directory, no files
    artifact_root = tmp_path / "artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Index
    result = indexer.index_run_artifacts(run_id, artifact_root)

    # Verify no artifacts indexed
    assert result["artifacts_indexed"] == 0


# ---------------------------------------------------------------------------
# Test 4: Duplicate indexing avoids duplicates based on hash
# ---------------------------------------------------------------------------

def test_duplicate_prevention_by_hash(indexer: ArtifactIndexer, run_context: tuple, tmp_path: Path, store: SQLiteStore) -> None:
    """Verify duplicate artifacts with same hash are not re-indexed."""
    run_id, doc_id, job_id, proj_id = run_context

    # Create artifact directory
    artifact_root = tmp_path / "artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Write artifact
    final_output = {"invoice_number": "INV-001"}
    with (doc_dir / "final_output.json").open("w") as f:
        import json

        json.dump(final_output, f)

    # Index first time
    result1 = indexer.index_run_artifacts(run_id, artifact_root)
    count1 = result1["artifacts_indexed"]

    # Index again with same content
    result2 = indexer.index_run_artifacts(run_id, artifact_root)
    count2 = result2["artifacts_indexed"]

    # Second indexing should not create duplicates
    assert count2 == 0


# ---------------------------------------------------------------------------
# Test 6: Malformed JSON produces error
# ---------------------------------------------------------------------------

def test_malformed_json_produces_error(indexer: ArtifactIndexer, run_context: tuple, tmp_path: Path) -> None:
    """Verify malformed JSON produces error."""
    run_id, doc_id, job_id, proj_id = run_context

    # Create artifact directory
    artifact_root = tmp_path / "artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Write malformed JSON
    with (doc_dir / "final_output.json").open("w") as f:
        f.write("{invalid json")

    # Index
    result = indexer.index_run_artifacts(run_id, artifact_root)

    # Verify error occurred
    assert len(result["errors"]) > 0


# ---------------------------------------------------------------------------
# Test 7: Metrics indexing uses expected_values provenance
# ---------------------------------------------------------------------------

def test_metrics_use_expected_values_provenance(indexer: ArtifactIndexer, run_context: tuple, tmp_path: Path, store: SQLiteStore) -> None:
    """Verify metrics inherit source/is_human_review from expected_values."""
    run_id, doc_id, job_id, proj_id = run_context

    # Create artifact directory
    artifact_root = tmp_path / "artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Write metrics
    metrics = {"accuracy": 0.95, "field_f1": 0.92}
    with (doc_dir / "document_metrics.json").open("w") as f:
        import json

        json.dump(metrics, f)

    # Write expected_values with source
    expected_values = {"source": "dataset_label", "is_human_review": False}
    with (doc_dir / "expected_values.json").open("w") as f:
        json.dump(expected_values, f)

    # Index
    result = indexer.index_run_artifacts(run_id, artifact_root)

    # Verify metrics indexed with correct provenance
    assert result["metrics_indexed"] is True
    metrics_records = store.list_document_metrics(run_id, doc_id)
    assert len(metrics_records) > 0
    assert metrics_records[0]["evidence_source"] == "dataset_label"
    assert metrics_records[0]["is_human_review"] == 0

"""Integration tests for manual artifact indexing API endpoint."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docai_core.api.app import create_app
from docai_core.persistence import SQLiteStore, initialize_database


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Temporary database."""
    db = tmp_path / "test.db"
    initialize_database(db)
    return db


@pytest.fixture()
def client(tmp_path: Path, db_path: Path) -> TestClient:
    """Test client with isolated database."""
    app = create_app(db_path=db_path, runs_dir=tmp_path / "runs")
    return TestClient(app)


@pytest.fixture()
def run_setup(db_path: Path, tmp_path: Path) -> tuple[str, str, str, str]:
    """Set up project, job, document, and run."""
    store = SQLiteStore(db_path)

    # Project
    proj = store.create_project("proj-idx", "Indexing Test")

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

    # Run with artifact_root
    artifact_root = tmp_path / "runs" / "artifacts" / "seed"
    run = store.create_run(
        proj.project_id,
        job.job_id,
        "invoice_basic",
        status="created",
        artifact_root=str(artifact_root),
    )

    # Attach document to run
    store.create_run_document(run.run_id, doc_id)

    return run.run_id, doc_id, str(artifact_root), proj.project_id


# ---------------------------------------------------------------------------
# Test 1: POST /runs/{run_id}/index-artifacts indexes existing artifacts
# ---------------------------------------------------------------------------

def test_indexes_artifacts_from_request_path(client: TestClient, run_setup: tuple, tmp_path: Path) -> None:
    """Verify endpoint indexes artifacts when artifact_root is in request body."""
    run_id, doc_id, _, _ = run_setup

    # Create artifact directory structure
    artifact_root = Path(client.app.state.runs_dir) / "custom_artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Write artifacts
    final_output = {"invoice_number": "INV-001", "amount": 100.0}
    with (doc_dir / "final_output.json").open("w") as f:
        json.dump(final_output, f)

    # Index
    response = client.post(
        f"/runs/{run_id}/index-artifacts",
        json={"artifact_root": str(artifact_root)},
    )

    # Verify
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id
    assert data["artifact_root"] == str(artifact_root)
    assert data["artifacts_indexed"] >= 1
    assert data["metrics_indexed"] is False
    assert len(data["errors"]) == 0


# ---------------------------------------------------------------------------
# Test 2: Missing run returns 404
# ---------------------------------------------------------------------------

def test_missing_run_returns_404(client: TestClient) -> None:
    """Verify missing run returns 404."""
    response = client.post(
        "/runs/run-nonexistent/index-artifacts",
        json={"artifact_root": "/tmp/artifacts"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 3: Missing artifact_root in body and DB returns 400
# ---------------------------------------------------------------------------

def test_missing_artifact_root_returns_400(client: TestClient, db_path: Path, tmp_path: Path) -> None:
    """Verify missing artifact_root returns 400."""
    store = SQLiteStore(db_path)

    # Create project, job, run WITHOUT artifact_root
    proj = store.create_project("proj-no-root", "Test")
    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("invoice_basic", "Invoice", "invoice", "v1", 0, store._now()),
        )
        conn.commit()
    job = store.create_job(proj.project_id, "invoice_basic", "Test Job")
    run = store.create_run(proj.project_id, job.job_id, "invoice_basic")  # No artifact_root

    # Try to index without providing artifact_root in request
    response = client.post(
        f"/runs/{run.run_id}/index-artifacts",
        json={"document_id": None},
    )

    assert response.status_code == 400
    assert "artifact_root" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 4: Body artifact_root overrides run.artifact_root
# ---------------------------------------------------------------------------

def test_request_artifact_root_overrides_run_root(client: TestClient, run_setup: tuple, tmp_path: Path) -> None:
    """Verify request body artifact_root takes precedence."""
    run_id, doc_id, db_artifact_root, _ = run_setup

    # Create artifacts in a different directory (not the one in DB)
    override_root = Path(client.app.state.runs_dir) / "override_artifacts"
    doc_dir = override_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    final_output = {"test": "data"}
    with (doc_dir / "final_output.json").open("w") as f:
        json.dump(final_output, f)

    # Index with override
    response = client.post(
        f"/runs/{run_id}/index-artifacts",
        json={"artifact_root": str(override_root)},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifact_root"] == str(override_root)
    assert data["artifacts_indexed"] >= 1


def test_index_artifacts_rejects_root_outside_runs_dir(client: TestClient, run_setup: tuple, tmp_path: Path) -> None:
    """artifact_root outside configured runs_dir is rejected."""
    run_id, _, _, _ = run_setup

    outside_root = tmp_path / "outside-artifacts"
    response = client.post(
        f"/runs/{run_id}/index-artifacts",
        json={"artifact_root": str(outside_root)},
    )

    assert response.status_code == 400
    assert "artifact_root" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test 5: Existing run.artifact_root is used when body omitted
# ---------------------------------------------------------------------------

def test_uses_run_artifact_root_when_body_omitted(client: TestClient, run_setup: tuple, db_path: Path) -> None:
    """Verify run.artifact_root from DB is used when request body is empty."""
    run_id, doc_id, db_artifact_root, _ = run_setup

    # Create artifacts in the DB artifact_root
    artifact_root_path = Path(db_artifact_root)
    doc_dir = artifact_root_path / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    final_output = {"invoice": "INV-123"}
    with (doc_dir / "final_output.json").open("w") as f:
        json.dump(final_output, f)

    # Index without specifying artifact_root in request
    response = client.post(
        f"/runs/{run_id}/index-artifacts",
        json={},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifact_root"] == db_artifact_root
    assert data["artifacts_indexed"] >= 1


# ---------------------------------------------------------------------------
# Test 6: document_id parameter is passed through
# ---------------------------------------------------------------------------

def test_document_id_parameter_passed_through(client: TestClient, run_setup: tuple, tmp_path: Path) -> None:
    """Verify document_id in request is passed to indexer."""
    run_id, doc_id, _, _ = run_setup

    # Create artifacts for specific document
    artifact_root = Path(client.app.state.runs_dir) / "doc_artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    final_output = {"doc_specific": True}
    with (doc_dir / "final_output.json").open("w") as f:
        json.dump(final_output, f)

    # Index with specific document_id
    response = client.post(
        f"/runs/{run_id}/index-artifacts",
        json={"artifact_root": str(artifact_root), "document_id": doc_id},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == doc_id
    assert data["artifacts_indexed"] >= 1


# ---------------------------------------------------------------------------
# Test 7: Warnings/errors from indexer returned without invention
# ---------------------------------------------------------------------------

def test_returns_indexer_warnings_and_errors(client: TestClient, run_setup: tuple, tmp_path: Path) -> None:
    """Verify warnings and errors from indexer are returned as-is."""
    run_id, doc_id, _, _ = run_setup

    # Create artifacts with malformed JSON to trigger error
    artifact_root = Path(client.app.state.runs_dir) / "bad_artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Write malformed JSON
    with (doc_dir / "final_output.json").open("w") as f:
        f.write("{invalid json")

    # Index
    response = client.post(
        f"/runs/{run_id}/index-artifacts",
        json={"artifact_root": str(artifact_root)},
    )

    # Should succeed with 200, but have errors in body
    assert response.status_code == 200
    data = response.json()
    assert len(data["errors"]) > 0
    assert "invalid" in data["errors"][0].lower() or "json" in data["errors"][0].lower()


# ---------------------------------------------------------------------------
# Test 8: Endpoint does not invoke extraction/orchestration modules
# ---------------------------------------------------------------------------

def test_no_extraction_runtime_invoked(client: TestClient, run_setup: tuple, tmp_path: Path) -> None:
    """Verify extraction runtime modules are not imported during indexing."""
    import sys

    run_id, doc_id, _, _ = run_setup

    # Record initial modules
    initial_modules = set(sys.modules.keys())

    artifact_root = Path(client.app.state.runs_dir) / "final_artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    final_output = {"test": "data"}
    with (doc_dir / "final_output.json").open("w") as f:
        json.dump(final_output, f)

    # Index
    response = client.post(
        f"/runs/{run_id}/index-artifacts",
        json={"artifact_root": str(artifact_root)},
    )

    assert response.status_code == 200

    # Check modules imported
    new_modules = set(sys.modules.keys())
    forbidden_modules = {"docai_core.extraction", "docai_core.orchestration", "docai_core.application.job_run_service"}

    for mod in new_modules - initial_modules:
        for forbidden in forbidden_modules:
            assert not mod.startswith(forbidden), f"Forbidden module imported: {mod}"


# ---------------------------------------------------------------------------
# Test 9: Endpoint does not mutate policy_id or run metadata
# ---------------------------------------------------------------------------

def test_does_not_mutate_run_metadata(client: TestClient, run_setup: tuple, db_path: Path, tmp_path: Path) -> None:
    """Verify run metadata (especially policy_id) is not modified."""
    run_id, doc_id, _, _ = run_setup

    store = SQLiteStore(db_path)

    # Get run before indexing
    run_before = store.get_run(run_id)
    policy_id_before = run_before.policy_id

    # Create artifacts
    artifact_root = Path(client.app.state.runs_dir) / "metadata_artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    final_output = {"test": "data"}
    with (doc_dir / "final_output.json").open("w") as f:
        json.dump(final_output, f)

    # Index
    response = client.post(
        f"/runs/{run_id}/index-artifacts",
        json={"artifact_root": str(artifact_root)},
    )

    assert response.status_code == 200

    # Verify policy unchanged
    run_after = store.get_run(run_id)
    assert run_after.policy_id == policy_id_before


# ---------------------------------------------------------------------------
# Test 10: Metrics are indexed with provenance from expected_values
# ---------------------------------------------------------------------------

def test_metrics_indexed_with_provenance(client: TestClient, run_setup: tuple, tmp_path: Path, db_path: Path) -> None:
    """Verify document metrics are indexed with provenance from expected_values."""
    run_id, doc_id, _, _ = run_setup

    artifact_root = Path(client.app.state.runs_dir) / "metrics_artifacts"
    doc_dir = artifact_root / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Write metrics
    metrics = {"accuracy": 0.92, "field_f1": 0.90}
    with (doc_dir / "document_metrics.json").open("w") as f:
        json.dump(metrics, f)

    # Write expected_values with provenance
    expected_values = {"source": "test_run", "is_human_review": False}
    with (doc_dir / "expected_values.json").open("w") as f:
        json.dump(expected_values, f)

    # Index
    response = client.post(
        f"/runs/{run_id}/index-artifacts",
        json={"artifact_root": str(artifact_root)},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["metrics_indexed"] is True

    # Verify in DB
    store = SQLiteStore(db_path)
    metrics_records = store.list_document_metrics(run_id, doc_id)
    assert len(metrics_records) > 0
    assert metrics_records[0]["evidence_source"] == "test_run"
    assert metrics_records[0]["is_human_review"] == 0

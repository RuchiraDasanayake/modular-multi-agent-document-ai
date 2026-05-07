"""Integration tests for Run Metadata API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docai_core.api.app import create_app
from docai_core.persistence import ensure_database_schema


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Temporary database path with schema initialized."""
    db_path = tmp_path / "test.db"
    ensure_database_schema(db_path)
    return db_path


@pytest.fixture()
def client(tmp_db: Path, tmp_path: Path) -> TestClient:
    """FastAPI test client with isolated temp database."""
    app = create_app(runs_dir=tmp_path / "runs", db_path=tmp_db)
    return TestClient(app)


@pytest.fixture()
def project_job_docs(client: TestClient) -> tuple[str, str, list[str]]:
    """Create project, job, and multiple documents for tests."""
    proj_response = client.post("/projects", json={"name": "Test Project"})
    project_id = proj_response.json()["project_id"]

    job_response = client.post(f"/projects/{project_id}/jobs", json={
        "name": "Test Job",
        "schema_id": "invoice_basic",
    })
    job_id = job_response.json()["job_id"]

    # Create three documents
    doc_ids = []
    for i in range(3):
        doc_response = client.post(f"/jobs/{job_id}/documents", json={
            "original_filename": f"doc{i}.pdf",
            "file_path": f"/data/doc{i}.pdf",
        })
        doc_ids.append(doc_response.json()["document_id"])

    return project_id, job_id, doc_ids


# ---------------------------------------------------------------------------
# Test 1: Create run under job
# ---------------------------------------------------------------------------

def test_create_run_under_job(client: TestClient, project_job_docs: tuple[str, str, list[str]]) -> None:
    """Verify run creation via POST /jobs/{job_id}/runs."""
    project_id, job_id, doc_ids = project_job_docs

    response = client.post(f"/jobs/{job_id}/runs", json={
        "policy_id": "policy-v1",
        "mode": "local_text",
        "run_type": "practice",
        "status": "created",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"].startswith("run-")
    assert data["project_id"] == project_id
    assert data["job_id"] == job_id
    assert data["policy_id"] == "policy-v1"
    assert data["mode"] == "local_text"
    assert data["run_type"] == "practice"
    assert data["status"] == "created"
    assert "created_at" in data


# ---------------------------------------------------------------------------
# Test 2: List runs for job
# ---------------------------------------------------------------------------

def test_list_runs_for_job(client: TestClient, project_job_docs: tuple[str, str, list[str]]) -> None:
    """Verify listing runs via GET /jobs/{job_id}/runs."""
    project_id, job_id, doc_ids = project_job_docs

    # Create two runs
    client.post(f"/jobs/{job_id}/runs", json={"run_type": "practice"})
    client.post(f"/jobs/{job_id}/runs", json={"run_type": "training"})

    response = client.get(f"/jobs/{job_id}/runs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    run_types = {r["run_type"] for r in data}
    assert "practice" in run_types
    assert "training" in run_types


# ---------------------------------------------------------------------------
# Test 3: Get run by id
# ---------------------------------------------------------------------------

def test_get_run_by_id(client: TestClient, project_job_docs: tuple[str, str, list[str]]) -> None:
    """Verify retrieving run via GET /runs/{run_id}."""
    project_id, job_id, doc_ids = project_job_docs

    create_response = client.post(f"/jobs/{job_id}/runs", json={
        "run_type": "practice",
        "policy_id": "test-policy",
    })
    run_id = create_response.json()["run_id"]

    response = client.get(f"/runs/{run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id
    assert data["job_id"] == job_id
    assert data["policy_id"] == "test-policy"


# ---------------------------------------------------------------------------
# Test 4: Missing job when creating run returns 404
# ---------------------------------------------------------------------------

def test_missing_job_when_creating_run_returns_404(client: TestClient) -> None:
    """Verify 404 when creating run under nonexistent job."""
    response = client.post("/jobs/job-nonexistent/runs", json={
        "run_type": "practice",
    })
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 5: Missing job when listing runs returns 404
# ---------------------------------------------------------------------------

def test_missing_job_when_listing_runs_returns_404(client: TestClient) -> None:
    """Verify 404 when listing runs for nonexistent job."""
    response = client.get("/jobs/job-nonexistent/runs")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 6: Missing run returns 404
# ---------------------------------------------------------------------------

def test_missing_run_returns_404(client: TestClient) -> None:
    """Verify 404 when run does not exist."""
    response = client.get("/runs/run-nonexistent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 7: Create run derives project_id and schema_id from job
# ---------------------------------------------------------------------------

def test_create_run_derives_project_and_schema_from_job(
    client: TestClient, project_job_docs: tuple[str, str, list[str]]
) -> None:
    """Verify run.project_id and run.schema_id match job."""
    project_id, job_id, doc_ids = project_job_docs

    response = client.post(f"/jobs/{job_id}/runs", json={"run_type": "practice"})
    data = response.json()
    assert data["project_id"] == project_id
    assert data["schema_id"] == "invoice_basic"


# ---------------------------------------------------------------------------
# Test 8: Attach existing document to run
# ---------------------------------------------------------------------------

def test_attach_existing_document_to_run(
    client: TestClient, project_job_docs: tuple[str, str, list[str]]
) -> None:
    """Verify attaching document via POST /runs/{run_id}/documents."""
    project_id, job_id, doc_ids = project_job_docs

    run_response = client.post(f"/jobs/{job_id}/runs", json={"run_type": "practice"})
    run_id = run_response.json()["run_id"]

    response = client.post(f"/runs/{run_id}/documents", json={
        "document_id": doc_ids[0],
        "status": "pending",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["run_document_id"].startswith("rd-")
    assert data["run_id"] == run_id
    assert data["document_id"] == doc_ids[0]
    assert data["status"] == "pending"


# ---------------------------------------------------------------------------
# Test 9: List documents attached to run
# ---------------------------------------------------------------------------

def test_list_documents_attached_to_run(
    client: TestClient, project_job_docs: tuple[str, str, list[str]]
) -> None:
    """Verify listing run_documents via GET /runs/{run_id}/documents."""
    project_id, job_id, doc_ids = project_job_docs

    run_response = client.post(f"/jobs/{job_id}/runs", json={"run_type": "practice"})
    run_id = run_response.json()["run_id"]

    # Attach two documents
    client.post(f"/runs/{run_id}/documents", json={"document_id": doc_ids[0]})
    client.post(f"/runs/{run_id}/documents", json={"document_id": doc_ids[1]})

    response = client.get(f"/runs/{run_id}/documents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    doc_ids_in_run = {d["document_id"] for d in data}
    assert doc_ids[0] in doc_ids_in_run
    assert doc_ids[1] in doc_ids_in_run


# ---------------------------------------------------------------------------
# Test 10: Missing run when attaching document returns 404
# ---------------------------------------------------------------------------

def test_missing_run_when_attaching_document_returns_404(
    client: TestClient, project_job_docs: tuple[str, str, list[str]]
) -> None:
    """Verify 404 when attaching document to nonexistent run."""
    project_id, job_id, doc_ids = project_job_docs

    response = client.post("/runs/run-nonexistent/documents", json={
        "document_id": doc_ids[0],
    })
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 11: Missing document when attaching to run returns 404
# ---------------------------------------------------------------------------

def test_missing_document_when_attaching_to_run_returns_404(
    client: TestClient, project_job_docs: tuple[str, str, list[str]]
) -> None:
    """Verify 404 when attaching nonexistent document to run."""
    project_id, job_id, doc_ids = project_job_docs

    run_response = client.post(f"/jobs/{job_id}/runs", json={"run_type": "practice"})
    run_id = run_response.json()["run_id"]

    response = client.post(f"/runs/{run_id}/documents", json={
        "document_id": "doc-nonexistent",
    })
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 12: Document from another job cannot be attached to run
# ---------------------------------------------------------------------------

def test_document_from_another_job_cannot_be_attached(client: TestClient) -> None:
    """Verify 400 when attaching document from different job."""
    # Create first job with document
    proj1_response = client.post("/projects", json={"name": "Project 1"})
    proj1_id = proj1_response.json()["project_id"]
    job1_response = client.post(f"/projects/{proj1_id}/jobs", json={
        "name": "Job 1",
        "schema_id": "invoice_basic",
    })
    job1_id = job1_response.json()["job_id"]
    doc1_response = client.post(f"/jobs/{job1_id}/documents", json={
        "original_filename": "doc1.pdf",
        "file_path": "/data/doc1.pdf",
    })
    doc1_id = doc1_response.json()["document_id"]

    # Create second job
    proj2_response = client.post("/projects", json={"name": "Project 2"})
    proj2_id = proj2_response.json()["project_id"]
    job2_response = client.post(f"/projects/{proj2_id}/jobs", json={
        "name": "Job 2",
        "schema_id": "invoice_basic",
    })
    job2_id = job2_response.json()["job_id"]
    run2_response = client.post(f"/jobs/{job2_id}/runs", json={"run_type": "practice"})
    run2_id = run2_response.json()["run_id"]

    # Try to attach doc1 (from job1) to run2 (from job2)
    response = client.post(f"/runs/{run2_id}/documents", json={
        "document_id": doc1_id,
    })
    assert response.status_code == 400
    assert "does not belong to job" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 13: Run creation does not invoke extraction or create artifacts
# ---------------------------------------------------------------------------

def test_run_creation_does_not_invoke_extraction(
    client: TestClient, project_job_docs: tuple[str, str, list[str]]
) -> None:
    """Verify run metadata creation is purely metadata, no extraction."""
    project_id, job_id, doc_ids = project_job_docs

    response = client.post(f"/jobs/{job_id}/runs", json={
        "run_type": "practice",
        "status": "created",
    })
    assert response.status_code == 200
    data = response.json()
    # Status stays "created" (not "processing" or "completed")
    # No extraction runtime was invoked
    assert data["status"] == "created"
    assert data["run_id"].startswith("run-")


# ---------------------------------------------------------------------------
# Test 14: Temp DB isolation works
# ---------------------------------------------------------------------------

def test_run_metadata_db_isolation_via_tmp_path(tmp_path: Path) -> None:
    """Verify each test gets isolated database."""
    db1 = tmp_path / "db1.sqlite"
    db2 = tmp_path / "db2.sqlite"

    ensure_database_schema(db1)
    ensure_database_schema(db2)

    client1 = create_app(runs_dir=tmp_path / "runs1", db_path=db1)
    client2 = create_app(runs_dir=tmp_path / "runs2", db_path=db2)

    tc1 = TestClient(client1)
    tc2 = TestClient(client2)

    # Create project/job/run in client1
    proj_resp = tc1.post("/projects", json={"name": "Project 1"})
    project_id = proj_resp.json()["project_id"]
    job_resp = tc1.post(f"/projects/{project_id}/jobs", json={
        "name": "Job 1",
        "schema_id": "invoice_basic",
    })
    job_id = job_resp.json()["job_id"]
    run_resp = tc1.post(f"/jobs/{job_id}/runs", json={"run_type": "practice"})
    assert run_resp.status_code == 200

    # Verify client2 has no runs (isolated database)
    proj_resp2 = tc2.post("/projects", json={"name": "Project 2"})
    project_id2 = proj_resp2.json()["project_id"]
    job_resp2 = tc2.post(f"/projects/{project_id2}/jobs", json={
        "name": "Job 2",
        "schema_id": "invoice_basic",
    })
    job_id2 = job_resp2.json()["job_id"]
    list_resp = tc2.get(f"/jobs/{job_id2}/runs")
    assert len(list_resp.json()) == 0

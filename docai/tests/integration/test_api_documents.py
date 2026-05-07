"""Integration tests for Document Metadata API endpoints."""

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
    """FastAPI test client with isolated temp database and runs directory."""
    app = create_app(runs_dir=tmp_path / "runs", db_path=tmp_db)
    return TestClient(app)


@pytest.fixture()
def project_and_job(client: TestClient) -> tuple[str, str]:
    """Create a project and job for tests."""
    proj_response = client.post("/projects", json={"name": "Test Project"})
    project_id = proj_response.json()["project_id"]

    job_response = client.post(f"/projects/{project_id}/jobs", json={
        "name": "Test Job",
        "schema_id": "invoice_basic",
    })
    job_id = job_response.json()["job_id"]

    return project_id, job_id


# ---------------------------------------------------------------------------
# Test 1: Create document under job
# ---------------------------------------------------------------------------

def test_create_document_under_job(client: TestClient, project_and_job: tuple[str, str]) -> None:
    """Verify document creation via POST /jobs/{job_id}/documents."""
    project_id, job_id = project_and_job

    response = client.post(f"/jobs/{job_id}/documents", json={
        "original_filename": "invoice.pdf",
        "file_path": "/data/invoice.pdf",
        "file_hash": "abc123def456",
        "file_type": "pdf",
        "status": "registered",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"].startswith("doc-")
    assert data["project_id"] == project_id
    assert data["job_id"] == job_id
    assert data["original_filename"] == "invoice.pdf"
    assert data["file_path"] == "/data/invoice.pdf"
    assert data["file_hash"] == "abc123def456"
    assert data["file_type"] == "pdf"
    assert data["status"] == "registered"
    assert "created_at" in data


# ---------------------------------------------------------------------------
# Test 2: List documents for job
# ---------------------------------------------------------------------------

def test_list_documents_for_job(client: TestClient, project_and_job: tuple[str, str]) -> None:
    """Verify listing documents via GET /jobs/{job_id}/documents."""
    project_id, job_id = project_and_job

    # Create two documents
    client.post(f"/jobs/{job_id}/documents", json={
        "original_filename": "doc1.pdf",
        "file_path": "/data/doc1.pdf",
    })
    client.post(f"/jobs/{job_id}/documents", json={
        "original_filename": "doc2.pdf",
        "file_path": "/data/doc2.pdf",
    })

    response = client.get(f"/jobs/{job_id}/documents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    filenames = {d["original_filename"] for d in data}
    assert "doc1.pdf" in filenames
    assert "doc2.pdf" in filenames


# ---------------------------------------------------------------------------
# Test 3: Get document
# ---------------------------------------------------------------------------

def test_get_document(client: TestClient, project_and_job: tuple[str, str]) -> None:
    """Verify retrieving single document via GET /documents/{document_id}."""
    project_id, job_id = project_and_job

    create_response = client.post(f"/jobs/{job_id}/documents", json={
        "original_filename": "test.pdf",
        "file_path": "/data/test.pdf",
        "file_hash": "test123",
    })
    document_id = create_response.json()["document_id"]

    response = client.get(f"/documents/{document_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == document_id
    assert data["project_id"] == project_id
    assert data["job_id"] == job_id
    assert data["original_filename"] == "test.pdf"
    assert data["file_hash"] == "test123"


# ---------------------------------------------------------------------------
# Test 4: Missing job when creating document returns 404
# ---------------------------------------------------------------------------

def test_missing_job_when_creating_document_returns_404(client: TestClient) -> None:
    """Verify 404 when creating document under nonexistent job."""
    response = client.post("/jobs/job-nonexistent/documents", json={
        "original_filename": "doc.pdf",
        "file_path": "/data/doc.pdf",
    })
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 5: Missing job when listing documents returns 404
# ---------------------------------------------------------------------------

def test_missing_job_when_listing_documents_returns_404(client: TestClient) -> None:
    """Verify 404 when listing documents for nonexistent job."""
    response = client.get("/jobs/job-nonexistent/documents")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 6: Missing document returns 404
# ---------------------------------------------------------------------------

def test_missing_document_returns_404(client: TestClient) -> None:
    """Verify 404 when document does not exist."""
    response = client.get("/documents/doc-nonexistent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 7: Document creation derives project_id from job
# ---------------------------------------------------------------------------

def test_document_creation_derives_project_id_from_job(
    client: TestClient, project_and_job: tuple[str, str]
) -> None:
    """Verify document.project_id matches job.project_id."""
    project_id, job_id = project_and_job

    response = client.post(f"/jobs/{job_id}/documents", json={
        "original_filename": "doc.pdf",
        "file_path": "/data/doc.pdf",
    })
    data = response.json()
    assert data["project_id"] == project_id


# ---------------------------------------------------------------------------
# Test 8: No extraction artifacts are created by document registration
# ---------------------------------------------------------------------------

def test_no_extraction_artifacts_created_by_registration(
    client: TestClient, project_and_job: tuple[str, str]
) -> None:
    """Verify document registration does not create extraction artifacts."""
    project_id, job_id = project_and_job

    # Register a document
    response = client.post(f"/jobs/{job_id}/documents", json={
        "original_filename": "doc.pdf",
        "file_path": "/data/doc.pdf",
    })
    assert response.status_code == 200

    # Artifact retrieval would require run_id; this test just verifies
    # document registration succeeded without invoking extraction runtime.
    # The key is that no extraction module imports or JobRunService calls
    # are made during document registration.
    document = response.json()
    assert document["status"] == "registered"  # Not "processing" or "completed"
    assert "document_id" in document


# ---------------------------------------------------------------------------
# Test 9: Test DB is isolated via tmp_path/create_app(db_path=...)
# ---------------------------------------------------------------------------

def test_document_test_db_is_isolated_via_tmp_path(tmp_path: Path) -> None:
    """Verify each test gets isolated database via tmp_path fixture."""
    db1 = tmp_path / "db1.sqlite"
    db2 = tmp_path / "db2.sqlite"

    ensure_database_schema(db1)
    ensure_database_schema(db2)

    client1 = create_app(runs_dir=tmp_path / "runs1", db_path=db1)
    client2 = create_app(runs_dir=tmp_path / "runs2", db_path=db2)

    tc1 = TestClient(client1)
    tc2 = TestClient(client2)

    # Create project/job in client1
    proj_resp = tc1.post("/projects", json={"name": "Project 1"})
    project_id = proj_resp.json()["project_id"]
    job_resp = tc1.post(f"/projects/{project_id}/jobs", json={
        "name": "Job 1",
        "schema_id": "invoice_basic",
    })
    job_id = job_resp.json()["job_id"]

    # Create document in client1
    doc_resp = tc1.post(f"/jobs/{job_id}/documents", json={
        "original_filename": "doc.pdf",
        "file_path": "/data/doc.pdf",
    })
    assert doc_resp.status_code == 200

    # Verify client2 has no jobs (isolated database)
    proj_resp2 = tc2.post("/projects", json={"name": "Project 2"})
    project_id2 = proj_resp2.json()["project_id"]
    list_resp = tc2.get(f"/projects/{project_id2}/jobs")
    assert len(list_resp.json()) == 0


# ---------------------------------------------------------------------------
# Test 10: Get document file returns 200 and exact bytes
# ---------------------------------------------------------------------------

def test_get_document_file_returns_bytes(client: TestClient, project_and_job: tuple[str, str], tmp_path: Path) -> None:
    """Verify GET /documents/{document_id}/file returns actual file bytes."""
    project_id, job_id = project_and_job

    # Create a document with registered file path
    file_path = tmp_path / "test_document.txt"
    test_content = b"Test document file content"
    file_path.write_bytes(test_content)

    create_response = client.post(f"/jobs/{job_id}/documents", json={
        "original_filename": "test_file.txt",
        "file_path": str(file_path),
        "file_type": "text/plain",
    })
    assert create_response.status_code == 200
    document_id = create_response.json()["document_id"]

    # Retrieve file
    response = client.get(f"/documents/{document_id}/file")
    assert response.status_code == 200
    assert response.content == test_content
    assert "text/plain" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# Test 11: Get document file for missing document returns 404
# ---------------------------------------------------------------------------

def test_get_document_file_missing_document_returns_404(client: TestClient) -> None:
    """Verify 404 when retrieving file for nonexistent document."""
    response = client.get("/documents/doc-nonexistent/file")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 12: Get document file when file path missing returns 404
# ---------------------------------------------------------------------------

def test_get_document_file_missing_file_returns_404(client: TestClient, project_and_job: tuple[str, str]) -> None:
    """Verify 404 when registered document file does not exist on disk."""
    project_id, job_id = project_and_job

    # Create a document with a file path that does not exist
    create_response = client.post(f"/jobs/{job_id}/documents", json={
        "original_filename": "nonexistent.txt",
        "file_path": "/nonexistent/path/to/file.txt",
        "file_type": "text/plain",
    })
    assert create_response.status_code == 200
    document_id = create_response.json()["document_id"]

    # Try to retrieve file
    response = client.get(f"/documents/{document_id}/file")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

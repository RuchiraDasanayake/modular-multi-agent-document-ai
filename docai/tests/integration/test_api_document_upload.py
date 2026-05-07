"""Integration tests for POST /jobs/{job_id}/documents/upload endpoint."""

import hashlib
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


# Test 1: basic upload succeeds
def test_upload_document_succeeds(client: TestClient, project_and_job: tuple[str, str]):
    """Upload document under existing job succeeds."""
    project_id, job_id = project_and_job

    content = b"Test document content"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    assert data["document_id"].startswith("doc-")
    assert data["job_id"] == job_id
    assert data["project_id"] == project_id


# Test 2: uploaded file exists on disk
def test_uploaded_file_exists_on_disk(client: TestClient, project_and_job: tuple[str, str]):
    """Saved file exists on backend disk."""
    project_id, job_id = project_and_job

    content = b"Test document content"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    file_path = Path(data["file_path"])
    assert file_path.exists()
    assert file_path.is_file()


# Test 3: uploaded file content matches
def test_uploaded_file_content_matches(client: TestClient, project_and_job: tuple[str, str]):
    """Saved file content matches uploaded bytes."""
    project_id, job_id = project_and_job

    content = b"Test document content with more bytes"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    file_path = Path(data["file_path"])
    assert file_path.read_bytes() == content


# Test 4: file_path is inside upload directory
def test_file_path_is_inside_upload_dir(client: TestClient, project_and_job: tuple[str, str], tmp_path: Path):
    """Returned file_path is inside runs_dir/uploads/jobs/{job_id}."""
    project_id, job_id = project_and_job

    content = b"Test document"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    file_path = Path(data["file_path"])
    expected_prefix = tmp_path / "runs" / "uploads" / "jobs" / job_id
    assert str(file_path).startswith(str(expected_prefix))


# Test 5: file_hash is computed correctly
def test_file_hash_is_computed_correctly(client: TestClient, project_and_job: tuple[str, str]):
    """file_hash equals sha256(content).hexdigest()."""
    project_id, job_id = project_and_job

    content = b"Test document for hashing"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    expected_hash = hashlib.sha256(content).hexdigest()
    assert data["file_hash"] == expected_hash


# Test 6: file_type is stored
def test_file_type_is_stored(client: TestClient, project_and_job: tuple[str, str]):
    """file_type from content_type is stored."""
    project_id, job_id = project_and_job

    content = b"Test document"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    assert data["file_type"] in ("text/plain", "txt")


# Test 7: missing job returns 404
def test_missing_job_returns_404(client: TestClient):
    """POST to nonexistent job_id returns 404."""
    content = b"Test document"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post("/jobs/nonexistent-job/documents/upload", files=files)

    assert response.status_code == 404


# Test 8: empty upload returns 400
def test_empty_upload_returns_400(client: TestClient, project_and_job: tuple[str, str]):
    """Empty file upload returns 400."""
    project_id, job_id = project_and_job

    content = b""
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 400


# Test 9: POSIX path traversal sanitized
def test_posix_path_traversal_sanitized(client: TestClient, project_and_job: tuple[str, str]):
    """POSIX path traversal filename is sanitized."""
    project_id, job_id = project_and_job

    content = b"Test document"
    # Filename with path traversal
    files = {"file": ("../../etc/passwd", content, "text/plain")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    # original_filename should be just the basename
    assert data["original_filename"] == "passwd"
    # Verify file is inside correct directory
    file_path = Path(data["file_path"])
    expected_prefix = Path(client.app.state.runs_dir) / "uploads" / "jobs" / job_id
    assert str(file_path).startswith(str(expected_prefix))


# Test 10: Windows path traversal sanitized
def test_windows_path_traversal_sanitized(client: TestClient, project_and_job: tuple[str, str]):
    """Windows path traversal filename is sanitized."""
    project_id, job_id = project_and_job

    content = b"Test document"
    # Filename with Windows path traversal
    files = {"file": ("..\\..\\windows\\system32\\cmd.exe", content, "application/octet-stream")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    # original_filename should be just the basename
    assert data["original_filename"] == "cmd.exe"


# Test 11: repeated upload no overwrite
def test_repeated_upload_no_overwrite(client: TestClient, project_and_job: tuple[str, str]):
    """Repeated upload with same filename does not overwrite previous file."""
    project_id, job_id = project_and_job

    content1 = b"First document"
    files1 = {"file": ("test.txt", content1, "text/plain")}
    response1 = client.post(f"/jobs/{job_id}/documents/upload", files=files1)
    assert response1.status_code == 201
    path1 = Path(response1.json()["file_path"])

    content2 = b"Second document"
    files2 = {"file": ("test.txt", content2, "text/plain")}
    response2 = client.post(f"/jobs/{job_id}/documents/upload", files=files2)
    assert response2.status_code == 201
    path2 = Path(response2.json()["file_path"])

    # Paths should be different (unique stored filename)
    assert path1 != path2
    # Both files should exist with their original content
    assert path1.read_bytes() == content1
    assert path2.read_bytes() == content2


# Test 12: upload does not invoke extraction
def test_upload_does_not_invoke_extraction(client: TestClient, project_and_job: tuple[str, str], tmp_path: Path):
    """Upload does not invoke extraction/orchestration/application runtime."""
    project_id, job_id = project_and_job

    content = b"Test document"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 201

    # Verify no artifacts directory was created
    artifacts_dir = tmp_path / "runs" / "artifacts"
    assert not artifacts_dir.exists()


# Test 13: upload does not create run artifacts
def test_upload_does_not_create_run_artifacts(client: TestClient, project_and_job: tuple[str, str]):
    """Upload does not create run artifacts."""
    project_id, job_id = project_and_job

    content = b"Test document"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 201

    # Verify no runs were created
    runs_response = client.get(f"/jobs/{job_id}/runs")
    assert runs_response.status_code == 200
    assert runs_response.json() == []


# Test 14: upload does not attach run documents
def test_upload_does_not_attach_run_documents(client: TestClient, project_and_job: tuple[str, str]):
    """Upload does not create or attach run documents."""
    project_id, job_id = project_and_job

    content = b"Test document"
    files = {"file": ("test.txt", content, "text/plain")}
    response = client.post(f"/jobs/{job_id}/documents/upload", files=files)

    assert response.status_code == 201

    # Verify no runs exist
    runs_response = client.get(f"/jobs/{job_id}/runs")
    assert runs_response.status_code == 200
    assert runs_response.json() == []


# Test 15: old POST /runs unchanged
def test_old_post_runs_unchanged(client: TestClient):
    """Old standalone POST /runs still works unchanged."""
    content = b"Old format test"
    files = {"files": ("test.txt", content, "text/plain")}
    data = {"mode": "stub"}
    response = client.post("/runs", files=files, data=data)

    assert response.status_code == 200
    result = response.json()
    assert "run_id" in result
    assert result["is_stub"] is True


def test_upload_rejects_oversized_file_with_413(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured max upload size is enforced for /jobs/{job_id}/documents/upload."""
    monkeypatch.setenv("DOCAI_MAX_UPLOAD_BYTES", "32")
    db_path = tmp_path / "oversize.db"
    ensure_database_schema(db_path)
    oversized_client = TestClient(create_app(runs_dir=tmp_path / "runs", db_path=db_path))

    proj = oversized_client.post("/projects", json={"name": "Oversize"}).json()
    job = oversized_client.post(
        f"/projects/{proj['project_id']}/jobs",
        json={"name": "Oversize Job", "schema_id": "invoice_basic"},
    ).json()

    files = {"file": ("big.txt", b"a" * 128, "text/plain")}
    response = oversized_client.post(f"/jobs/{job['job_id']}/documents/upload", files=files)
    assert response.status_code == 413


def test_legacy_post_runs_rejects_oversized_file_with_413(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured max upload size is enforced for legacy POST /runs."""
    monkeypatch.setenv("DOCAI_MAX_UPLOAD_BYTES", "32")
    db_path = tmp_path / "legacy-oversize.db"
    ensure_database_schema(db_path)
    oversized_client = TestClient(create_app(runs_dir=tmp_path / "runs", db_path=db_path))

    files = {"files": ("big.txt", b"a" * 128, "text/plain")}
    response = oversized_client.post("/runs", data={"mode": "stub"}, files=files)
    assert response.status_code == 413


def test_legacy_post_runs_unsafe_filename_cannot_escape_upload_dir(client: TestClient) -> None:
    """Unsafe filename for legacy /runs upload stays contained under runs/uploads/{run_id}."""
    files = {"files": ("..\\..\\outside.txt", b"legacy upload", "text/plain")}
    response = client.post("/runs", data={"mode": "stub"}, files=files)
    assert response.status_code == 200

    run_id = response.json()["run_id"]
    upload_dir = Path(client.app.state.runs_dir) / "uploads" / run_id
    assert upload_dir.exists()

    escaped_target = Path(client.app.state.runs_dir).parent / "outside.txt"
    assert not escaped_target.exists()
    assert all(".." not in p.name for p in upload_dir.iterdir())


# Test 16: DB and runs_dir isolation
def test_db_and_runs_dir_isolation(tmp_path: Path):
    """Two clients with separate tmp_path instances have isolated state."""
    # Client 1
    db_path_1 = tmp_path / "db1" / "test.db"
    db_path_1.parent.mkdir(parents=True)
    ensure_database_schema(db_path_1)
    app_1 = create_app(runs_dir=tmp_path / "runs1", db_path=db_path_1)
    client_1 = TestClient(app_1)

    # Create project and job in client 1
    proj_resp = client_1.post("/projects", json={"name": "Project 1"})
    project_id_1 = proj_resp.json()["project_id"]
    job_resp = client_1.post(f"/projects/{project_id_1}/jobs", json={
        "name": "Job 1",
        "schema_id": "invoice_basic",
    })
    job_id_1 = job_resp.json()["job_id"]

    # Upload to job in client 1
    content = b"Document in client 1"
    files = {"file": ("test.txt", content, "text/plain")}
    response_1 = client_1.post(f"/jobs/{job_id_1}/documents/upload", files=files)
    assert response_1.status_code == 201

    # Client 2 (separate database and runs_dir)
    db_path_2 = tmp_path / "db2" / "test.db"
    db_path_2.parent.mkdir(parents=True)
    ensure_database_schema(db_path_2)
    app_2 = create_app(runs_dir=tmp_path / "runs2", db_path=db_path_2)
    client_2 = TestClient(app_2)

    # Verify job from client 1 does not exist in client 2
    response_2 = client_2.get(f"/jobs/{job_id_1}")
    assert response_2.status_code == 404

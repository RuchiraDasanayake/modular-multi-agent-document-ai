"""Integration tests for Projects and Jobs API endpoints."""

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


# ---------------------------------------------------------------------------
# Test 1: Create project
# ---------------------------------------------------------------------------

def test_create_project(client: TestClient) -> None:
    """Verify project creation via POST /projects."""
    response = client.post("/projects", json={
        "name": "Test Project",
        "description": "A test project"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"].startswith("proj-")
    assert data["name"] == "Test Project"
    assert data["description"] == "A test project"
    assert data["status"] == "active"
    assert "created_at" in data


# ---------------------------------------------------------------------------
# Test 2: List projects
# ---------------------------------------------------------------------------

def test_list_projects(client: TestClient) -> None:
    """Verify listing projects via GET /projects."""
    # Create two projects
    client.post("/projects", json={"name": "Project 1"})
    client.post("/projects", json={"name": "Project 2"})

    response = client.get("/projects")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = {p["name"] for p in data}
    assert "Project 1" in names
    assert "Project 2" in names


# ---------------------------------------------------------------------------
# Test 3: Get project
# ---------------------------------------------------------------------------

def test_get_project(client: TestClient) -> None:
    """Verify retrieving single project via GET /projects/{project_id}."""
    create_response = client.post("/projects", json={
        "name": "Specific Project",
        "description": "To retrieve"
    })
    project_id = create_response.json()["project_id"]

    response = client.get(f"/projects/{project_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == project_id
    assert data["name"] == "Specific Project"
    assert data["description"] == "To retrieve"


# ---------------------------------------------------------------------------
# Test 4: Get missing project returns 404
# ---------------------------------------------------------------------------

def test_get_missing_project_returns_404(client: TestClient) -> None:
    """Verify 404 when project does not exist."""
    response = client.get("/projects/proj-nonexistent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 5: Create job under project
# ---------------------------------------------------------------------------

def test_create_job_under_project(client: TestClient) -> None:
    """Verify job creation via POST /projects/{project_id}/jobs."""
    proj_response = client.post("/projects", json={"name": "Project for Jobs"})
    project_id = proj_response.json()["project_id"]

    response = client.post(f"/projects/{project_id}/jobs", json={
        "name": "Test Job",
        "schema_id": "invoice_basic",
        "job_type": "training"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"].startswith("job-")
    assert data["project_id"] == project_id
    assert data["name"] == "Test Job"
    assert data["schema_id"] == "invoice_basic"
    assert data["job_type"] == "training"
    assert data["status"] == "queued"
    assert "created_at" in data


# ---------------------------------------------------------------------------
# Test 6: List jobs for project
# ---------------------------------------------------------------------------

def test_list_jobs_for_project(client: TestClient) -> None:
    """Verify listing jobs via GET /projects/{project_id}/jobs."""
    proj_response = client.post("/projects", json={"name": "Project for Multiple Jobs"})
    project_id = proj_response.json()["project_id"]

    # Create two jobs
    client.post(f"/projects/{project_id}/jobs", json={
        "name": "Job 1",
        "schema_id": "invoice_basic"
    })
    client.post(f"/projects/{project_id}/jobs", json={
        "name": "Job 2",
        "schema_id": "invoice_basic"
    })

    response = client.get(f"/projects/{project_id}/jobs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = {j["name"] for j in data}
    assert "Job 1" in names
    assert "Job 2" in names


# ---------------------------------------------------------------------------
# Test 7: Get job
# ---------------------------------------------------------------------------

def test_get_job(client: TestClient) -> None:
    """Verify retrieving single job via GET /jobs/{job_id}."""
    proj_response = client.post("/projects", json={"name": "Project"})
    project_id = proj_response.json()["project_id"]

    job_response = client.post(f"/projects/{project_id}/jobs", json={
        "name": "Specific Job",
        "schema_id": "invoice_basic"
    })
    job_id = job_response.json()["job_id"]

    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["name"] == "Specific Job"
    assert data["schema_id"] == "invoice_basic"


# ---------------------------------------------------------------------------
# Test 8: Missing project when creating job returns 404
# ---------------------------------------------------------------------------

def test_missing_project_when_creating_job_returns_404(client: TestClient) -> None:
    """Verify 404 when creating job under nonexistent project."""
    response = client.post("/projects/proj-nonexistent/jobs", json={
        "name": "Job",
        "schema_id": "invoice_basic"
    })
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 9: Invalid schema_id when creating job returns 400
# ---------------------------------------------------------------------------

def test_invalid_schema_id_when_creating_job_returns_404(client: TestClient) -> None:
    """Verify 404 when schema_id does not exist (built-in or persisted)."""
    proj_response = client.post("/projects", json={"name": "Project"})
    project_id = proj_response.json()["project_id"]

    response = client.post(f"/projects/{project_id}/jobs", json={
        "name": "Job",
        "schema_id": "nonexistent_schema"
    })
    assert response.status_code == 404
    assert "schema" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 10: API test DB is isolated via temp path
# ---------------------------------------------------------------------------

def test_api_test_db_is_isolated_via_temp_path(tmp_path: Path) -> None:
    """Verify each test gets isolated database via tmp_path."""
    db1 = tmp_path / "db1.sqlite"
    db2 = tmp_path / "db2.sqlite"

    ensure_database_schema(db1)
    ensure_database_schema(db2)

    client1 = TestClient(create_app(runs_dir=tmp_path / "runs1", db_path=db1))
    client2 = TestClient(create_app(runs_dir=tmp_path / "runs2", db_path=db2))

    # Create project in client1
    response1 = client1.post("/projects", json={"name": "Project in DB1"})
    assert response1.status_code == 200

    # Verify client2 has no projects (isolated database)
    response2 = client2.get("/projects")
    assert response2.status_code == 200
    assert len(response2.json()) == 0

    # Verify client1 has the project
    response1_list = client1.get("/projects")
    assert len(response1_list.json()) == 1
    assert response1_list.json()[0]["name"] == "Project in DB1"

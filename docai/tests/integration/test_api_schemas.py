"""Integration tests for extraction schema persistence API endpoints."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docai_core.api.app import create_app
from docai_core.persistence import ensure_database_schema


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    ensure_database_schema(db_path)
    return db_path


@pytest.fixture()
def client(tmp_db: Path, tmp_path: Path) -> TestClient:
    app = create_app(runs_dir=tmp_path / "runs", db_path=tmp_db)
    return TestClient(app)


def _create_project(client: TestClient) -> str:
    response = client.post("/projects", json={"name": "Schema Project"})
    assert response.status_code == 200
    return response.json()["project_id"]


def _schema_payload(name: str = "Invoice Schema") -> dict:
    return {
        "name": name,
        "document_type": "invoice",
        "fields": [
            {
                "id": "f1",
                "name": "Invoice Number",
                "type": "string",
                "required": True,
                "description": "Primary invoice identifier",
            }
        ],
        "tables": [
            {
                "id": "t1",
                "name": "Line Items",
                "description": "Invoice rows",
                "columns": [
                    {"id": "c1", "name": "Description", "type": "string"},
                ],
            }
        ],
    }


def test_create_schema_under_project_persists(client: TestClient) -> None:
    project_id = _create_project(client)
    response = client.post(f"/projects/{project_id}/schemas", json=_schema_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["schema_id"].startswith("schema-")
    assert data["project_id"] == project_id
    assert data["name"] == "Invoice Schema"
    assert data["version"] == 1
    assert data["fields"][0]["name"] == "Invoice Number"
    assert data["tables"][0]["name"] == "Line Items"


def test_list_and_get_schema_by_id(client: TestClient) -> None:
    project_id = _create_project(client)
    create_response = client.post(f"/projects/{project_id}/schemas", json=_schema_payload("Alpha"))
    schema_id = create_response.json()["schema_id"]

    listed = client.get(f"/projects/{project_id}/schemas")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["schema_id"] == schema_id

    fetched = client.get(f"/schemas/{schema_id}")
    assert fetched.status_code == 200
    assert fetched.json()["schema_id"] == schema_id
    assert fetched.json()["fields"][0]["name"] == "Invoice Number"
    assert fetched.json()["tables"][0]["columns"][0]["name"] == "Description"


def test_update_schema_changes_payload_and_survives_reload(client: TestClient) -> None:
    project_id = _create_project(client)
    create_response = client.post(f"/projects/{project_id}/schemas", json=_schema_payload("Before Update"))
    schema_id = create_response.json()["schema_id"]

    update_payload = _schema_payload("After Update")
    update_payload["fields"].append(
        {
            "id": "f2",
            "name": "Total Amount",
            "type": "currency",
            "required": False,
            "description": "",
        }
    )
    update_payload["tables"][0]["columns"].append(
        {"id": "c2", "name": "Amount", "type": "currency"}
    )

    updated = client.put(f"/schemas/{schema_id}", json=update_payload)
    assert updated.status_code == 200
    assert updated.json()["name"] == "After Update"
    assert updated.json()["version"] == 2
    assert len(updated.json()["fields"]) == 2

    fetched = client.get(f"/schemas/{schema_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "After Update"
    assert fetched.json()["version"] == 2
    assert fetched.json()["fields"][1]["name"] == "Total Amount"
    assert fetched.json()["tables"][0]["columns"][1]["name"] == "Amount"


def test_missing_project_or_schema_returns_404(client: TestClient) -> None:
    list_missing_project = client.get("/projects/proj-missing/schemas")
    assert list_missing_project.status_code == 404

    create_missing_project = client.post(
        "/projects/proj-missing/schemas",
        json=_schema_payload(),
    )
    assert create_missing_project.status_code == 404

    get_missing_schema = client.get("/schemas/schema-missing")
    assert get_missing_schema.status_code == 404

    put_missing_schema = client.put("/schemas/schema-missing", json=_schema_payload())
    assert put_missing_schema.status_code == 404


def test_schema_initialization_upgrades_existing_db(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS projects (project_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.commit()

    ensure_database_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='extraction_schemas'"
        ).fetchone()
    assert row is not None

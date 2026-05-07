from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docai_core.api.app import create_app
from docai_core.persistence import ensure_database_schema


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    ensure_database_schema(db)
    return db


@pytest.fixture()
def client(tmp_path: Path, db_path: Path) -> TestClient:
    app = create_app(db_path=db_path, runs_dir=tmp_path / "runs")
    return TestClient(app)


def _create_project(client: TestClient) -> str:
    response = client.post("/projects", json={"name": "Profile Project"})
    assert response.status_code == 200
    return response.json()["project_id"]


def test_create_and_get_extraction_profile(client: TestClient) -> None:
    project_id = _create_project(client)

    created = client.post(
        f"/projects/{project_id}/extraction-profiles",
        json={
            "name": "invoice-local-text",
            "schema_id": "invoice_basic",
            "mode": "local_text",
            "ocr_strategy": "router_default",
            "validation_level": "standard",
            "is_default": True,
        },
    )
    assert created.status_code == 200
    profile = created.json()
    assert profile["project_id"] == project_id
    assert profile["schema_id"] == "invoice_basic"
    assert profile["mode"] == "local_text"
    assert profile["is_default"] is True

    fetched = client.get(f"/extraction-profiles/{profile['profile_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["profile_id"] == profile["profile_id"]


def test_list_extraction_profiles(client: TestClient) -> None:
    project_id = _create_project(client)

    for name in ["p1", "p2"]:
        response = client.post(
            f"/projects/{project_id}/extraction-profiles",
            json={
                "name": name,
                "schema_id": "invoice_basic",
                "mode": "stub",
                "ocr_strategy": "router_default",
                "validation_level": "standard",
                "is_default": False,
            },
        )
        assert response.status_code == 200

    listed = client.get(f"/projects/{project_id}/extraction-profiles")
    assert listed.status_code == 200
    names = {item["name"] for item in listed.json()}
    assert {"p1", "p2"}.issubset(names)


def test_create_job_from_profile_uses_profile_schema_and_default_mode(client: TestClient) -> None:
    project_id = _create_project(client)
    profile = client.post(
        f"/projects/{project_id}/extraction-profiles",
        json={
            "name": "profile-job",
            "schema_id": "invoice_basic",
            "mode": "local_text",
            "ocr_strategy": "router_default",
            "validation_level": "strict",
            "is_default": False,
        },
    ).json()

    job_resp = client.post(
        f"/projects/{project_id}/jobs",
        json={
            "name": "job-from-profile",
            "profile_id": profile["profile_id"],
            "job_type": "training",
        },
    )
    assert job_resp.status_code == 200
    job = job_resp.json()
    assert job["profile_id"] == profile["profile_id"]
    assert job["schema_id"] == "invoice_basic"
    assert job["default_mode"] == "local_text"


def test_adaptive_advice_does_not_create_profile_automatically(client: TestClient) -> None:
    project_id = _create_project(client)

    before = client.get(f"/projects/{project_id}/extraction-profiles")
    assert before.status_code == 200
    assert before.json() == []

    advice = client.get(f"/projects/{project_id}/adaptive-routing/advice")
    assert advice.status_code == 200

    after = client.get(f"/projects/{project_id}/extraction-profiles")
    assert after.status_code == 200
    assert after.json() == []


def test_missing_profile_returns_404(client: TestClient) -> None:
    project_id = _create_project(client)

    get_missing = client.get("/extraction-profiles/profile-missing")
    assert get_missing.status_code == 404

    job_missing = client.post(
        f"/projects/{project_id}/jobs",
        json={"name": "bad-job", "profile_id": "profile-missing"},
    )
    assert job_missing.status_code == 404


def test_run_mode_omitted_defaults_to_job_default_mode(client: TestClient) -> None:
    project_id = _create_project(client)
    profile = client.post(
        f"/projects/{project_id}/extraction-profiles",
        json={
            "name": "profile-default-mode",
            "schema_id": "invoice_basic",
            "mode": "local_text",
            "ocr_strategy": "router_default",
            "validation_level": "standard",
            "is_default": False,
        },
    ).json()

    job_resp = client.post(
        f"/projects/{project_id}/jobs",
        json={
            "name": "job-from-profile-default-mode",
            "profile_id": profile["profile_id"],
        },
    )
    assert job_resp.status_code == 200
    job = job_resp.json()
    assert job["default_mode"] == "local_text"

    # Create run without specifying mode - should default to job's default_mode
    run_resp = client.post(f"/jobs/{job['job_id']}/runs", json={})
    assert run_resp.status_code == 200
    run = run_resp.json()
    assert run["mode"] == "local_text"


def test_profile_with_unknown_schema_fails_clearly(client: TestClient) -> None:
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/extraction-profiles",
        json={
            "name": "bad-schema-profile",
            "schema_id": "unknown_schema_123",
            "mode": "stub",
            "ocr_strategy": "router_default",
            "validation_level": "standard",
            "is_default": False,
        },
    )
    assert response.status_code == 404
    assert "schema" in response.json()["detail"].lower()


def test_profile_with_invalid_mode_fails_clearly(client: TestClient) -> None:
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/extraction-profiles",
        json={
            "name": "bad-mode-profile",
            "schema_id": "invoice_basic",
            "mode": "invalid_mode_123",
            "ocr_strategy": "router_default",
            "validation_level": "standard",
            "is_default": False,
        },
    )
    assert response.status_code == 422
    assert "mode" in response.json()["detail"].lower()


def test_setting_one_profile_as_default_does_not_corrupt_others(client: TestClient) -> None:
    project_id = _create_project(client)

    # Create two profiles
    profile1 = client.post(
        f"/projects/{project_id}/extraction-profiles",
        json={
            "name": "profile1",
            "schema_id": "invoice_basic",
            "mode": "stub",
            "ocr_strategy": "router_default",
            "validation_level": "standard",
            "is_default": False,
        },
    ).json()

    profile2 = client.post(
        f"/projects/{project_id}/extraction-profiles",
        json={
            "name": "profile2",
            "schema_id": "invoice_basic",
            "mode": "local_text",
            "ocr_strategy": "router_default",
            "validation_level": "standard",
            "is_default": False,
        },
    ).json()

    # Set profile1 as default
    update1 = client.put(
        f"/extraction-profiles/{profile1['profile_id']}",
        json={
            "name": "profile1",
            "schema_id": "invoice_basic",
            "mode": "stub",
            "ocr_strategy": "router_default",
            "validation_level": "standard",
            "is_default": True,
        },
    )
    assert update1.status_code == 200

    # Check profile1 is default, profile2 is not
    get1 = client.get(f"/extraction-profiles/{profile1['profile_id']}")
    get2 = client.get(f"/extraction-profiles/{profile2['profile_id']}")
    assert get1.json()["is_default"] is True
    assert get2.json()["is_default"] is False

    # Set profile2 as default
    update2 = client.put(
        f"/extraction-profiles/{profile2['profile_id']}",
        json={
            "name": "profile2",
            "schema_id": "invoice_basic",
            "mode": "local_text",
            "ocr_strategy": "router_default",
            "validation_level": "standard",
            "is_default": True,
        },
    )
    assert update2.status_code == 200

    # Check profile2 is default, profile1 is no longer default
    get1_after = client.get(f"/extraction-profiles/{profile1['profile_id']}")
    get2_after = client.get(f"/extraction-profiles/{profile2['profile_id']}")
    assert get1_after.json()["is_default"] is False
    assert get2_after.json()["is_default"] is True


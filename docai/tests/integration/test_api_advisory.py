"""Integration tests for POST /advisory/recommend.

Advisory endpoint is read-only: no run artifacts created, no policy files mutated,
no runtime pipeline invoked.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docai_core.api.app import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    app = create_app(runs_dir=tmp_path / "runs")
    return TestClient(app)


def _record(
    policy_id: str,
    document_type: str = "invoice",
    quality_bin: str = "medium",
    document_count: int = 20,
    field_f1: float | None = 0.85,
    field_accuracy: float | None = 0.87,
    missing_rate: float | None = 0.05,
    correction_rate: float | None = 0.03,
) -> dict:
    return {
        "policy_id": policy_id,
        "policy_version": "v1",
        "document_type": document_type,
        "quality_bin": quality_bin,
        "document_count": document_count,
        "field_accuracy": field_accuracy,
        "field_precision": field_accuracy,
        "field_recall": field_accuracy,
        "field_f1": field_f1,
        "missing_rate": missing_rate,
        "correction_rate": correction_rate,
        "evaluated_at": "2026-05-01T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Test 1: endpoint returns a recommendation when eligible evidence is provided
# ---------------------------------------------------------------------------

def test_advisory_recommend_endpoint_returns_recommendation(client: TestClient) -> None:
    payload = {
        "document_type": "invoice",
        "quality_bin": "medium",
        "min_document_count": 10,
        "records": [
            _record("policy_kv",    field_f1=0.70, document_count=15),
            _record("policy_model", field_f1=0.92, document_count=20),
        ],
    }
    r = client.post("/advisory/recommend", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "recommended"
    assert data["recommendation"] is not None
    assert data["recommendation"]["policy_id"] == "policy_model"
    assert data["recommendation"]["evidence_document_count"] == 20
    assert data["recommendation"]["score"] is not None
    assert 0.0 <= data["recommendation"]["score"] <= 1.0
    assert data["reason"]


# ---------------------------------------------------------------------------
# Test 2: no_recommendation when records list is empty
# ---------------------------------------------------------------------------

def test_advisory_recommend_endpoint_returns_no_recommendation_without_evidence(
    client: TestClient,
) -> None:
    payload = {
        "document_type": "invoice",
        "quality_bin": "medium",
        "min_document_count": 10,
        "records": [],
    }
    r = client.post("/advisory/recommend", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "no_recommendation"
    assert data["recommendation"] is None
    assert data["reason"]


# ---------------------------------------------------------------------------
# Test 3: respects min_document_count — record below threshold excluded
# ---------------------------------------------------------------------------

def test_advisory_recommend_endpoint_respects_min_document_count(
    client: TestClient,
) -> None:
    payload = {
        "document_type": "invoice",
        "quality_bin": "medium",
        "min_document_count": 10,
        "records": [
            _record("sparse_policy", document_count=4, field_f1=0.99),
        ],
    }
    r = client.post("/advisory/recommend", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "no_recommendation"
    assert data["recommendation"] is None


# ---------------------------------------------------------------------------
# Test 4: policy JSON files not mutated after endpoint call
# ---------------------------------------------------------------------------

def test_advisory_endpoint_does_not_mutate_policy_files(
    client: TestClient, tmp_path: Path
) -> None:
    policy_dir = Path(__file__).resolve().parents[2] / "configs" / "policies"
    snapshots = {p: p.read_text(encoding="utf-8") for p in policy_dir.glob("*.json")}

    payload = {
        "document_type": "invoice",
        "quality_bin": "medium",
        "min_document_count": 10,
        "records": [_record("invoice_basic_local_v1", document_count=15)],
    }
    r = client.post("/advisory/recommend", json=payload)
    assert r.status_code == 200

    for p, original in snapshots.items():
        assert p.read_text(encoding="utf-8") == original, f"{p.name} was mutated"


# ---------------------------------------------------------------------------
# Test 5: endpoint does not create run artifacts
# ---------------------------------------------------------------------------

def test_advisory_endpoint_does_not_trigger_runtime_run(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    app = create_app(runs_dir=runs_dir)
    c = TestClient(app)

    payload = {
        "document_type": "invoice",
        "quality_bin": "medium",
        "min_document_count": 10,
        "records": [_record("some_policy", document_count=15)],
    }
    r = c.post("/advisory/recommend", json=payload)
    assert r.status_code == 200

    # No run artifacts should exist — advisory never calls JobRunService
    artifacts_dir = runs_dir / "artifacts"
    assert not artifacts_dir.exists() or not any(artifacts_dir.rglob("*"))

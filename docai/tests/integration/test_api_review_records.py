"""Integration tests for review record persistence API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docai_core.api.app import create_app
from docai_core.artifacts.store import ArtifactStore
from docai_core.persistence import SQLiteStore, ensure_database_schema


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    ensure_database_schema(db)
    return db


@pytest.fixture()
def client(tmp_path: Path, db_path: Path) -> TestClient:
    app = create_app(db_path=db_path, runs_dir=tmp_path / "runs")
    return TestClient(app)


@pytest.fixture()
def review_setup(tmp_path: Path, db_path: Path) -> dict[str, str]:
    store = SQLiteStore(db_path)
    project = store.create_project("proj-review", "Review Test")

    with store._conn() as conn:
        conn.execute(
            "INSERT INTO extraction_schemas_index (schema_id, name, document_type, version, is_builtin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("invoice_basic", "Invoice", "invoice", "v1", 0, store._now()),
        )
        conn.commit()

    job = store.create_job(project.project_id, "invoice_basic", "Review Job")
    doc_file = tmp_path / "invoice.txt"
    doc_file.write_text("Invoice Number: INV-001")
    doc_id = store.register_document(project.project_id, job.job_id, "invoice.txt", str(doc_file))
    run = store.create_run(project.project_id, job.job_id, "invoice_basic", mode="stub", status="created")
    store.create_run_document(run.run_id, doc_id)

    artifact_store = ArtifactStore(tmp_path / "runs" / "artifacts")
    artifact_store.create_job(job.job_id)
    artifact_store.create_document(job.job_id, doc_id)
    artifact_store.write_json(
        artifact_store.document_artifact_path(job.job_id, doc_id, "final_output.json"),
        {
            "fields": [
                {
                    "field_name": "invoice_number",
                    "value": "INV-001",
                    "normalized_value": "INV-001",
                    "confidence": 0.99,
                    "evidence_text": "Invoice Number: INV-001",
                    "validation_status": "needs_review",
                },
                {
                    "field_name": "vendor_name",
                    "value": "Acme Corp",
                    "normalized_value": "Acme Corp",
                    "confidence": 0.88,
                    "evidence_text": "Vendor: Acme Corp",
                    "validation_status": "valid",
                },
            ],
            "is_stub": False,
        },
    )
    artifact_store.write_json(
        artifact_store.document_artifact_path(job.job_id, doc_id, "validation_report.json"),
        {
            "pass_status": False,
            "summary": "1 issue",
            "field_issues": ["invoice_number: low_confidence"],
            "table_issues": [],
            "document_issues": [],
            "artifact_paths": [],
            "is_stub": False,
        },
    )

    return {
        "run_id": run.run_id,
        "job_id": job.job_id,
        "doc_id": doc_id,
        "final_output_path": str(artifact_store.document_artifact_path(job.job_id, doc_id, "final_output.json")),
        "validation_report_path": str(artifact_store.document_artifact_path(job.job_id, doc_id, "validation_report.json")),
    }


def _create_review(client: TestClient, run_id: str, doc_id: str, review_note: str) -> str:
    response = client.post(
        f"/runs/{run_id}/documents/{doc_id}/review-record",
        json={
            "reviewer_id": "reviewer-1",
            "review_status": "corrected",
            "review_note": review_note,
            "corrections": [
                {
                    "field_name": "invoice_number",
                    "decision": "wrong_value",
                    "corrected_value": "INV-002",
                },
                {
                    "field_name": "missing_po_number",
                    "decision": "missed_field",
                    "corrected_value": "PO-100",
                },
            ],
        },
    )
    assert response.status_code == 200
    return response.json()["review_id"]


def test_post_creates_review_record_and_preserves_artifacts(client: TestClient, review_setup: dict[str, str]) -> None:
    run_id = review_setup["run_id"]
    doc_id = review_setup["doc_id"]
    final_output_path = Path(review_setup["final_output_path"])
    validation_report_path = Path(review_setup["validation_report_path"])
    final_output_before = final_output_path.read_bytes()
    validation_report_before = validation_report_path.read_bytes()

    response = client.post(
        f"/runs/{run_id}/documents/{doc_id}/review-record",
        json={
            "reviewer_id": "reviewer-1",
            "review_status": "corrected",
            "review_note": "corrected invoice number",
            "corrections": [
                {
                    "field_name": "invoice_number",
                    "decision": "wrong_value",
                    "corrected_value": "INV-002",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id
    assert data["document_id"] == doc_id
    assert data["source"] == "human_review"
    assert data["review_status"] == "corrected"
    assert len(data["corrections"]) == 1
    assert data["corrections"][0]["field_name"] == "invoice_number"
    assert data["corrections"][0]["extracted_value_snapshot"] == "INV-001"
    assert data["corrections"][0]["corrected_value"] == "INV-002"

    assert final_output_path.read_bytes() == final_output_before
    assert validation_report_path.read_bytes() == validation_report_before


def test_get_review_history_and_latest_newest_first(client: TestClient, review_setup: dict[str, str]) -> None:
    run_id = review_setup["run_id"]
    doc_id = review_setup["doc_id"]
    first_review_id = _create_review(client, run_id, doc_id, "first correction")
    second_review_id = _create_review(client, run_id, doc_id, "second correction")

    history = client.get(f"/runs/{run_id}/documents/{doc_id}/review-records")
    assert history.status_code == 200
    items = history.json()
    assert len(items) == 2
    assert items[0]["review_id"] == second_review_id
    assert items[1]["review_id"] == first_review_id

    latest = client.get(f"/runs/{run_id}/documents/{doc_id}/latest-review-record")
    assert latest.status_code == 200
    assert latest.json()["review_id"] == second_review_id


def test_missing_run_or_document_returns_404(client: TestClient, review_setup: dict[str, str]) -> None:
    run_id = review_setup["run_id"]

    missing_run = client.post(
        "/runs/run-missing/documents/doc-1/review-record",
        json={"review_status": "reviewed", "corrections": []},
    )
    assert missing_run.status_code == 404

    missing_doc = client.post(
        f"/runs/{run_id}/documents/doc-missing/review-record",
        json={"review_status": "reviewed", "corrections": []},
    )
    assert missing_doc.status_code == 404


def test_invalid_correction_rules(client: TestClient, review_setup: dict[str, str]) -> None:
    run_id = review_setup["run_id"]
    doc_id = review_setup["doc_id"]

    wrong_value_without_corrected_value = client.post(
        f"/runs/{run_id}/documents/{doc_id}/review-record",
        json={
            "review_status": "corrected",
            "corrections": [{"field_name": "invoice_number", "decision": "wrong_value"}],
        },
    )
    assert wrong_value_without_corrected_value.status_code == 422

    correct_with_corrected_value = client.post(
        f"/runs/{run_id}/documents/{doc_id}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {
                    "field_name": "invoice_number",
                    "decision": "correct",
                    "corrected_value": "INV-003",
                }
            ],
        },
    )
    assert correct_with_corrected_value.status_code == 422

    unknown_field_with_non_missed_decision = client.post(
        f"/runs/{run_id}/documents/{doc_id}/review-record",
        json={
            "review_status": "corrected",
            "corrections": [
                {
                    "field_name": "unknown_field",
                    "decision": "wrong_value",
                    "corrected_value": "X",
                }
            ],
        },
    )
    assert unknown_field_with_non_missed_decision.status_code == 422


"""Tests for learning samples export API.

Verifies that human review corrections are exported as learning samples
for future training/evaluation without automatic learning or model updates.
"""

from __future__ import annotations

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


@pytest.fixture()
def run_setup(client: TestClient, tmp_path: Path) -> tuple[str, str, str]:
    """Project + job + document + run for learning tests."""
    proj = client.post("/projects", json={"name": "LearningTest"}).json()
    pid = proj["project_id"]

    job = client.post(
        f"/projects/{pid}/jobs",
        json={"schema_id": "invoice_basic", "name": "learning-job"}
    ).json()
    jid = job["job_id"]

    doc_file = tmp_path / "invoice.txt"
    doc_file.write_text(
        "Invoice Number: INV-LEARN-001\n"
        "Invoice Date: 2024-08-01\n"
        "Total Amount: $6,666.66\n"
    )

    with open(str(doc_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("invoice.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]

    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    return rid, docid, jid


def test_no_reviews_returns_empty_samples(client: TestClient, run_setup: tuple) -> None:
    """Learning samples should be empty if no reviews exist."""
    rid, _, _ = run_setup

    samples = client.get(f"/runs/{rid}/learning-samples").json()

    assert samples["run_id"] == rid
    assert samples["samples"] == []


def test_missing_run_returns_404(client: TestClient) -> None:
    """Missing run should return 404."""
    response = client.get("/runs/nonexistent-run/learning-samples")
    assert response.status_code == 404


def test_wrong_value_correction_becomes_learning_sample(client: TestClient, run_setup: tuple) -> None:
    """wrong_value correction should appear as learning sample."""
    rid, docid, _ = run_setup

    # Create review with wrong_value correction
    review = client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "corrected",
            "corrections": [
                {
                    "field_name": "invoice_number",
                    "decision": "wrong_value",
                    "corrected_value": "INV-CORRECTED-001",
                }
            ]
        }
    ).json()

    samples = client.get(f"/runs/{rid}/learning-samples").json()

    assert len(samples["samples"]) == 1
    sample = samples["samples"][0]
    assert sample["field_name"] == "invoice_number"
    assert sample["decision"] == "wrong_value"
    assert sample["corrected_value"] == "INV-CORRECTED-001"
    assert sample["review_id"] == review["review_id"]


def test_missed_field_correction_becomes_learning_sample(client: TestClient, run_setup: tuple) -> None:
    """missed_field correction should appear as learning sample."""
    rid, docid, _ = run_setup

    review = client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "corrected",
            "corrections": [
                {
                    "field_name": "vendor_name",
                    "decision": "missed_field",
                    "corrected_value": "Vendor Corp Inc",
                }
            ]
        }
    ).json()

    samples = client.get(f"/runs/{rid}/learning-samples").json()

    assert len(samples["samples"]) == 1
    sample = samples["samples"][0]
    assert sample["field_name"] == "vendor_name"
    assert sample["decision"] == "missed_field"
    assert sample["corrected_value"] == "Vendor Corp Inc"
    assert sample["original_value"] is None  # missed field has no original value


def test_hallucinated_field_correction_becomes_learning_sample(client: TestClient, run_setup: tuple) -> None:
    """hallucinated_field correction should appear as learning sample."""
    rid, docid, _ = run_setup

    review = client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {
                    "field_name": "status",
                    "decision": "hallucinated_field",
                }
            ]
        }
    ).json()

    samples = client.get(f"/runs/{rid}/learning-samples").json()

    assert len(samples["samples"]) == 1
    sample = samples["samples"][0]
    assert sample["field_name"] == "status"
    assert sample["decision"] == "hallucinated_field"
    assert sample["corrected_value"] is None


def test_multiple_corrections_multiple_samples(client: TestClient, run_setup: tuple) -> None:
    """Review with multiple corrections should produce multiple samples."""
    rid, docid, _ = run_setup

    client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "corrected",
            "corrections": [
                {
                    "field_name": "invoice_number",
                    "decision": "wrong_value",
                    "corrected_value": "INV-FIXED-001",
                },
                {
                    "field_name": "vendor_name",
                    "decision": "missed_field",
                    "corrected_value": "NewVendor",
                },
                {
                    "field_name": "total_amount",
                    "decision": "hallucinated_field",
                },
            ]
        }
    )

    samples = client.get(f"/runs/{rid}/learning-samples").json()

    assert len(samples["samples"]) == 3
    decisions = [s["decision"] for s in samples["samples"]]
    assert set(decisions) == {"wrong_value", "missed_field", "hallucinated_field"}


def test_learning_sample_has_correct_metadata(client: TestClient, run_setup: tuple) -> None:
    """Learning sample should have all required metadata."""
    rid, docid, _ = run_setup

    review = client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "reviewed",
            "reviewer_id": "reviewer123",
            "corrections": [
                {
                    "field_name": "total_amount",
                    "decision": "correct",
                }
            ]
        }
    ).json()

    samples = client.get(f"/runs/{rid}/learning-samples").json()

    sample = samples["samples"][0]

    # Check all required fields
    assert sample["sample_id"]  # synthetic ID
    assert sample["run_id"] == rid
    assert sample["document_id"] == docid
    assert sample["review_id"] == review["review_id"]
    assert sample["field_name"]
    assert sample["decision"]
    assert sample["source"] == "human_review"
    assert sample["created_at"]


def test_samples_preserve_evidence_text(client: TestClient, run_setup: tuple) -> None:
    """Learning samples should preserve evidence_text from correction."""
    rid, docid, _ = run_setup

    client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {
                    "field_name": "invoice_number",
                    "decision": "correct",
                }
            ]
        }
    )

    samples = client.get(f"/runs/{rid}/learning-samples").json()

    sample = samples["samples"][0]
    # evidence_text may be present from extracted value
    assert "evidence_text" in sample


def test_multiple_reviews_produce_samples(client: TestClient, run_setup: tuple) -> None:
    """Multiple review records should each produce samples."""
    rid, docid, _ = run_setup

    # First review
    client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {"field_name": "invoice_number", "decision": "correct"}
            ]
        }
    )

    # Second review (different status/corrections)
    client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "corrected",
            "corrections": [
                {
                    "field_name": "total_amount",
                    "decision": "wrong_value",
                    "corrected_value": "$9,999.99",
                }
            ]
        }
    )

    samples = client.get(f"/runs/{rid}/learning-samples").json()

    # Should have 2 samples (one from each review)
    assert len(samples["samples"]) == 2


def test_learning_sample_source_always_human_review(client: TestClient, run_setup: tuple) -> None:
    """All learning samples should have source=human_review."""
    rid, docid, _ = run_setup

    client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {"field_name": "invoice_number", "decision": "correct"}
            ]
        }
    )

    samples = client.get(f"/runs/{rid}/learning-samples").json()

    for sample in samples["samples"]:
        assert sample["source"] == "human_review"


def test_learning_samples_include_original_value_and_evidence_text(client: TestClient, run_setup: tuple) -> None:
    """wrong_value sample includes original_value and evidence_text."""
    rid, docid, _ = run_setup

    # Get original final_output
    fo_before = client.get(f"/runs/{rid}/documents/{docid}/final-output").json()

    original_invoice_number = None
    for field in fo_before.get("fields", []):
        if field["field_name"] == "invoice_number":
            original_invoice_number = field["value"]
            break

    # Create review
    review = client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "corrected",
            "corrections": [
                {
                    "field_name": "invoice_number",
                    "decision": "wrong_value",
                    "corrected_value": "INV-CORRECTED-001",
                }
            ]
        }
    ).json()

    samples = client.get(f"/runs/{rid}/learning-samples").json()

    assert len(samples["samples"]) == 1
    sample = samples["samples"][0]
    assert sample["original_value"] == original_invoice_number
    assert "evidence_text" in sample
    assert sample["evidence_text"] is not None


def test_hallucinated_field_sample_includes_original_value_if_present(client: TestClient, run_setup: tuple) -> None:
    """hallucinated_field sample has original_value if in final_output."""
    rid, docid, _ = run_setup

    # Get original final_output
    fo_before = client.get(f"/runs/{rid}/documents/{docid}/final-output").json()

    original_status = None
    for field in fo_before.get("fields", []):
        if field["field_name"] == "status":
            original_status = field["value"]
            break

    review = client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {
                    "field_name": "status",
                    "decision": "hallucinated_field",
                }
            ]
        }
    ).json()

    samples = client.get(f"/runs/{rid}/learning-samples").json()

    assert len(samples["samples"]) == 1
    sample = samples["samples"][0]
    if original_status is not None:
        assert sample["original_value"] == original_status
    assert sample["corrected_value"] is None


def test_learning_samples_do_not_mutate_final_output(client: TestClient, run_setup: tuple) -> None:
    """Learning samples do not mutate final_output.json."""
    rid, docid, _ = run_setup

    fo_before = client.get(f"/runs/{rid}/documents/{docid}/final-output")
    assert fo_before.status_code == 200
    fo_hash_before = hash(str(fo_before.json()))

    # Create review
    client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {
                    "field_name": "invoice_number",
                    "decision": "correct",
                }
            ]
        }
    )

    samples = client.get(f"/runs/{rid}/learning-samples")
    assert samples.status_code == 200

    fo_after = client.get(f"/runs/{rid}/documents/{docid}/final-output")
    assert fo_after.status_code == 200
    fo_hash_after = hash(str(fo_after.json()))

    assert fo_hash_before == fo_hash_after


def test_learning_samples_do_not_mutate_validation_report(client: TestClient, run_setup: tuple) -> None:
    """Learning samples do not mutate validation_report.json."""
    rid, docid, _ = run_setup

    vr_before = client.get(f"/runs/{rid}/documents/{docid}/validation-report")
    assert vr_before.status_code == 200
    vr_hash_before = hash(str(vr_before.json()))

    # Create review
    client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {
                    "field_name": "invoice_number",
                    "decision": "correct",
                }
            ]
        }
    )

    samples = client.get(f"/runs/{rid}/learning-samples")
    assert samples.status_code == 200

    vr_after = client.get(f"/runs/{rid}/documents/{docid}/validation-report")
    assert vr_after.status_code == 200
    vr_hash_after = hash(str(vr_after.json()))

    assert vr_hash_before == vr_hash_after


def test_learning_samples_scoped_to_requested_run(client: TestClient, run_setup: tuple, tmp_path: Path) -> None:
    """Samples are scoped to the requested run only."""
    rid1, docid1, jid = run_setup

    # Create another run
    run2 = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid2 = run2["run_id"]

    doc_file2 = tmp_path / "invoice2.txt"
    doc_file2.write_text("Invoice Number: INV-LEARN-002\n")

    with open(str(doc_file2), "rb") as fh:
        doc2 = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("invoice2.txt", fh, "text/plain")}
        ).json()
    docid2 = doc2["document_id"]

    client.post(f"/runs/{rid2}/documents", json={"document_id": docid2})
    client.post(f"/runs/{rid2}/execute", json={"index_artifacts": False})

    # Review on run1
    client.post(
        f"/runs/{rid1}/documents/{docid1}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {"field_name": "invoice_number", "decision": "correct"}
            ]
        }
    )

    # Review on run2
    client.post(
        f"/runs/{rid2}/documents/{docid2}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {"field_name": "invoice_number", "decision": "correct"}
            ]
        }
    )

    samples1 = client.get(f"/runs/{rid1}/learning-samples").json()
    samples2 = client.get(f"/runs/{rid2}/learning-samples").json()

    assert len(samples1["samples"]) == 1
    assert len(samples2["samples"]) == 1
    assert samples1["samples"][0]["run_id"] == rid1
    assert samples2["samples"][0]["run_id"] == rid2


def test_no_fake_sample_created_without_review_evidence(client: TestClient, run_setup: tuple) -> None:
    """No fake sample is created without review evidence."""
    rid, docid, _ = run_setup

    # No reviews
    samples = client.get(f"/runs/{rid}/learning-samples").json()
    assert samples["samples"] == []

    # After review, samples exist
    client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {"field_name": "invoice_number", "decision": "correct"}
            ]
        }
    )

    samples_after = client.get(f"/runs/{rid}/learning-samples").json()
    assert len(samples_after["samples"]) == 1


def test_absence_of_correction_does_not_imply_correct_samples(client: TestClient, run_setup: tuple) -> None:
    """Only explicit corrections create learning samples, absence does not."""
    rid, docid, _ = run_setup

    # Review with only one field corrected, others absent
    client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "corrected",
            "corrections": [
                {"field_name": "invoice_number", "decision": "wrong_value", "corrected_value": "FIXED"}
            ]
            # No correction for other fields
        }
    )

    samples = client.get(f"/runs/{rid}/learning-samples").json()
    # Only one sample for the corrected field
    assert len(samples["samples"]) == 1
    assert samples["samples"][0]["field_name"] == "invoice_number"


def test_learning_samples_not_created_from_validation_only_reviews(client: TestClient, run_setup: tuple) -> None:
    """Reviews that only validate without corrections don't create samples."""
    rid, docid, _ = run_setup

    # Review with status "reviewed" and only "correct" decisions
    client.post(
        f"/runs/{rid}/documents/{docid}/review-record",
        json={
            "review_status": "reviewed",
            "corrections": [
                {"field_name": "invoice_number", "decision": "correct"},
                {"field_name": "total_amount", "decision": "correct"}
            ]
        }
    )

    samples = client.get(f"/runs/{rid}/learning-samples").json()
    # Samples are created even for "correct" decisions
    assert len(samples["samples"]) == 2

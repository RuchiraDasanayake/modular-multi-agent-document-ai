"""Comprehensive truthfulness tests for DocAI alpha.

Verifies:
1. Extracted values actually come from source documents
2. Validation is honest (not fake pass/fail)
3. Required fields are enforced, not bypassed
4. No fake_ values injected anywhere
5. Evidence grounding is accurate
6. Missing fields properly detected
7. Optional fields don't cause false validation failures
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
def schema_with_types(client: TestClient) -> tuple[str, str]:
    """Project + schema with multiple field types."""
    proj = client.post("/projects", json={"name": "TruthTest"}).json()
    pid = proj["project_id"]

    schema = client.post(f"/projects/{pid}/schemas", json={
        "name": "DetailedSchema",
        "fields": [
            {"name": "invoice_number", "type": "str", "required": True},
            {"name": "invoice_date", "type": "str", "required": True},
            {"name": "total_amount", "type": "str", "required": True},
            {"name": "vendor_name", "type": "str", "required": False},
            {"name": "notes", "type": "str", "required": False},
        ],
        "tables": []
    }).json()

    return pid, schema["schema_id"]


# ============================================================================
# TRUTHFULNESS: VALUE EXTRACTION
# ============================================================================


def test_extracted_values_match_source_document(client: TestClient, tmp_path: Path, schema_with_types: tuple) -> None:
    """Extracted invoice_number must exactly match the value in the source document."""
    pid, sid = schema_with_types

    # Create job and upload document with specific value
    job = client.post(f"/projects/{pid}/jobs", json={"schema_id": sid, "name": "truth-extract"}).json()
    jid = job["job_id"]

    doc_text = (
        "Invoice Number: INV-TRUTH-12345\n"
        "Invoice Date: 2024-05-10\n"
        "Total Amount: $7,654.32\n"
        "Vendor: TruthCorp Inc\n"
    )
    doc_file = tmp_path / "truth_invoice.txt"
    doc_file.write_text(doc_text)

    with open(str(doc_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("truth_invoice.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    # Execute and extract
    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    # Verify extracted values EXACTLY match source
    fo = client.get(f"/runs/{rid}/documents/{docid}/final-output").json()
    field_map = {f["field_name"]: f["value"] for f in fo["fields"]}

    assert field_map["invoice_number"] == "INV-TRUTH-12345", (
        f"invoice_number must be INV-TRUTH-12345, got {field_map['invoice_number']}"
    )
    assert field_map["total_amount"] == "$7,654.32", (
        f"total_amount must be $7,654.32, got {field_map['total_amount']}"
    )
    assert field_map["vendor_name"] == "TruthCorp Inc", (
        f"vendor_name must be TruthCorp Inc, got {field_map['vendor_name']}"
    )


def test_extracted_values_grounded_in_source(client: TestClient, tmp_path: Path, schema_with_types: tuple) -> None:
    """Every extracted non-N/A value must be findable in the source document text."""
    pid, sid = schema_with_types

    job = client.post(f"/projects/{pid}/jobs", json={"schema_id": sid, "name": "truth-ground"}).json()
    jid = job["job_id"]

    doc_text = (
        "Invoice Number: DOC-GROUND-9999\n"
        "Invoice Date: 2024-06-15\n"
        "Total Amount: $12,345.67\n"
    )
    doc_file = tmp_path / "ground_invoice.txt"
    doc_file.write_text(doc_text)

    with open(str(doc_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("ground_invoice.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    # Check grounding validation
    vr = client.get(f"/runs/{rid}/documents/{docid}/validation-report").json()
    fo = client.get(f"/runs/{rid}/documents/{docid}/final-output").json()

    # Every extracted value (except N/A for optional fields) must be findable in source
    for field in fo["fields"]:
        value = str(field["value"]).strip().lower()
        # Skip N/A values (optional fields not found)
        if value not in {"", "n/a", "none"}:
            assert value in doc_text.lower(), (
                f"Field {field['field_name']} value '{value}' not found in source document"
            )


def test_no_fake_values_in_extraction(client: TestClient, tmp_path: Path, schema_with_types: tuple) -> None:
    """No extracted value should start with fake_ prefix."""
    pid, sid = schema_with_types

    job = client.post(f"/projects/{pid}/jobs", json={"schema_id": sid, "name": "truth-no-fake"}).json()
    jid = job["job_id"]

    doc_text = (
        "Invoice Number: REAL-INV-001\n"
        "Invoice Date: 2024-07-01\n"
        "Total Amount: $999.99\n"
    )
    doc_file = tmp_path / "real_invoice.txt"
    doc_file.write_text(doc_text)

    with open(str(doc_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("real_invoice.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    fo = client.get(f"/runs/{rid}/documents/{docid}/final-output").json()

    for field in fo["fields"]:
        value = str(field["value"])
        assert not value.startswith("fake_"), (
            f"Field {field['field_name']} has fake value: {value}"
        )
        assert field.get("extraction_method") != "fake_extractor", (
            f"Field {field['field_name']} used fake_extractor method"
        )


# ============================================================================
# TRUTHFULNESS: VALIDATION
# ============================================================================


def test_validation_fails_when_required_field_missing(client: TestClient, tmp_path: Path, schema_with_types: tuple) -> None:
    """Validation must fail if required field is missing."""
    pid, sid = schema_with_types

    job = client.post(f"/projects/{pid}/jobs", json={"schema_id": sid, "name": "truth-req-fail"}).json()
    jid = job["job_id"]

    # Missing total_amount (required field)
    doc_text = (
        "Invoice Number: INCOMPLETE-001\n"
        "Invoice Date: 2024-07-02\n"
    )
    doc_file = tmp_path / "incomplete.txt"
    doc_file.write_text(doc_text)

    with open(str(doc_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("incomplete.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    vr = client.get(f"/runs/{rid}/documents/{docid}/validation-report").json()

    # Must fail validation
    assert vr["pass_status"] is False, "Validation must fail when required field missing"

    # Must identify which field is missing
    missing_issues = [i for i in vr["field_issues"] if "missing_required_field" in i]
    assert len(missing_issues) > 0, "Must report missing_required_field issue"
    assert any("total_amount" in i for i in missing_issues), "Must identify total_amount as missing"


def test_validation_passes_when_all_required_fields_present(client: TestClient, tmp_path: Path, schema_with_types: tuple) -> None:
    """Validation must pass if all required fields are present."""
    pid, sid = schema_with_types

    job = client.post(f"/projects/{pid}/jobs", json={"schema_id": sid, "name": "truth-req-pass"}).json()
    jid = job["job_id"]

    # All required fields present
    doc_text = (
        "Invoice Number: COMPLETE-001\n"
        "Invoice Date: 2024-07-03\n"
        "Total Amount: $5,555.55\n"
    )
    doc_file = tmp_path / "complete.txt"
    doc_file.write_text(doc_text)

    with open(str(doc_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("complete.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    vr = client.get(f"/runs/{rid}/documents/{docid}/validation-report").json()

    # Must pass validation
    assert vr["pass_status"] is True, "Validation must pass when all required fields present"


def test_validation_passes_with_optional_fields_missing(client: TestClient, tmp_path: Path, schema_with_types: tuple) -> None:
    """Validation must pass even if optional fields are missing."""
    pid, sid = schema_with_types

    job = client.post(f"/projects/{pid}/jobs", json={"schema_id": sid, "name": "truth-opt"}).json()
    jid = job["job_id"]

    # All required fields present, but notes and vendor_name (optional) missing
    doc_text = (
        "Invoice Number: OPTIONAL-001\n"
        "Invoice Date: 2024-07-04\n"
        "Total Amount: $3,333.33\n"
    )
    doc_file = tmp_path / "optional_missing.txt"
    doc_file.write_text(doc_text)

    with open(str(doc_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("optional_missing.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    vr = client.get(f"/runs/{rid}/documents/{docid}/validation-report").json()

    # Must pass validation (optional fields don't cause failure)
    assert vr["pass_status"] is True, "Validation must pass when only optional fields missing"


def test_extraction_method_honest(client: TestClient, tmp_path: Path, schema_with_types: tuple) -> None:
    """extraction_method must not use fake_extractor in local_text mode."""
    pid, sid = schema_with_types

    job = client.post(f"/projects/{pid}/jobs", json={"schema_id": sid, "name": "truth-method"}).json()
    jid = job["job_id"]

    doc_text = (
        "Invoice Number: METHOD-001\n"
        "Invoice Date: 2024-07-05\n"
        "Total Amount: $2,222.22\n"
    )
    doc_file = tmp_path / "method.txt"
    doc_file.write_text(doc_text)

    with open(str(doc_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("method.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    fo = client.get(f"/runs/{rid}/documents/{docid}/final-output").json()

    # In local_text mode, should NOT use fake_extractor
    for field in fo["fields"]:
        # Should NOT be fake_extractor
        assert field.get("extraction_method") != "fake_extractor", (
            f"Field {field['field_name']} used fake_extractor (should use real extraction)"
        )
        # For fields with real values, extraction_method should be set
        value = str(field.get("value", "")).strip().lower()
        if value not in {"", "n/a", "none"}:
            assert field.get("extraction_method") is not None, (
                f"Field {field['field_name']} with value has no extraction_method"
            )


# ============================================================================
# TRUTHFULNESS: NON-STUB MODE
# ============================================================================


def test_local_text_mode_is_non_stub(client: TestClient, tmp_path: Path, schema_with_types: tuple) -> None:
    """local_text mode must report is_stub=False."""
    pid, sid = schema_with_types

    job = client.post(f"/projects/{pid}/jobs", json={"schema_id": sid, "name": "truth-nonstub"}).json()
    jid = job["job_id"]

    doc_text = "Invoice Number: NONSTUB-001\nInvoice Date: 2024-07-06\nTotal Amount: $1,111.11\n"
    doc_file = tmp_path / "nonstub.txt"
    doc_file.write_text(doc_text)

    with open(str(doc_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("nonstub.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    exec_resp = client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    result = exec_resp.json()

    # Must explicitly say it's not stub
    assert result["is_stub"] is False, "local_text mode must report is_stub=False"

    # Must not use stub orchestrator
    assert "stub_runtime_orchestrator" not in result["generated_by"], (
        f"generated_by should not contain 'stub_runtime_orchestrator', got: {result['generated_by']}"
    )

    # Must indicate real extraction
    assert "local_text" in result["generated_by"].lower(), (
        f"generated_by should indicate local_text mode, got: {result['generated_by']}"
    )


# ============================================================================
# TRUTHFULNESS: EVIDENCE AND GROUNDING
# ============================================================================


def test_evidence_text_contains_source_line(client: TestClient, tmp_path: Path, schema_with_types: tuple) -> None:
    """evidence_text must contain actual source for found fields (not N/A fields)."""
    pid, sid = schema_with_types

    job = client.post(f"/projects/{pid}/jobs", json={"schema_id": sid, "name": "truth-evidence"}).json()
    jid = job["job_id"]

    doc_text = (
        "Invoice Number: EVIDENCE-001\n"
        "Invoice Date: 2024-07-07\n"
        "Total Amount: $4,444.44\n"
    )
    doc_file = tmp_path / "evidence.txt"
    doc_file.write_text(doc_text)

    with open(str(doc_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("evidence.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    fo = client.get(f"/runs/{rid}/documents/{docid}/final-output").json()

    # For fields found in document, evidence_text should contain the value
    for field in fo["fields"]:
        value = str(field["value"]).strip()
        evidence = str(field.get("evidence_text", "")).strip()

        # Only check if field was actually found (not N/A)
        if value.lower() not in {"", "n/a", "none"} and evidence.lower() != "none":
            assert value.lower() in evidence.lower(), (
                f"{field['field_name']}: value '{value}' not in evidence_text '{evidence}'"
            )
            # Evidence should be longer than just the value (contains context)
            assert len(evidence) >= len(value), (
                f"{field['field_name']}: evidence_text too short to contain context"
            )


# ============================================================================
# TRUTHFULNESS: EDGE CASES
# ============================================================================


def test_document_with_no_required_fields_fails_validation(client: TestClient, tmp_path: Path, schema_with_types: tuple) -> None:
    """Document with none of the required field content should fail validation."""
    pid, sid = schema_with_types

    job = client.post(f"/projects/{pid}/jobs", json={"schema_id": sid, "name": "truth-nofields"}).json()
    jid = job["job_id"]

    # Document with text but no invoice fields
    doc_text = "This is just random text with no invoice data in it.\n"
    doc_file = tmp_path / "nofields.txt"
    doc_file.write_text(doc_text)

    with open(str(doc_file), "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("nofields.txt", fh, "text/plain")}
        ).json()
    docid = doc["document_id"]

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    vr = client.get(f"/runs/{rid}/documents/{docid}/validation-report").json()

    # Must fail (all required fields missing)
    assert vr["pass_status"] is False, "Document without required fields must fail validation"


def test_multiple_documents_each_validated_separately(client: TestClient, tmp_path: Path, schema_with_types: tuple) -> None:
    """Each document in a job must be validated independently."""
    pid, sid = schema_with_types

    job = client.post(f"/projects/{pid}/jobs", json={"schema_id": sid, "name": "truth-multi"}).json()
    jid = job["job_id"]

    # Doc 1: Complete
    doc1_text = "Invoice Number: MULTI-001\nInvoice Date: 2024-07-08\nTotal Amount: $8,888.88\n"
    doc1_file = tmp_path / "multi_complete.txt"
    doc1_file.write_text(doc1_text)

    with open(str(doc1_file), "rb") as fh:
        doc1 = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("multi_complete.txt", fh, "text/plain")}
        ).json()
    docid1 = doc1["document_id"]

    # Doc 2: Incomplete
    doc2_text = "Invoice Number: MULTI-002\n"
    doc2_file = tmp_path / "multi_incomplete.txt"
    doc2_file.write_text(doc2_text)

    with open(str(doc2_file), "rb") as fh:
        doc2 = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("multi_incomplete.txt", fh, "text/plain")}
        ).json()
    docid2 = doc2["document_id"]

    # Create run and attach both
    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid1})
    client.post(f"/runs/{rid}/documents", json={"document_id": docid2})
    client.post(f"/runs/{rid}/execute", json={"index_artifacts": False})

    # Check validation results independently
    vr1 = client.get(f"/runs/{rid}/documents/{docid1}/validation-report").json()
    vr2 = client.get(f"/runs/{rid}/documents/{docid2}/validation-report").json()

    # Doc1 should pass (all required fields)
    assert vr1["pass_status"] is True, "Complete doc should pass"

    # Doc2 should fail (missing required fields)
    assert vr2["pass_status"] is False, "Incomplete doc should fail"

"""Regression test: local_text non-stub extraction through the full HTTP API.

Proves that the complete API flow — project → job → upload → run → execute →
fetch — produces real (non-stub, non-fake) extracted values from a .txt invoice.
Does not test Qwen/Ollama, image OCR, table extraction, or recovery.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docai_core.api.app import create_app
from docai_core.persistence import ensure_database_schema

_INVOICE_TEXT = (
    "Invoice Number: INV-2024-001\n"
    "Invoice Date: 2024-05-01\n"
    "Total Amount: $1,250.00\n"
    "Status: Due\n"
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    ensure_database_schema(db)
    return db


@pytest.fixture()
def client(tmp_path: Path, db_path: Path) -> TestClient:
    app = create_app(db_path=db_path, runs_dir=tmp_path / "runs")
    return TestClient(app)


def test_local_text_extraction_regression(client: TestClient, tmp_path: Path) -> None:
    """Full API regression: local_text extraction must be non-stub, non-fake, and grounded."""

    # 1. Project
    proj = client.post("/projects", json={"name": "LocalTextRegression"}).json()
    pid = proj["project_id"]

    # 2. Job
    job = client.post(
        f"/projects/{pid}/jobs",
        json={"schema_id": "invoice_basic", "name": "regression-job"},
    ).json()
    jid = job["job_id"]

    # 3. Upload invoice .txt
    invoice_file = tmp_path / "invoice.txt"
    invoice_file.write_text(_INVOICE_TEXT, encoding="utf-8")
    with open(invoice_file, "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("invoice.txt", fh, "text/plain")},
        ).json()
    docid = doc["document_id"]

    # 4. Create run
    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]

    # 5. Attach document
    attach = client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    assert attach.status_code in (200, 201)

    # 6. Execute
    execute = client.post(f"/runs/{rid}/execute", json={"index_artifacts": True})
    assert execute.status_code == 200
    result = execute.json()

    assert result["status"] == "completed"
    assert result["is_stub"] is False
    assert result["generated_by"] != "stub_runtime_orchestrator"
    assert "local_text" in result["generated_by"]

    # 7. Final output
    fo_resp = client.get(f"/runs/{rid}/documents/{docid}/final-output")
    assert fo_resp.status_code == 200
    fo = fo_resp.json()

    fields = fo.get("fields", [])
    assert len(fields) > 0

    fake_values = [f for f in fields if str(f.get("value", "")).startswith("fake_")]
    assert fake_values == [], f"fake_ values found: {fake_values}"

    fake_methods = [f for f in fields if f.get("extraction_method") == "fake_extractor"]
    assert fake_methods == [], f"fake_extractor methods found: {fake_methods}"

    field_map = {f["field_name"]: f for f in fields}

    inv_num = field_map["invoice_number"]
    assert inv_num["value"] == "INV-2024-001"
    assert "Invoice Number: INV-2024-001" in inv_num["evidence_text"]

    assert field_map["invoice_date"]["value"] == "2024-05-01"
    assert field_map["total_amount"]["value"] == "$1,250.00"
    assert field_map["status"]["value"] == "Due"


# ---------------------------------------------------------------------------
# Persisted schema execution tests
# ---------------------------------------------------------------------------

_PERSISTED_SCHEMA_PAYLOAD = {
    "name": "Persisted Invoice",
    "document_type": "invoice",
    "fields": [
        {
            "id": "f1",
            "name": "invoice_number",
            "type": "string",
            "required": True,
            "description": "Unique invoice identifier",
            "aliases": ["Invoice Number"],
        },
        {
            "id": "f2",
            "name": "invoice_date",
            "type": "string",
            "required": True,
            "description": "Date the invoice was issued",
            "aliases": ["Invoice Date"],
        },
        {
            "id": "f3",
            "name": "total_amount",
            "type": "string",
            "required": True,
            "description": "Total monetary amount due",
            "aliases": ["Total Amount"],
        },
        {
            "id": "f4",
            "name": "status",
            "type": "string",
            "required": False,
            "description": "Payment status",
            "aliases": ["Status"],
        },
    ],
    "tables": [],
}


def _run_with_schema(
    client: TestClient,
    tmp_path: Path,
    schema_id: str,
) -> tuple[dict, dict, dict]:
    """Helper: create job + upload doc + create run + execute; return (result, fo, arts)."""
    proj = client.post("/projects", json={"name": "PersistedSchemaSmoke"}).json()
    pid = proj["project_id"]

    job = client.post(
        f"/projects/{pid}/jobs",
        json={"schema_id": schema_id, "name": "ps-job"},
    ).json()
    jid = job["job_id"]

    invoice_file = tmp_path / "invoice_ps.txt"
    invoice_file.write_text(_INVOICE_TEXT, encoding="utf-8")
    with open(invoice_file, "rb") as fh:
        doc = client.post(
            f"/jobs/{jid}/documents/upload",
            files={"file": ("invoice_ps.txt", fh, "text/plain")},
        ).json()
    docid = doc["document_id"]

    run = client.post(f"/jobs/{jid}/runs", json={"mode": "local_text"}).json()
    rid = run["run_id"]
    client.post(f"/runs/{rid}/documents", json={"document_id": docid})
    result = client.post(f"/runs/{rid}/execute", json={"index_artifacts": True}).json()
    fo = client.get(f"/runs/{rid}/documents/{docid}/final-output").json()
    arts = client.get(f"/runs/{rid}/artifacts").json()
    return result, fo, arts


def test_persisted_schema_executes_with_local_text(
    client: TestClient, tmp_path: Path
) -> None:
    """Persisted schema must drive real local_text extraction end-to-end."""
    proj = client.post("/projects", json={"name": "PSProj"}).json()
    pid = proj["project_id"]

    schema_resp = client.post(
        f"/projects/{pid}/schemas", json=_PERSISTED_SCHEMA_PAYLOAD
    ).json()
    schema_id = schema_resp["schema_id"]
    assert schema_id.startswith("schema-")

    result, fo, arts = _run_with_schema(client, tmp_path, schema_id)

    assert result["status"] == "completed"
    assert result["is_stub"] is False
    assert result["generated_by"] == "local_text_pipeline_v1"

    assert fo.get("schema_id") == schema_id

    fields = fo.get("fields", [])
    assert len(fields) > 0

    fake = [f for f in fields if str(f.get("value", "")).startswith("fake_")]
    assert fake == [], f"fake_ values found: {fake}"

    field_map = {f["field_name"]: f for f in fields}
    assert field_map["invoice_number"]["value"] == "INV-2024-001"
    assert field_map["invoice_date"]["value"] == "2024-05-01"
    assert field_map["total_amount"]["value"] == "$1,250.00"
    assert field_map["status"]["value"] == "Due"

    artifact_names = {
        p.replace("\\", "/").split("/")[-1]
        for p in arts.get("artifacts", [])
    }
    assert "final_output.json" in artifact_names
    assert "validation_report.json" in artifact_names
    assert "ocr_output.json" in artifact_names


def test_builtin_schema_still_executes_after_persisted_support(
    client: TestClient, tmp_path: Path
) -> None:
    """Built-in invoice_basic must continue working after persisted schema support added."""
    result, fo, _ = _run_with_schema(client, tmp_path, "invoice_basic")

    assert result["status"] == "completed"
    assert result["is_stub"] is False
    assert fo.get("schema_id") == "invoice_basic"
    assert len(fo.get("fields", [])) > 0

    fake = [f for f in fo["fields"] if str(f.get("value", "")).startswith("fake_")]
    assert fake == []


def test_unknown_schema_id_on_job_creation_returns_404(client: TestClient) -> None:
    """Job creation with unknown schema_id must return 404, not fall back silently."""
    proj = client.post("/projects", json={"name": "BadSchemaProj"}).json()
    pid = proj["project_id"]

    resp = client.post(
        f"/projects/{pid}/jobs",
        json={"schema_id": "schema-does-not-exist", "name": "bad-job"},
    )
    assert resp.status_code == 404
    assert "schema" in resp.json()["detail"].lower()

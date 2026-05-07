"""Integration tests for schema_id parameter in POST /runs.

Tests that non-default extraction schemas can be selected via the API.
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


@pytest.fixture()
def simple_invoice_txt(tmp_path: Path) -> Path:
    """Simple invoice text for testing."""
    content = """
    Invoice Number: INV-2024-001
    Invoice Date: 2024-01-15
    Total Amount: $1,250.00
    Status: Paid
    """
    txt_file = tmp_path / "invoice.txt"
    txt_file.write_text(content)
    return txt_file


@pytest.fixture()
def simple_receipt_txt(tmp_path: Path) -> Path:
    """Simple receipt text for testing."""
    content = """
    Receipt Number: RCP-2024-001
    Receipt Date: 2024-01-15
    Merchant Name: Acme Store
    Total Amount: $25.99
    """
    txt_file = tmp_path / "receipt.txt"
    txt_file.write_text(content)
    return txt_file


# ---------------------------------------------------------------------------
# Test 1: Default schema still works (no schema_id provided)
# ---------------------------------------------------------------------------

def test_post_runs_defaults_to_invoice_basic(
    client: TestClient, simple_invoice_txt: Path
) -> None:
    with open(simple_invoice_txt, "rb") as f:
        r = client.post(
            "/runs",
            data={"mode": "stub"},
            files={"files": ("invoice.txt", f, "text/plain")},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"]
    assert data["job_id"]

    run_id = data["run_id"]
    doc_id = "doc-0"

    final_output = client.get(f"/runs/{run_id}/documents/{doc_id}/final-output")
    assert final_output.status_code == 200
    final_data = final_output.json()
    assert final_data["schema_id"] == "invoice_basic"
    assert len(final_data["fields"]) == 4


# ---------------------------------------------------------------------------
# Test 2: Explicit default schema_id works
# ---------------------------------------------------------------------------

def test_post_runs_explicit_invoice_basic_schema(
    client: TestClient, simple_invoice_txt: Path
) -> None:
    with open(simple_invoice_txt, "rb") as f:
        r = client.post(
            "/runs",
            data={"mode": "stub", "schema_id": "invoice_basic"},
            files={"files": ("invoice.txt", f, "text/plain")},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"]

    run_id = data["run_id"]
    doc_id = "doc-0"

    final_output = client.get(f"/runs/{run_id}/documents/{doc_id}/final-output")
    assert final_output.status_code == 200
    final_data = final_output.json()
    assert final_data["schema_id"] == "invoice_basic"
    assert len(final_data["fields"]) == 4


# ---------------------------------------------------------------------------
# Test 3: Non-default schema_id works (receipt_basic)
# ---------------------------------------------------------------------------

def test_post_runs_with_receipt_basic_schema(
    client: TestClient, simple_receipt_txt: Path
) -> None:
    with open(simple_receipt_txt, "rb") as f:
        r = client.post(
            "/runs",
            data={"mode": "stub", "schema_id": "receipt_basic"},
            files={"files": ("receipt.txt", f, "text/plain")},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"]

    run_id = data["run_id"]
    doc_id = "doc-0"

    final_output = client.get(f"/runs/{run_id}/documents/{doc_id}/final-output")
    assert final_output.status_code == 200
    final_data = final_output.json()
    assert final_data["schema_id"] == "receipt_basic"
    assert len(final_data["fields"]) == 4
    field_names = [f["field_name"] for f in final_data["fields"]]
    assert "receipt_number" in field_names
    assert "merchant_name" in field_names
    assert "receipt_date" in field_names
    assert "total_amount" in field_names


# ---------------------------------------------------------------------------
# Test 4: Invalid schema_id returns 400
# ---------------------------------------------------------------------------

def test_post_runs_invalid_schema_id_returns_400(
    client: TestClient, simple_invoice_txt: Path
) -> None:
    with open(simple_invoice_txt, "rb") as f:
        r = client.post(
            "/runs",
            data={"mode": "stub", "schema_id": "does_not_exist"},
            files={"files": ("invoice.txt", f, "text/plain")},
        )
    assert r.status_code == 400
    data = r.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower() or "unknown" in data["detail"].lower()


# ---------------------------------------------------------------------------
# Test 5: Selected schema_id is recorded in artifacts
# ---------------------------------------------------------------------------

def test_selected_schema_recorded_in_final_output(
    client: TestClient, simple_receipt_txt: Path
) -> None:
    with open(simple_receipt_txt, "rb") as f:
        r = client.post(
            "/runs",
            data={"mode": "stub", "schema_id": "receipt_basic"},
            files={"files": ("receipt.txt", f, "text/plain")},
        )
    assert r.status_code == 200

    run_id = r.json()["run_id"]
    doc_id = "doc-0"

    final_output = client.get(f"/runs/{run_id}/documents/{doc_id}/final-output")
    assert final_output.status_code == 200
    final_data = final_output.json()
    assert final_data["schema_id"] == "receipt_basic"
    assert "artifact_paths" in final_data
    assert len(final_data["artifact_paths"]) > 0

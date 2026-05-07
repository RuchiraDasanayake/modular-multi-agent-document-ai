"""Integration tests for DocAI v2 local API.

Uses FastAPI TestClient — no real Qwen endpoint, no Tesseract required.
All three pipeline modes are exercised with uploaded TXT files.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docai_core.api.app import create_app

_INVOICE_TEXT = (
    "Invoice Number: INV-001\n"
    "Invoice Date: 2026-03-15\n"
    "Total Amount: $100.00\n"
    "Status: Paid\n"
)


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    app = create_app(runs_dir=tmp_path / "runs")
    return TestClient(app)


def _invoice_file() -> tuple[str, tuple[str, io.BytesIO, str]]:
    return ("files", ("invoice.txt", io.BytesIO(_INVOICE_TEXT.encode()), "text/plain"))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "docai-v2-api"


# ---------------------------------------------------------------------------
# POST /runs — pipeline modes
# ---------------------------------------------------------------------------

def test_post_run_stub_mode(client: TestClient) -> None:
    r = client.post("/runs", data={"mode": "stub"}, files=[_invoice_file()])
    assert r.status_code == 200
    data = r.json()
    assert data["is_stub"] is True
    assert data["generated_by"] == "stub_runtime_orchestrator"
    assert data["document_count"] == 1
    assert data["completed_count"] == 1
    assert "run_id" in data
    assert "artifact_root" in data


def test_post_run_local_text_mode_with_txt_file(client: TestClient) -> None:
    r = client.post("/runs", data={"mode": "local_text"}, files=[_invoice_file()])
    assert r.status_code == 200
    data = r.json()
    assert data["is_stub"] is False
    assert data["generated_by"] == "local_text_pipeline_v1"
    assert data["document_count"] == 1
    assert data["completed_count"] == 1
    assert "artifact_root" in data


def test_post_run_model_mode_uses_fake_model_without_network(client: TestClient) -> None:
    r = client.post("/runs", data={"mode": "local_text_model"}, files=[_invoice_file()])
    assert r.status_code == 200
    data = r.json()
    assert data["is_stub"] is False
    assert data["generated_by"] == "model_centered_pipeline_v1"
    assert data["document_count"] == 1
    assert data["completed_count"] == 1


def test_post_run_rejects_unknown_mode(client: TestClient) -> None:
    r = client.post("/runs", data={"mode": "bad_mode"}, files=[_invoice_file()])
    assert r.status_code == 400
    assert "bad_mode" in r.json()["detail"]


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/artifacts
# ---------------------------------------------------------------------------

def test_get_run_artifacts_returns_file_list(client: TestClient) -> None:
    r = client.post("/runs", data={"mode": "stub"}, files=[_invoice_file()])
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    r2 = client.get(f"/runs/{run_id}/artifacts")
    assert r2.status_code == 200
    data = r2.json()
    assert data["run_id"] == run_id
    assert data["artifact_count"] > 0
    assert len(data["artifacts"]) == data["artifact_count"]
    assert any("final_output.json" in a for a in data["artifacts"])


def test_get_run_artifacts_returns_404_for_unknown_run(client: TestClient) -> None:
    r = client.get("/runs/nonexistent-run-id/artifacts")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/documents/{doc_id}/final-output
# ---------------------------------------------------------------------------

def test_get_final_output_for_document(client: TestClient) -> None:
    r = client.post("/runs", data={"mode": "local_text"}, files=[_invoice_file()])
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    r2 = client.get(f"/runs/{run_id}/documents/doc-0/final-output")
    assert r2.status_code == 200
    payload = r2.json()
    assert "fields" in payload
    assert payload["is_stub"] is False


def test_get_final_output_returns_404_for_missing_doc(client: TestClient) -> None:
    r = client.post("/runs", data={"mode": "stub"}, files=[_invoice_file()])
    run_id = r.json()["run_id"]

    r2 = client.get(f"/runs/{run_id}/documents/ghost-doc/final-output")
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/documents/{doc_id}/validation-report
# ---------------------------------------------------------------------------

def test_get_validation_report_for_document(client: TestClient) -> None:
    r = client.post("/runs", data={"mode": "local_text"}, files=[_invoice_file()])
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    r2 = client.get(f"/runs/{run_id}/documents/doc-0/validation-report")
    assert r2.status_code == 200
    payload = r2.json()
    assert "pass_status" in payload
    assert "summary" in payload


def test_get_validation_report_returns_404_for_missing_doc(client: TestClient) -> None:
    r = client.post("/runs", data={"mode": "stub"}, files=[_invoice_file()])
    run_id = r.json()["run_id"]

    r2 = client.get(f"/runs/{run_id}/documents/ghost-doc/validation-report")
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Model provider env config
# ---------------------------------------------------------------------------

def test_model_mode_default_provider_uses_stub(client: TestClient) -> None:
    r = client.post("/runs", data={"mode": "local_text_model"}, files=[_invoice_file()])
    assert r.status_code == 200
    data = r.json()
    assert data["generated_by"] == "model_centered_pipeline_v1"
    assert data["is_stub"] is False


def test_model_mode_ollama_provider_uses_qwen_plugin_without_network(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from docai_core.plugins.models.base import ModelResponse
    from docai_core.plugins.models.qwen_model_plugin import QwenModelPlugin

    monkeypatch.setenv("DOCAI_MODEL_PROVIDER", "ollama")
    monkeypatch.setattr(
        QwenModelPlugin,
        "generate",
        lambda self, request: ModelResponse(
            text="invoice_number: INV-001\ntotal_amount: $100.00",
            is_stub=False,
            success=True,
        ),
    )

    r = client.post("/runs", data={"mode": "local_text_model"}, files=[_invoice_file()])
    assert r.status_code == 200
    data = r.json()
    assert data["generated_by"] == "model_centered_pipeline_v1"
    assert data["completed_count"] == 1


def test_model_mode_unknown_provider_returns_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCAI_MODEL_PROVIDER", "bad_provider")
    r = client.post("/runs", data={"mode": "local_text_model"}, files=[_invoice_file()])
    assert r.status_code == 400
    assert "bad_provider" in r.json()["detail"]


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

def test_cors_preflight_allows_local_frontend_origin(tmp_path: Path) -> None:
    from docai_core.api.app import create_app
    app = create_app(runs_dir=tmp_path / "runs")
    c = TestClient(app, raise_server_exceptions=True)
    r = c.options(
        "/runs",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers.get("access-control-allow-origin") in (
        "http://localhost:5173", "*"
    )


def test_cors_uses_env_configured_origins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCAI_CORS_ALLOW_ORIGINS", "http://my-custom-origin.example")
    from docai_core.api import app as app_module
    import importlib
    importlib.reload(app_module)
    custom_app = app_module.create_app(runs_dir=tmp_path / "runs")
    c = TestClient(custom_app, raise_server_exceptions=True)
    r = c.options(
        "/runs",
        headers={
            "Origin": "http://my-custom-origin.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "http://my-custom-origin.example"


# ---------------------------------------------------------------------------
# policy_id parameter
# ---------------------------------------------------------------------------

def test_post_run_with_policy_id_invoice_basic_uses_local_text_pipeline(
    client: TestClient, tmp_path: Path
) -> None:
    r = client.post("/runs", data={"policy_id": "invoice_basic_local_v1"}, files=[_invoice_file()])
    assert r.status_code == 200
    data = r.json()
    assert data["generated_by"] == "local_text_pipeline_v1"
    assert data["is_stub"] is False
    assert "invoice_basic_local_v1" in data["policies_used"]

    run_id = data["run_id"]
    r2 = client.get(f"/runs/{run_id}/documents/doc-0/final-output")
    assert r2.status_code == 200
    payload = r2.json()
    assert payload["policy_id"] == "invoice_basic_local_v1"
    assert all(
        not str(f.get("value", "")).startswith("fake_")
        for f in payload.get("fields", [])
    )


def test_post_run_with_policy_id_noisy_scan_uses_model_pipeline(client: TestClient) -> None:
    r = client.post("/runs", data={"policy_id": "noisy_scan_rescue_v1"}, files=[_invoice_file()])
    assert r.status_code == 200
    data = r.json()
    assert data["generated_by"] == "model_centered_pipeline_v1"
    assert data["is_stub"] is False
    assert "noisy_scan_rescue_v1" in data["policies_used"]

    run_id = data["run_id"]
    r2 = client.get(f"/runs/{run_id}/documents/doc-0/final-output")
    assert r2.status_code == 200
    assert r2.json()["policy_id"] == "noisy_scan_rescue_v1"


def test_post_run_unknown_policy_id_returns_400(client: TestClient) -> None:
    r = client.post("/runs", data={"policy_id": "does_not_exist"}, files=[_invoice_file()])
    assert r.status_code == 400
    assert "does_not_exist" in r.json()["detail"]


def test_policy_id_takes_precedence_over_mode(client: TestClient) -> None:
    r = client.post(
        "/runs",
        data={"mode": "local_text", "policy_id": "noisy_scan_rescue_v1"},
        files=[_invoice_file()],
    )
    assert r.status_code == 200
    assert r.json()["generated_by"] == "model_centered_pipeline_v1"


def test_post_run_neither_mode_nor_policy_id_returns_400(client: TestClient) -> None:
    r = client.post("/runs", data={}, files=[_invoice_file()])
    assert r.status_code == 400

"""
IDPO test suite — health endpoint, HITL correction, safe filename,
path traversal protection, integration data classes.

Uses FastAPI TestClient. External service calls (AHMN, XAI) are mocked.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from idpo.ui.app import app, _safe_filename, _safe_run_dir

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

# ═══════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["service"] == "idpo"

# ═══════════════════════════════════════════════════════════════
# Safe Filename Sanitisation
# ═══════════════════════════════════════════════════════════════

def test_safe_filename_strips_path():
    assert _safe_filename("/etc/passwd") == "passwd"
    assert _safe_filename("../../../etc/shadow") == "shadow"

def test_safe_filename_removes_dotdot():
    assert ".." not in _safe_filename("..foo..bar.txt")

def test_safe_filename_normal():
    assert _safe_filename("document.pdf") == "document.pdf"
    assert _safe_filename("my file (1).docx") == "my file (1).docx"

# ═══════════════════════════════════════════════════════════════
# Path Traversal Protection
# ═══════════════════════════════════════════════════════════════

def test_safe_run_dir_rejects_traversal():
    with pytest.raises(ValueError, match="Invalid"):
        _safe_run_dir("../../etc")

def test_safe_run_dir_accepts_valid_id():
    # Should not raise
    path = _safe_run_dir("abc123")
    assert "abc123" in str(path)

# ═══════════════════════════════════════════════════════════════
# Index Redirect
# ═══════════════════════════════════════════════════════════════

def test_index_redirects(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "localhost:3000" in resp.text

# ═══════════════════════════════════════════════════════════════
# HITL Correction Endpoint
# ═══════════════════════════════════════════════════════════════

def test_hitl_correction_valid(client):
    """Valid HITL correction request should forward to AHMN."""
    mock_result = {"status": "accepted", "advice_id": "abc"}
    with patch("idpo.ui.app.forward_hitl_correction", return_value=mock_result):
        resp = client.post(
            "/idpo/hitl-correction",
            json={
                "advice_id": "abc-123",
                "feedback_type": "incorrect",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

def test_hitl_correction_invalid_feedback_type(client):
    """Invalid feedback_type should be rejected by Pydantic validation."""
    resp = client.post(
        "/idpo/hitl-correction",
        json={
            "advice_id": "abc-123",
            "feedback_type": "invalid_value",
        },
    )
    assert resp.status_code == 422

def test_hitl_correction_missing_fields(client):
    resp = client.post("/idpo/hitl-correction", json={})
    assert resp.status_code == 422

def test_hitl_correction_all_feedback_types(client):
    """All valid feedback types should pass validation."""
    valid_types = ["correct", "incorrect", "partially_correct", "needs_more_context"]
    mock_result = {"status": "accepted"}
    with patch("idpo.ui.app.forward_hitl_correction", return_value=mock_result):
        for ft in valid_types:
            resp = client.post(
                "/idpo/hitl-correction",
                json={"advice_id": "test-id", "feedback_type": ft},
            )
            assert resp.status_code == 200, f"Failed for feedback_type={ft}"

# ═══════════════════════════════════════════════════════════════
# Run Endpoint (upload validation)
# ═══════════════════════════════════════════════════════════════

def test_run_no_files(client):
    """POST /idpo/run without files should return 422."""
    resp = client.post("/idpo/run")
    assert resp.status_code == 422

# ═══════════════════════════════════════════════════════════════
# Integration Data Classes
# ═══════════════════════════════════════════════════════════════

def test_integration_result_dataclass():
    from idpo.integration import IntegrationResult

    result = IntegrationResult()
    assert result.guardrails == []
    assert result.xai_explanations == []
    assert result.cycle_time_ms == 0.0
    assert hasattr(result, "ahmn_advice")

def test_ahmn_advice_dataclass():
    from idpo.integration import AHMNAdvice

    advice = AHMNAdvice(error="Test error")
    assert advice.error == "Test error"

def test_ahmn_advice_success():
    from idpo.integration import AHMNAdvice

    advice = AHMNAdvice()
    assert advice.error is None

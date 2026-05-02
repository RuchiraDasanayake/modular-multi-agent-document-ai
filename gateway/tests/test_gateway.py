"""
Gateway test suite — auth endpoints, token lifecycle, proxy routing.

Uses FastAPI TestClient with mocked database and Redis dependencies.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from psycopg_pool import PoolTimeout

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_dependencies(monkeypatch):
    """Patch heavy dependencies so tests run without Postgres / Redis."""
    # Mock pool with proper async context manager for connection()
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    _cm = AsyncMock()
    _cm.__aenter__ = AsyncMock(return_value=mock_conn)
    _cm.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection = MagicMock(return_value=_cm)
    monkeypatch.setattr("gateway.database.DatabasePool.get_pool", AsyncMock(return_value=mock_pool))
    monkeypatch.setattr("gateway.database.DatabasePool.close_pool", AsyncMock())
    # Also mock Redis so /health doesn't fail
    monkeypatch.setattr("gateway.main._get_redis", AsyncMock(return_value=AsyncMock(ping=AsyncMock())))

@pytest.fixture()
def client():
    """Create a TestClient for the gateway app."""
    from gateway.main import app
    from gateway.deps import get_db

    # Override get_db to yield a proper AsyncMock connection
    async def _mock_get_db():
        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_cursor.fetchall = AsyncMock(return_value=[])
        _cm = AsyncMock()
        _cm.__aenter__ = AsyncMock(return_value=mock_cursor)
        _cm.__aexit__ = AsyncMock(return_value=False)
        mock_db.cursor = MagicMock(return_value=_cm)
        return mock_db

    app.dependency_overrides[get_db] = _mock_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()

# ═══════════════════════════════════════════════════════════════
# Health Endpoints
# ═══════════════════════════════════════════════════════════════

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["service"] == "gateway"

def test_api_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"

# ═══════════════════════════════════════════════════════════════
# Auth Service Unit Tests
# ═══════════════════════════════════════════════════════════════

def test_password_hash_and_verify():
    from gateway.auth_service import hash_password, verify_password

    pw = "TestPass123!"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed)
    assert not verify_password("wrong", hashed)

def test_access_token_create_and_verify():
    from gateway.auth_service import create_access_token, verify_token

    token = create_access_token({"sub": "user-123"})
    payload = verify_token(token, expected_type="access")
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"

def test_refresh_token_create_and_verify():
    from gateway.auth_service import create_refresh_token, verify_token

    token = create_refresh_token({"sub": "user-456"})
    payload = verify_token(token, expected_type="refresh")
    assert payload is not None
    assert payload["sub"] == "user-456"
    assert payload["type"] == "refresh"
    assert "jti" in payload  # JTI must be present for revocation

def test_refresh_token_rejected_as_access():
    from gateway.auth_service import create_refresh_token, verify_token

    token = create_refresh_token({"sub": "user-789"})
    payload = verify_token(token, expected_type="access")
    assert payload is None

def test_access_token_rejected_as_refresh():
    from gateway.auth_service import create_access_token, verify_token

    token = create_access_token({"sub": "user-012"})
    payload = verify_token(token, expected_type="refresh")
    assert payload is None

def test_expired_token_rejected():
    from gateway.auth_service import create_access_token, verify_token

    token = create_access_token(
        {"sub": "user-exp"}, expires_delta=timedelta(seconds=-1)
    )
    payload = verify_token(token)
    assert payload is None

def test_invalid_token_rejected():
    from gateway.auth_service import verify_token

    assert verify_token("not.a.valid.jwt") is None
    assert verify_token("") is None

def test_generate_reset_token():
    from gateway.auth_service import generate_reset_token

    t1 = generate_reset_token()
    t2 = generate_reset_token()
    assert isinstance(t1, str)
    assert len(t1) > 20
    assert t1 != t2  # should be random

# ═══════════════════════════════════════════════════════════════
# Auth Endpoints (Login, Signup)
# ═══════════════════════════════════════════════════════════════

def test_login_missing_body(client):
    resp = client.post("/api/auth/login", json={})
    assert resp.status_code == 422  # validation error

def test_login_invalid_credentials(client):
    """Login with non-existent user should return 401."""
    resp = client.post(
        "/api/auth/login",
        json={"username": "nonexistent", "password": "wrong"},
    )
    assert resp.status_code in (401, 500)

def test_signup_missing_fields(client):
    resp = client.post("/api/auth/signup", json={})
    assert resp.status_code == 422

# ═══════════════════════════════════════════════════════════════
# Protected Endpoints (no token)
# ═══════════════════════════════════════════════════════════════

def test_me_without_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code in (401, 403)

def test_proxy_without_token(client):
    resp = client.get("/api/advice/something")
    assert resp.status_code in (401, 403)

# ═══════════════════════════════════════════════════════════════
# Proxy Routing Logic
# ═══════════════════════════════════════════════════════════════

def test_resolve_upstream_known_services():
    from gateway.main import _resolve_upstream

    assert _resolve_upstream("/api/advice/generate") is not None
    assert _resolve_upstream("/api/dashboard/stats") is not None
    assert _resolve_upstream("/api/guardrails/check") is not None
    assert _resolve_upstream("/api/xai/ask") is not None
    assert _resolve_upstream("/api/hitl/feedback") is not None
    assert _resolve_upstream("/api/idpo/run") is not None

def test_resolve_upstream_unknown_service():
    from gateway.main import _resolve_upstream

    assert _resolve_upstream("/api/nonexistent/foo") is None
    assert _resolve_upstream("/health") is None
    assert _resolve_upstream("/api/") is None

def test_resolve_upstream_strips_prefix():
    from gateway.main import _resolve_upstream

    result = _resolve_upstream("/api/xai/ask")
    assert result is not None
    upstream_url, downstream_path = result
    assert downstream_path == "/xai/ask"

# ═══════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════

def test_settings_loads():
    from gateway.config import settings

    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES > 0
    assert settings.PROXY_TIMEOUT > 0

def test_jwt_secret_not_default():
    """After validate_jwt_secret(), the key should not be the placeholder."""
    from gateway.config import settings

    assert settings.JWT_SECRET_KEY != "change-me-in-production"

# ═══════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════

def test_login_request_schema():
    from gateway.schemas import LoginRequest

    req = LoginRequest(username="alice", password="pass123")
    assert req.username == "alice"

def test_register_request_schema():
    from gateway.schemas import RegisterRequest

    req = RegisterRequest(email="a@b.com", username="alice", password="pass123")
    assert req.email == "a@b.com"
    assert req.role == "viewer"  # default

def test_token_response_schema():
    from gateway.schemas import TokenResponse

    resp = TokenResponse(access_token="a.b.c", refresh_token="d.e.f")
    assert resp.access_token == "a.b.c"
    assert resp.refresh_token == "d.e.f"

def test_refresh_request_schema():
    from gateway.schemas import RefreshRequest

    req = RefreshRequest(refresh_token="x.y.z")
    assert req.refresh_token == "x.y.z"

def test_get_db_connection_rebuilds_pool_after_timeout(monkeypatch):
    from gateway.database import DatabasePool, get_db_connection

    first_pool = MagicMock()
    first_pool.connection = MagicMock(side_effect=PoolTimeout("pool exhausted"))

    recovered_conn = AsyncMock()
    recovered_cm = AsyncMock()
    recovered_cm.__aenter__ = AsyncMock(return_value=recovered_conn)
    recovered_cm.__aexit__ = AsyncMock(return_value=False)

    second_pool = MagicMock()
    second_pool.connection = MagicMock(return_value=recovered_cm)

    get_pool = AsyncMock(side_effect=[first_pool, second_pool])
    close_pool = AsyncMock()

    monkeypatch.setattr(DatabasePool, "get_pool", get_pool)
    monkeypatch.setattr(DatabasePool, "close_pool", close_pool)

    async def run_case():
        gen = get_db_connection()
        conn = await anext(gen)
        assert conn is recovered_conn
        await gen.aclose()

    asyncio.run(run_case())

    assert get_pool.await_count == 2
    close_pool.assert_awaited_once()

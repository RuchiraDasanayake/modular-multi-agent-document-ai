"""
Gateway test suite — auth endpoints, token lifecycle, proxy routing.

Uses FastAPI TestClient with mocked database and Redis dependencies.
"""

import asyncio

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from psycopg_pool import PoolTimeout

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _admin_check_connection(*fetch_results):
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(side_effect=list(fetch_results))
    cursor_cm = AsyncMock()
    cursor_cm.__aenter__ = AsyncMock(return_value=cursor)
    cursor_cm.__aexit__ = AsyncMock(return_value=False)
    conn = AsyncMock()
    conn.cursor = MagicMock(return_value=cursor_cm)
    return conn, cursor

@pytest.fixture(autouse=True)
def _mock_dependencies(monkeypatch):
    """Patch heavy dependencies so tests run without Postgres / Redis."""
    # Mock pool with proper async context manager for connection(); the startup check finds an existing admin
    mock_conn, _ = _admin_check_connection((1,))
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

def test_public_signup_defaults_to_off(monkeypatch):
    from gateway.config import Settings

    monkeypatch.delenv("PUBLIC_SIGNUP_ENABLED", raising=False)
    assert Settings(_env_file=None).PUBLIC_SIGNUP_ENABLED is False

def test_signup_status_follows_setting(client, monkeypatch):
    from gateway.config import settings

    monkeypatch.setattr(settings, "PUBLIC_SIGNUP_ENABLED", False)
    assert client.get("/api/auth/signup-status").json() == {"enabled": False}
    monkeypatch.setattr(settings, "PUBLIC_SIGNUP_ENABLED", True)
    assert client.get("/api/auth/signup-status").json() == {"enabled": True}

def test_signup_is_refused_when_public_signup_is_off(client, monkeypatch):
    from gateway.config import settings

    monkeypatch.setattr(settings, "PUBLIC_SIGNUP_ENABLED", False)
    resp = client.post(
        "/api/auth/signup",
        json={"email": "new.viewer@example.org", "username": "newviewer", "password": "secret-123"},
    )
    assert resp.status_code == 403
    assert "turned off" in resp.json()["detail"]

# ═══════════════════════════════════════════════════════════════
# Protected Endpoints (no token)
# ═══════════════════════════════════════════════════════════════

def test_me_without_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code in (401, 403)

def test_proxy_without_token(client):
    resp = client.get("/api/advice/something")
    assert resp.status_code in (401, 403)


@pytest.mark.parametrize(
    "path",
    [
        "/api/idpo/runs",
        "/api/idpo/runs/other-user/docs.xlsx",
        "/api/xai/explanation/other-user-question",
        "/api/hitl/history",
        "/api/dashboard/memory/mtm",
        "/api/guardrails/history",
    ],
)
def test_viewer_cannot_proxy_unscoped_service_data(client, path):
    from gateway.deps import get_current_user
    from gateway.main import app

    app.dependency_overrides[get_current_user] = lambda: {"id": "viewer-1", "role": "viewer"}
    with patch("gateway.main._get_client", new_callable=AsyncMock) as get_client:
        resp = client.get(path)

    assert resp.status_code == 403
    get_client.assert_not_awaited()


def test_viewer_cannot_start_legacy_idpo_run(client):
    from gateway.deps import get_current_user
    from gateway.main import app

    app.dependency_overrides[get_current_user] = lambda: {"id": "viewer-1", "role": "viewer"}
    with patch("gateway.main._get_client", new_callable=AsyncMock) as get_client:
        resp = client.post("/api/idpo/run", json={"documents": []})

    assert resp.status_code == 403
    get_client.assert_not_awaited()


def test_admin_can_proxy_legacy_service(client):
    from gateway.deps import get_current_user
    from gateway.main import app

    app.dependency_overrides[get_current_user] = lambda: {"id": "admin-1", "role": "admin"}
    upstream = AsyncMock()
    upstream.request.return_value = httpx.Response(200, json={"runs": []})
    with patch("gateway.main._get_client", new_callable=AsyncMock, return_value=upstream):
        resp = client.get("/api/idpo/runs")

    assert resp.status_code == 200
    assert resp.json() == {"runs": []}
    assert upstream.request.await_args.kwargs["headers"]["x-user-id"] == "admin-1"

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


@pytest.mark.parametrize("secret", ["", "short", "change-me-in-production-use-a-32-char-random-string"])
def test_production_rejects_missing_or_example_jwt_secret(secret):
    from gateway.config import Settings

    config = Settings(_env_file=None, JWT_SECRET_KEY=secret, REQUIRE_EXPLICIT_SECRETS=True)
    with pytest.raises(ValueError, match="explicit JWT secret"):
        config.validate_jwt_secret()


def test_production_keeps_a_stable_explicit_jwt_secret():
    from gateway.config import Settings

    secret = "independent-test-secret-32-characters-long"
    config = Settings(_env_file=None, JWT_SECRET_KEY=secret, REQUIRE_EXPLICIT_SECRETS=True)
    config.validate_jwt_secret()
    assert config.JWT_SECRET_KEY == secret

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

# ═══════════════════════════════════════════════════════════════
# First admin account
# ═══════════════════════════════════════════════════════════════

def test_first_admin_is_created_from_admin_password(monkeypatch):
    from gateway.auth_service import verify_password
    from gateway.config import settings
    from gateway.main import _ensure_admin_account

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "S3cure-first-login")
    conn, cursor = _admin_check_connection(None, ("new-admin-id",))

    asyncio.run(_ensure_admin_account(conn))

    insert_sql, params = cursor.execute.await_args_list[1].args
    assert "INSERT INTO users" in insert_sql and "'admin'" in insert_sql
    assert params[:2] == (settings.ADMIN_EMAIL, settings.ADMIN_USERNAME)
    assert verify_password("S3cure-first-login", params[2])
    conn.commit.assert_awaited_once()

def test_existing_admin_is_left_untouched(monkeypatch):
    from gateway.config import settings
    from gateway.main import _ensure_admin_account

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "ignored-because-admin-exists")
    conn, cursor = _admin_check_connection((1,))

    asyncio.run(_ensure_admin_account(conn))

    assert cursor.execute.await_count == 1
    conn.commit.assert_not_awaited()

def test_no_admin_is_created_without_admin_password(monkeypatch):
    from gateway.config import settings
    from gateway.main import _ensure_admin_account

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
    conn, cursor = _admin_check_connection(None)

    asyncio.run(_ensure_admin_account(conn))

    assert cursor.execute.await_count == 1
    conn.commit.assert_not_awaited()

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

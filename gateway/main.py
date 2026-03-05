"""
API Gateway
============
Single public entry point. Handles JWT authentication directly and
proxies all other requests to the appropriate microservice.

Route map
---------
/api/auth/*                → handled locally (JWT + Postgres)
/api/advice/*              → AHMN service   (8001)
/api/dashboard/*           → AHMN service   (8001)
/api/experiments/*         → AHMN service   (8001)
/api/guardrails/*          → Guardrails     (8002)
/api/xai/*                 → XAI-HITL       (8003)
/api/hitl/*                → XAI-HITL       (8003)
/api/idpo/*                → IDPO           (8004)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import redis.asyncio as aioredis
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from psycopg import AsyncConnection
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .config import settings
from .database import DatabasePool
from .deps import get_current_user, get_db, require_admin
from .schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from .auth_service import (
    create_access_token,
    create_refresh_token,
    generate_reset_token,
    hash_password,
    verify_password,
    verify_token,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("gateway")

# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# ---------------------------------------------------------------------------
# Service routing table
# ---------------------------------------------------------------------------
SERVICE_MAP: dict[str, str] = {
    "advice": settings.AHMN_SERVICE_URL,
    "dashboard": settings.AHMN_SERVICE_URL,
    "experiments": settings.AHMN_SERVICE_URL,
    "scheduler": settings.AHMN_SERVICE_URL,
    "guardrails": settings.GUARDRAILS_SERVICE_URL,
    "xai": settings.XAI_HITL_SERVICE_URL,
    "hitl": settings.XAI_HITL_SERVICE_URL,
    "idpo": settings.IDPO_SERVICE_URL,
}

# ---------------------------------------------------------------------------
# Shared httpx client
# ---------------------------------------------------------------------------
_http_client: httpx.AsyncClient | None = None

async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=15.0,
                read=settings.PROXY_TIMEOUT,
                write=120.0,
                pool=15.0,
            ),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
        )
    return _http_client

# ---------------------------------------------------------------------------
# Redis pool (token blacklist)
# ---------------------------------------------------------------------------
_redis: aioredis.Redis | None = None
_REVOKED_PREFIX = "revoked:"
_REFRESH_TOKEN_TTL = 7 * 24 * 3600  # 7 days — matches refresh token lifetime

async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL, decode_responses=True
        )
    return _redis

async def _blacklist_token(jti: str) -> None:
    """Add a refresh token JTI to the revocation set with auto-expiry."""
    r = await _get_redis()
    await r.setex(f"{_REVOKED_PREFIX}{jti}", _REFRESH_TOKEN_TTL, "1")

async def _is_token_revoked(jti: str) -> bool:
    r = await _get_redis()
    return await r.exists(f"{_REVOKED_PREFIX}{jti}") > 0

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    await DatabasePool.get_pool()
    logger.info("Gateway started — DB pool ready")
    yield
    await DatabasePool.close_pool()
    if _http_client:
        await _http_client.aclose()
    if _redis:
        await _redis.aclose()
    logger.info("Gateway shut down cleanly")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Modular Document AI — API Gateway",
    version="1.0.0",
    description="Authentication and routing gateway for AHMN, Guardrails, and XAI-HITL services.",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

origins = [o.strip() for o in settings.BACKEND_CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "gateway"}

@app.get("/api/health")
async def api_health():
    """Backwards-compatible health endpoint."""
    return {"status": "healthy", "service": "gateway"}

@app.get("/api/services/health")
async def services_health():
    """Check health of all backend microservices at once."""
    import asyncio

    client = await _get_client()
    service_checks = {
        "gateway": {"url": None, "status": "healthy", "latency": 0},
        "ahmn": {"url": f"{settings.AHMN_SERVICE_URL}/health"},
        "guardrails": {"url": f"{settings.GUARDRAILS_SERVICE_URL}/health"},
        "xai": {"url": f"{settings.XAI_HITL_SERVICE_URL}/health"},
        "idpo": {"url": f"{settings.IDPO_SERVICE_URL}/health"},
    }

    async def check_service(name: str, url: str) -> dict:
        import time
        start = time.monotonic()
        try:
            resp = await client.get(url, timeout=5.0)
            latency = round((time.monotonic() - start) * 1000)
            if resp.status_code < 400:
                return {"name": name, "status": "healthy", "latency": latency}
            return {"name": name, "status": "degraded", "latency": latency}
        except Exception:
            return {"name": name, "status": "offline", "latency": 0}

    tasks = []
    for name, info in service_checks.items():
        if info.get("url"):
            tasks.append(check_service(name, info["url"]))

    results = await asyncio.gather(*tasks)
    services = [{"name": "gateway", "status": "healthy", "latency": 0}]
    services.extend(results)

    return {"services": services}

# ═══════════════════════════════════════════════════════════════════════════
# Auth routes (handled locally — not proxied)
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/auth/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: AsyncConnection = Depends(get_db)):
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id, hashed_password, is_active FROM users WHERE username = %s",
            (body.username,),
        )
        row = await cur.fetchone()

    if row is None or not verify_password(body.password, row[1]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    if not row[2]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled"
        )

    token = create_access_token({"sub": str(row[0])})
    refresh = create_refresh_token({"sub": str(row[0])})
    return TokenResponse(access_token=token, refresh_token=refresh)

@app.post("/api/auth/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncConnection = Depends(get_db)):
    """Exchange a valid refresh token for a new access + refresh token pair.

    The old refresh token is blacklisted to prevent reuse (rotation).
    """
    payload = verify_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Check if this refresh token has been revoked
    if jti and await _is_token_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    # Verify user still exists and is active
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id, is_active FROM users WHERE id = %s", (user_id,)
        )
        row = await cur.fetchone()

    if row is None or not row[1]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Blacklist the old refresh token (token rotation)
    if jti:
        await _blacklist_token(jti)

    new_access = create_access_token({"sub": user_id})
    new_refresh = create_refresh_token({"sub": user_id})
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)

@app.post("/api/auth/signup", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
async def signup(
    request: Request,
    body: RegisterRequest,
    db: AsyncConnection = Depends(get_db),
):
    """Public self-registration (always creates 'viewer' role)."""
    hashed = hash_password(body.password)
    try:
        async with db.cursor() as cur:
            await cur.execute(
                """INSERT INTO users (email, username, hashed_password, role)
                   VALUES (%s, %s, %s, 'viewer')
                   RETURNING id""",
                (body.email, body.username, hashed),
            )
            row = await cur.fetchone()
            await db.commit()
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="Username or email already taken")
        raise HTTPException(status_code=500, detail="Database error")

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create user")
    token = create_access_token({"sub": str(row[0])})
    refresh = create_refresh_token({"sub": str(row[0])})
    return TokenResponse(access_token=token, refresh_token=refresh)

@app.post("/api/auth/register", response_model=UserResponse, status_code=201)
async def register(
    body: RegisterRequest,
    db: AsyncConnection = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Create a new user (admin only)."""
    hashed = hash_password(body.password)
    try:
        async with db.cursor() as cur:
            await cur.execute(
                """INSERT INTO users (email, username, hashed_password, role)
                   VALUES (%s, %s, %s, %s)
                   RETURNING id, email, username, role, is_active""",
                (body.email, body.username, hashed, body.role),
            )
            row = await cur.fetchone()
            await db.commit()
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="Username or email already taken")
        raise HTTPException(status_code=500, detail="Database error")

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create user")
    return UserResponse(
        id=str(row[0]), email=row[1], username=row[2], role=row[3], is_active=row[4]
    )

@app.get("/api/auth/me", response_model=UserResponse)
async def me(user: dict = Depends(get_current_user)):
    return UserResponse(**user)

@app.get("/api/auth/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncConnection = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id, email, username, role, is_active, created_at FROM users ORDER BY created_at"
        )
        rows = await cur.fetchall()
    return [
        UserResponse(
            id=str(r[0]), email=r[1], username=r[2], role=r[3], is_active=r[4],
            created_at=r[5].isoformat() if r[5] else None
        )
        for r in rows
    ]

@app.patch("/api/auth/users/{user_id}/toggle")
async def toggle_user(
    user_id: str,
    db: AsyncConnection = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    async with db.cursor() as cur:
        await cur.execute(
            "UPDATE users SET is_active = NOT is_active, updated_at = NOW() WHERE id = %s RETURNING is_active",
            (user_id,),
        )
        row = await cur.fetchone()
        await db.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"is_active": row[0]}

@app.post("/api/auth/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncConnection = Depends(get_db),
):
    """Request a password reset.

    In production, the token would be sent via email. For this prototype,
    the token is stored server-side only — the user must check logs/DB.
    """
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id, username FROM users WHERE email = %s AND is_active = TRUE",
            (body.email,),
        )
        row = await cur.fetchone()

    if row is None:
        # Return success even if not found — prevents user enumeration
        return {"message": "If that email is registered, a reset link has been generated."}

    user_id = str(row[0])
    token = generate_reset_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    async with db.cursor() as cur:
        # Invalidate any previous unused tokens for this user
        await cur.execute(
            "UPDATE password_reset_tokens SET used = TRUE WHERE user_id = %s AND used = FALSE",
            (user_id,),
        )
        await cur.execute(
            """INSERT INTO password_reset_tokens (user_id, token, expires_at)
               VALUES (%s, %s, %s)""",
            (user_id, token, expires_at),
        )
        await db.commit()

    logger.info("Password reset token generated for user %s", row[1])
    # In demo/prototype mode, return the token so the frontend can redirect
    # directly to the reset page. In production, this would be sent via email.
    return {
        "message": "If that email is registered, a reset link has been generated.",
        "token": token,
    }

@app.post("/api/auth/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncConnection = Depends(get_db),
):
    """Reset password using a valid, unexpired token."""
    async with db.cursor() as cur:
        await cur.execute(
            """SELECT id, user_id, expires_at FROM password_reset_tokens
               WHERE token = %s AND used = FALSE""",
            (body.token,),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already-used reset token",
        )

    token_id, user_id, expires_at = str(row[0]), str(row[1]), row[2]

    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired. Please request a new one.",
        )

    hashed = hash_password(body.new_password)
    async with db.cursor() as cur:
        await cur.execute(
            "UPDATE users SET hashed_password = %s, updated_at = NOW() WHERE id = %s",
            (hashed, user_id),
        )
        await cur.execute(
            "UPDATE password_reset_tokens SET used = TRUE WHERE id = %s",
            (token_id,),
        )
        await db.commit()

    logger.info("Password reset completed for user_id %s", user_id)
    return {"message": "Password has been reset successfully. You can now sign in."}

@app.post("/api/auth/change-password")
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncConnection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Change password for the currently authenticated user."""
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT hashed_password FROM users WHERE id = %s",
            (user["id"],),
        )
        row = await cur.fetchone()

    if row is None or not verify_password(body.current_password, row[0]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    hashed = hash_password(body.new_password)
    async with db.cursor() as cur:
        await cur.execute(
            "UPDATE users SET hashed_password = %s, updated_at = NOW() WHERE id = %s",
            (hashed, user["id"]),
        )
        await db.commit()

    return {"message": "Password changed successfully"}

# ═══════════════════════════════════════════════════════════════════════════
# Reverse proxy — everything else
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_upstream(path: str) -> tuple[str, str] | None:
    """
    Given a request path like ``/api/xai/ask``, return
    ``(upstream_base_url, downstream_path)`` or ``None``.

    Downstream path strips the ``/api`` prefix so that the service
    receives e.g. ``/xai/ask``.
    """
    if not path.startswith("/api/"):
        return None
    parts = path.split("/")
    # parts: ['', 'api', '<domain>', ...]
    if len(parts) < 3:
        return None
    domain = parts[2]
    upstream = SERVICE_MAP.get(domain)
    if upstream is None:
        return None
    downstream = "/" + "/".join(parts[2:])  # e.g. /xai/ask
    return upstream, downstream

@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy(
    request: Request,
    path: str,
    user: dict = Depends(get_current_user),
):
    """Authenticate, then forward request to the responsible microservice."""
    resolved = _resolve_upstream(request.url.path)
    if resolved is None:
        raise HTTPException(status_code=404, detail="No upstream service for this path")

    upstream_base, downstream_path = resolved
    url = f"{upstream_base}{downstream_path}"

    # Forward query string
    if request.url.query:
        url = f"{url}?{request.url.query}"

    # Build headers — pass user identity downstream
    headers: dict[str, str] = {
        "x-user-id": user["id"],
        "x-user-role": user["role"],
    }
    # Preserve original content-type exactly (critical for multipart/form-data boundaries)
    ct = request.headers.get("content-type")
    if ct:
        headers["content-type"] = ct

    body = await request.body()

    client = await _get_client()
    try:
        upstream_resp = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body if body else None,
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Service unavailable: {downstream_path.split('/')[1]}",
        )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Upstream service timed out — try processing fewer documents at once",
        )
    except httpx.WriteTimeout:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Upload timed out — the file may be too large",
        )
    except httpx.PoolTimeout:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="All connections exhausted — try again shortly",
        )

    # Forward error details from upstream services
    if upstream_resp.status_code >= 400:
        try:
            error_body = upstream_resp.json()
            error_detail = error_body.get("error") or error_body.get("detail") or upstream_resp.text
        except Exception:
            error_detail = upstream_resp.text or f"Upstream error {upstream_resp.status_code}"
        logger.warning("Upstream %s returned %d: %s", downstream_path, upstream_resp.status_code, error_detail)
        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            media_type=upstream_resp.headers.get("content-type", "application/json"),
        )

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        media_type=upstream_resp.headers.get("content-type", "application/json"),
    )

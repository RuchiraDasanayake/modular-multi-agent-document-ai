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

import httpx
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

from .config import settings
from .database import DatabasePool
from .deps import get_current_user, get_db, require_admin
from .schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from .auth_service import hash_password, verify_password, create_access_token

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("gateway")

# ---------------------------------------------------------------------------
# Service routing table
# ---------------------------------------------------------------------------
SERVICE_MAP: dict[str, str] = {
    "advice": settings.AHMN_SERVICE_URL,
    "dashboard": settings.AHMN_SERVICE_URL,
    "experiments": settings.AHMN_SERVICE_URL,
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
        _http_client = httpx.AsyncClient(timeout=settings.PROXY_TIMEOUT)
    return _http_client


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


# ═══════════════════════════════════════════════════════════════════════════
# Auth routes (handled locally — not proxied)
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncConnection = Depends(get_db)):
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
    return TokenResponse(access_token=token)


@app.post("/api/auth/signup", response_model=TokenResponse, status_code=201)
async def signup(
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
    except Exception:
        raise HTTPException(status_code=409, detail="Username or email already taken")

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create user")
    token = create_access_token({"sub": str(row[0])})
    return TokenResponse(access_token=token)


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
    except Exception:
        raise HTTPException(status_code=409, detail="Username or email already taken")

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create user")
    return UserResponse(
        id=str(row[0]), email=row[1], username=row[2], role=row[3], is_active=row[4]
    )


@app.get("/api/auth/me", response_model=UserResponse)
async def me(user: dict = Depends(get_current_user)):
    return UserResponse(**user, is_active=True)


@app.get("/api/auth/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncConnection = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id, email, username, role, is_active FROM users ORDER BY created_at"
        )
        rows = await cur.fetchall()
    return [
        UserResponse(
            id=str(r[0]), email=r[1], username=r[2], role=r[3], is_active=r[4]
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
    headers = {
        "x-user-id": user["id"],
        "x-user-role": user["role"],
        "content-type": request.headers.get("content-type", "application/json"),
    }

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
            detail="Upstream service timed out",
        )

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        media_type=upstream_resp.headers.get("content-type", "application/json"),
    )

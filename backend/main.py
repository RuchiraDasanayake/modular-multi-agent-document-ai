"""
AHMN Backend — FastAPI entry point.
Mounts all routers, CORS, lifespan events.
"""

import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on path so `import ahmn_core` works
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings
from app.database import DatabasePool, redis_client
from app.routers import auth, advice, dashboard, experiments, xai, hitl


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    await DatabasePool.get_pool()
    yield
    await DatabasePool.close_pool()
    await redis_client.close()


app = FastAPI(
    title="AHMN — Adaptive Hierarchical Memory Network",
    description="Self-learning document processing advisor with Thompson Sampling, RABI & DAAF",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.BACKEND_CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(advice.router)
app.include_router(dashboard.router)
app.include_router(experiments.router)
app.include_router(xai.router)
app.include_router(hitl.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ahmn-backend"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

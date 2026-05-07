from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

_LOCAL_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
_DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _cors_origins() -> list[str]:
    raw = os.getenv("DOCAI_CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return _LOCAL_DEV_ORIGINS
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def _max_upload_bytes() -> int:
    raw = os.getenv("DOCAI_MAX_UPLOAD_BYTES", str(_DEFAULT_MAX_UPLOAD_BYTES)).strip()
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_UPLOAD_BYTES
    return value if value > 0 else _DEFAULT_MAX_UPLOAD_BYTES


def create_app(runs_dir: Path | None = None, db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="DocAI v2 API", version="0.1.0")
    app.state.runs_dir = runs_dir or Path(os.getenv("DOCAI_RUNS_DIR", "./runs"))
    app.state.db_path = db_path or Path(os.getenv("DOCAI_SQLITE_PATH", "./.docai/docai.sqlite"))
    app.state.max_upload_bytes = _max_upload_bytes()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def _enforce_multipart_upload_size(request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            content_type = request.headers.get("content-type", "")
            if "multipart/form-data" in content_type:
                content_length = request.headers.get("content-length")
                if content_length:
                    try:
                        payload_bytes = int(content_length)
                    except ValueError:
                        payload_bytes = 0
                    if payload_bytes > app.state.max_upload_bytes:
                        return JSONResponse(
                            status_code=413,
                            content={
                                "detail": (
                                    f"Upload too large: {payload_bytes} bytes exceeds "
                                    f"limit {app.state.max_upload_bytes} bytes"
                                )
                            },
                        )
        return await call_next(request)

    from docai_core.api.routers.health import router as health_router
    from docai_core.api.routers.projects import router as projects_router
    from docai_core.api.routers.schemas import router as schemas_router
    from docai_core.api.routers.jobs import router as jobs_router
    from docai_core.api.routers.documents import router as documents_router
    from docai_core.api.routers.runs import router as runs_router
    from docai_core.api.routers.artifacts import router as artifacts_router
    from docai_core.api.routers.execution import router as execution_router
    from docai_core.api.routers.reviews import router as reviews_router
    from docai_core.api.routers.learning_samples import router as learning_samples_router
    from docai_core.api.routers.advisory import router as advisory_router

    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(schemas_router)
    app.include_router(jobs_router)
    app.include_router(documents_router)
    app.include_router(runs_router)
    app.include_router(artifacts_router)
    app.include_router(execution_router)
    app.include_router(reviews_router)
    app.include_router(learning_samples_router)
    app.include_router(advisory_router)

    return app


# Module-level app instance used by uvicorn: `uvicorn docai_core.api.app:app`
app = create_app()

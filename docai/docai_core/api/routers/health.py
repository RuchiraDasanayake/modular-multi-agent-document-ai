"""Health check endpoint."""
from fastapi import APIRouter

from docai_core.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="docai-v2-api")

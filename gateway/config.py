"""
Gateway configuration — server, database, JWT, microservice URLs.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_env_candidates = [
    Path.cwd() / ".env",
    Path(__file__).resolve().parent.parent / ".env",
]
_env_path = str(next((p for p in _env_candidates if p.is_file()), Path(".env")))


class Settings(BaseSettings):
    # ── Postgres (auth tables only) ──
    POSTGRES_URI: str = "postgresql://user:password@localhost:5432/ahmn_db"

    # ── JWT ──
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 h

    # ── CORS ──
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000"

    # ── Microservice URLs (Docker service names) ──
    AHMN_SERVICE_URL: str = "http://ahmn:8001"
    GUARDRAILS_SERVICE_URL: str = "http://guardrails:8002"
    XAI_HITL_SERVICE_URL: str = "http://xai-hitl:8003"
    IDPO_SERVICE_URL: str = "http://idpo:8004"

    # ── Proxy ──
    PROXY_TIMEOUT: float = 60.0

    model_config = SettingsConfigDict(
        env_file=_env_path,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # type: ignore[call-arg]

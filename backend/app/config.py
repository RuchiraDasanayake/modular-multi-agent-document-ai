"""
Backend configuration — server, database, JWT settings.
Loads from environment variables / .env file.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env at project root (two levels up from backend/app/)
_current_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(os.path.dirname(os.path.dirname(_current_dir)), ".env")


class Settings(BaseSettings):
    # ── Postgres ──
    POSTGRES_URI: str = "postgresql://user:password@localhost:5432/ahmn_db"

    # ── Redis ──
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # ── JWT ──
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 h

    # ── CORS ──
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=_env_path,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # type: ignore[call-arg]

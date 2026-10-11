"""
Gateway configuration — server, database, JWT, microservice URLs.
"""

import logging
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_log = logging.getLogger("gateway.config")

_env_candidates = [
    Path.cwd() / ".env",
    Path(__file__).resolve().parent.parent / ".env",
]
_env_path = str(next((p for p in _env_candidates if p.is_file()), Path(".env")))

class Settings(BaseSettings):
    # ── Postgres (auth tables only) ──
    POSTGRES_URI: str = "postgresql://user:password@localhost:5432/ahmn_db"

    # ── Redis (token blacklist) ──
    REDIS_URL: str = "redis://:docai_redis_secret@localhost:6379/1"

    # ── JWT ──
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 h

    # ── CORS ──
    BACKEND_CORS_ORIGINS: str = "*"

    # ── First admin account (created at startup only while no admin exists) ──
    ADMIN_USERNAME: str = "admin"
    ADMIN_EMAIL: str = "admin@localhost"
    ADMIN_PASSWORD: str = ""

    # ── Public self-registration (creates viewer accounts; admins can always add users) ──
    PUBLIC_SIGNUP_ENABLED: bool = False

    def validate_jwt_secret(self) -> None:
        """Ensure a stable JWT secret across restarts.

        Priority:
        1. Explicit JWT_SECRET_KEY env var (not the default).
        2. Previously generated secret persisted in ``/app/.jwt_secret``.
        3. Generate a new random secret, persist it, and reuse next time.
        """
        if self.JWT_SECRET_KEY != "change-me-in-production":
            return  # explicitly set — nothing to do

        secret_file = Path("/app/.jwt_secret")
        if secret_file.exists():
            stored = secret_file.read_text().strip()
            if stored:
                object.__setattr__(self, "JWT_SECRET_KEY", stored)
                _log.info("Loaded persisted JWT secret from %s", secret_file)
                return

        generated = secrets.token_urlsafe(48)
        try:
            secret_file.write_text(generated)
            secret_file.chmod(0o600)
            _log.info(
                "Generated JWT secret and persisted to %s. "
                "Set JWT_SECRET_KEY env var to override.",
                secret_file,
            )
        except OSError:
            _log.warning(
                "⚠️  Could not persist JWT secret to %s — "
                "tokens will be invalidated on restart. "
                "Set JWT_SECRET_KEY env var for production.",
                secret_file,
            )
        object.__setattr__(self, "JWT_SECRET_KEY", generated)

    # ── Microservice URLs (Docker service names) ──
    AHMN_SERVICE_URL: str = "http://ahmn:8001"
    GUARDRAILS_SERVICE_URL: str = "http://guardrails:8002"
    XAI_HITL_SERVICE_URL: str = "http://xai-hitl:8003"
    IDPO_SERVICE_URL: str = "http://idpo:8004"

    # ── Proxy ──
    PROXY_TIMEOUT: float = 300.0
    IDPO_PROXY_TIMEOUT: float = 1200.0

    model_config = SettingsConfigDict(
        env_file=_env_path,
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()  # type: ignore[call-arg]
settings.validate_jwt_secret()

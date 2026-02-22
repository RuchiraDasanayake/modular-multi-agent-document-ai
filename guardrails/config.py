"""Guardrail-specific configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class GuardrailSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    THRESHOLD_FAITHFULNESS: float = Field(0.78, description="Cosine similarity threshold for faithfulness check")
    LOG_LEVEL: str = Field("INFO")


guardrail_settings = GuardrailSettings()  # type: ignore

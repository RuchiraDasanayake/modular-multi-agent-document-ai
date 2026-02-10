from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')
    OPENAI_API_KEY: str = Field("demo-key")  # For optional ragas integration if needed
    THRESHOLD_FAITHFULNESS: float = Field(0.78)  # Synced with validation.py
    LOG_LEVEL: str = Field("INFO")

settings = Settings()  # type: ignore  # Suppress Pylance false positive on missing args (fields have defaults)

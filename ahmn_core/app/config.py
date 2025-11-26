import os
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the absolute path to the .env file (one level up from app/)
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(os.path.dirname(current_dir), ".env")

class Settings(BaseSettings):
    POSTGRES_URI: str
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    model_config = SettingsConfigDict(env_file=env_path, env_file_encoding="utf-8")

settings = Settings() # type: ignore

"""All configuration comes from environment variables / backend/.env. No secrets in code."""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mongodb_uri: str = ""
    mongodb_database: str = "travelmate"
    copilot_model: str = "auto"
    frontend_url: str = "http://localhost:5173"
    copilot_timeout_seconds: float = 90.0
    max_revisions: int = 3
    chroma_dir: str = str(Path(__file__).resolve().parents[1] / "chroma")
    embedding_model: str = "all-MiniLM-L6-v2"
    demo_user_id: str = "demo-user"


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Typed settings loaded from environment / backend/.env."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    APP_NAME: str = "Knowledge Desk"

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""
    DATABASE_URL: str = ""
    STORAGE_BUCKET: str = "documents"
    DEFAULT_TENANT_ID: str = "00000000-0000-0000-0000-000000000001"
    CORS_ORIGINS: str = "http://localhost:5173"

    EMBEDDING_BACKEND: Literal["bge", "hash", "hf"] = "bge"  # hf = Hugging Face Inference API (serverless, no local model)
    HF_TOKEN: str = ""
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    MODEL_CACHE_DIR: Path = BASE_DIR / "data" / "models"
    RETRIEVAL_MIN_SCORE: float = 0.55
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024
    MAX_TEXT_CHARS: int = 3_000_000
    INLINE_PROCESSING: bool = False  # true on AWS Lambda

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def supabase_configured(self) -> bool:
        return bool(self.SUPABASE_URL and self.SUPABASE_SERVICE_ROLE_KEY and self.DATABASE_URL)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

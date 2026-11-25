"""Typed settings loaded from environment / backend/.env."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    APP_NAME: str = "Knowledge Desk"

    DATA_DIR: Path = BASE_DIR / "data"  # database, uploaded files and the session-signing key live here
    DATABASE_PATH: Path = BASE_DIR / "data" / "knowledge.db"
    STORAGE_DIR: Path = BASE_DIR / "data" / "files"
    JWT_SECRET: str = ""  # empty = generated once and kept in data/jwt_secret
    SESSION_HOURS: int = 12
    DEFAULT_TENANT_ID: str = "00000000-0000-0000-0000-000000000001"
    CORS_ORIGINS: str = "https://knowledgedesk.vercel.app,http://localhost:5173"

    EMBEDDING_BACKEND: Literal["bge", "hash", "hf"] = "bge"  # hf = Hugging Face Inference API (serverless, no local model)
    HF_TOKEN: str = ""
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    MODEL_CACHE_DIR: Path = BASE_DIR / "data" / "models"
    RETRIEVAL_MIN_SCORE: float = 0.55
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024
    MAX_TEXT_CHARS: int = 3_000_000
    INLINE_PROCESSING: bool = False  # true only on serverless hosts

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env.local", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]



@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

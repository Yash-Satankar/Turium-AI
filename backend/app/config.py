from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration, read from environment variables (or backend/.env)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_path: str = "data/inbox.db"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Providers
    provider: Literal["gemini", "fake"] = "gemini"
    gemini_api_key: str | None = None
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_chat_model: str = "gemini-2.5-flash"
    embedding_dim: int = Field(default=768, ge=8, le=3072)
    provider_timeout_s: float = Field(default=30.0, gt=0)

    # Retrieval
    min_score: float = Field(default=0.6, ge=-1, le=1)
    snippet_chars: int = 300

    # Chunking
    chunk_size: int = Field(default=800, ge=100)
    chunk_overlap: int = Field(default=120, ge=0)

    # URL fetching
    fetch_timeout_s: float = Field(default=10.0, gt=0)
    fetch_max_bytes: int = Field(default=2_000_000, gt=0)
    fetch_max_redirects: int = Field(default=5, ge=0)
    # Some sites (e.g. Wikipedia) reject bot UAs without contact info: "MyInbox/1.0 (+https://you.example)"
    fetch_user_agent: str = "KnowledgeInbox/0.1 (python-httpx)"

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.provider == "gemini" and not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is required when PROVIDER=gemini "
                "(get a free key at https://aistudio.google.com, or set PROVIDER=fake to run offline)"
            )
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

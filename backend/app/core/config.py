"""
RepoMind AI — Application Configuration

All configuration is loaded from environment variables.
No secrets are hard-coded.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Core ────────────────────────────────────────────────────
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False
    secret_key: str = Field(default="dev_secret_change_me")
    app_name: str = "RepoMind AI"
    version: str = "0.1.0"

    # ── Database ────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://repomind:repomind_password@localhost:5433/repomind"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # ── AI Providers ────────────────────────────────────────────
    llm_provider: Literal["ollama", "bedrock"] = "ollama"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout: int = 120
    ollama_max_tokens: int = 4096

    # Embedding
    embedding_provider: str = "local"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    embedding_batch_size: int = 32

    # ── Security ────────────────────────────────────────────────
    workspace_root: str = "/data/workspaces"
    max_file_size_mb: int = 10
    tool_execution_timeout: int = 60
    tool_output_max_chars: int = 50_000

    # ── Retrieval ───────────────────────────────────────────────
    retrieval_top_k_vector: int = 20
    retrieval_top_k_keyword: int = 20
    retrieval_top_k_final: int = 8
    reranker_enabled: bool = False
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ── CORS ────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── Observability ───────────────────────────────────────────
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    enable_request_logging: bool = True

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith(("postgresql", "sqlite")):
            raise ValueError("DATABASE_URL must be a PostgreSQL or SQLite URL")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()

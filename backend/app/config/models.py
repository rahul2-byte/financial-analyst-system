from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class LlamaServerConfig(BaseModel):
    """Llama.cpp server settings from YAML."""

    binary_path: str
    model_path: str
    host: str
    port: int
    args: dict[str, Any] = Field(default_factory=dict)


class ApiConfig(BaseModel):
    """API runtime settings from YAML."""

    base_url: HttpUrl
    timeout: float


class ModelConfig(BaseModel):
    """LLM model settings from YAML."""

    default_model: str
    max_output_tokens: int


class YamlAppSettings(BaseModel):
    """Top-level YAML settings model."""

    API_TITLE: str = "Financial Intelligence Platform API"
    API_VERSION: str = "v1"
    DEBUG: bool = False
    llama_server: LlamaServerConfig
    api: ApiConfig
    model: ModelConfig
    server_logfile: str


class EnvSettings(BaseSettings):
    """Environment-driven settings."""

    POSTGRES_USER: str = "fin_user"
    POSTGRES_PASSWORD: str = "fin_password"
    POSTGRES_DB: str = "fin_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "financial_context"

    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    BATCH_SIZE_YEARS: int = 5

    ALPHA_VANTAGE_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None

    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    PHOENIX_HOST: str = "http://localhost:6006"

    DEFAULT_LLM_MODEL: str | None = None
    FALLBACK_LLM_MODEL: str = "llama-3b"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def QDRANT_URL(self) -> str:
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"

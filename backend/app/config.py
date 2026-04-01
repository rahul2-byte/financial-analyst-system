"""
Unified configuration system for the Financial Intelligence Platform.

This module consolidates:
- YAML-based config (llama_server, api, model settings)
- Pydantic BaseSettings (database, qdrant, llm configuration)

Usage:
    from app.config import settings

    # Access YAML-loaded config
    settings.llama_server.model_path
    settings.api.base_url

    # Access environment-based config
    settings.DATABASE_URL
    settings.DEFAULT_LLM_MODEL
"""

import os
import yaml
from pathlib import Path
from functools import lru_cache
from pydantic import BaseModel, HttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Dict, Optional

# ============================================================================
# YAML-Loaded Configuration Models
# ============================================================================


class LlamaServerConfig(BaseModel):
    """LLama.cpp server configuration."""

    binary_path: str
    model_path: str
    host: str
    port: int
    args: Dict[str, Any] = Field(default_factory=dict)


class ApiConfig(BaseModel):
    """API server configuration."""

    base_url: HttpUrl
    timeout: float


class ModelConfig(BaseModel):
    """LLM model configuration."""

    default_model: str
    max_output_tokens: int


class YamlAppSettings(BaseModel):
    """Settings loaded from YAML config file."""

    API_TITLE: str = "Financial Intelligence Platform API"
    API_VERSION: str = "v1"
    DEBUG: bool = False
    llama_server: LlamaServerConfig
    api: ApiConfig
    model: ModelConfig
    server_logfile: str


# ============================================================================
# Environment-Based Configuration (Pydantic Settings)
# ============================================================================


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Values can be overridden via:
    1. Environment variables
    2. .env file in project root
    """

    # Database Configuration
    POSTGRES_USER: str = "fin_user"
    POSTGRES_PASSWORD: str = "fin_password"
    POSTGRES_DB: str = "fin_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # Qdrant Configuration
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "financial_context"

    # Data Pipeline Configuration
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    BATCH_SIZE_YEARS: int = 5

    # Provider API Keys
    ALPHA_VANTAGE_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # Langfuse Configuration (Legacy)
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # Phoenix Configuration
    PHOENIX_HOST: str = "http://localhost:6006"

    # LLM Configuration
    DEFAULT_LLM_MODEL: Optional[str] = None
    FALLBACK_LLM_MODEL: str = "llama-3b"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True
    )

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def QDRANT_URL(self) -> str:
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"


# ============================================================================
# Configuration Loading
# ============================================================================


def _get_backend_root() -> Path:
    """Get the absolute path to the backend directory."""
    return Path(__file__).parent.parent.resolve()


def _load_yaml_config() -> YamlAppSettings:
    """Load configuration from YAML file."""
    backend_root = _get_backend_root()
    config_path = backend_root / "config" / "llm_config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")

    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)

    # Resolve paths relative to backend root
    llama_config = config_data.get("llama_server", {})
    binary_path = backend_root / llama_config.get("binary_path", "")
    model_path = backend_root / llama_config.get("model_path", "")

    if not binary_path.exists():
        raise FileNotFoundError(f"Llama.cpp binary not found: {binary_path.resolve()}")
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path.resolve()}")

    config_data["llama_server"]["binary_path"] = str(binary_path.resolve())
    config_data["llama_server"]["model_path"] = str(model_path.resolve())

    # Resolve log file path
    logfile = backend_root / config_data.get("server_logfile", "logs/llama_server.log")
    config_data["server_logfile"] = str(logfile.resolve())

    return YamlAppSettings(**config_data)


# ============================================================================
# Unified Settings Object
# ============================================================================


class AppSettings:
    """
    Unified settings object that combines YAML-loaded and environment-based config.

    This is the main entry point for accessing configuration.
    """

    _yaml_config: Optional[YamlAppSettings] = None
    _env_config: Optional[Settings] = None

    def __init__(self):
        self._yaml_config = None
        self._env_config = None

    def _get_yaml(self) -> YamlAppSettings:
        if self._yaml_config is None:
            self._yaml_config = _load_yaml_config()
        return self._yaml_config

    def _get_env(self) -> Settings:
        if self._env_config is None:
            self._env_config = Settings()
        return self._env_config

    # YAML-loaded properties
    @property
    def API_TITLE(self) -> str:
        return self._get_yaml().API_TITLE

    @property
    def API_VERSION(self) -> str:
        return self._get_yaml().API_VERSION

    @property
    def DEBUG(self) -> bool:
        return self._get_yaml().DEBUG

    @property
    def llama_server(self) -> LlamaServerConfig:
        return self._get_yaml().llama_server

    @property
    def api(self) -> ApiConfig:
        return self._get_yaml().api

    @property
    def model(self) -> ModelConfig:
        return self._get_yaml().model

    @property
    def server_logfile(self) -> str:
        return self._get_yaml().server_logfile

    # Environment-loaded properties (delegate to Settings)
    @property
    def DATABASE_URL(self) -> str:
        return self._get_env().DATABASE_URL

    @property
    def QDRANT_URL(self) -> str:
        return self._get_env().QDRANT_URL

    @property
    def POSTGRES_USER(self) -> str:
        return self._get_env().POSTGRES_USER

    @property
    def POSTGRES_PASSWORD(self) -> str:
        return self._get_env().POSTGRES_PASSWORD

    @property
    def POSTGRES_DB(self) -> str:
        return self._get_env().POSTGRES_DB

    @property
    def POSTGRES_HOST(self) -> str:
        return self._get_env().POSTGRES_HOST

    @property
    def POSTGRES_PORT(self) -> int:
        return self._get_env().POSTGRES_PORT

    @property
    def QDRANT_HOST(self) -> str:
        return self._get_env().QDRANT_HOST

    @property
    def QDRANT_PORT(self) -> int:
        return self._get_env().QDRANT_PORT

    @property
    def QDRANT_COLLECTION(self) -> str:
        return self._get_env().QDRANT_COLLECTION

    @property
    def CHUNK_SIZE(self) -> int:
        return self._get_env().CHUNK_SIZE

    @property
    def CHUNK_OVERLAP(self) -> int:
        return self._get_env().CHUNK_OVERLAP

    @property
    def BATCH_SIZE_YEARS(self) -> int:
        return self._get_env().BATCH_SIZE_YEARS

    @property
    def ALPHA_VANTAGE_API_KEY(self) -> Optional[str]:
        return self._get_env().ALPHA_VANTAGE_API_KEY

    @property
    def OPENAI_API_KEY(self) -> Optional[str]:
        return self._get_env().OPENAI_API_KEY

    @property
    def LANGFUSE_PUBLIC_KEY(self) -> Optional[str]:
        return self._get_env().LANGFUSE_PUBLIC_KEY

    @property
    def LANGFUSE_SECRET_KEY(self) -> Optional[str]:
        return self._get_env().LANGFUSE_SECRET_KEY

    @property
    def LANGFUSE_HOST(self) -> str:
        return self._get_env().LANGFUSE_HOST

    @property
    def PHOENIX_HOST(self) -> str:
        return self._get_env().PHOENIX_HOST

    @property
    def DEFAULT_LLM_MODEL(self) -> str:
        env_override = self._get_env().DEFAULT_LLM_MODEL
        if env_override:
            return env_override
        return self._get_yaml().model.default_model

    @property
    def FALLBACK_LLM_MODEL(self) -> str:
        return self._get_env().FALLBACK_LLM_MODEL


# Global singleton instance
settings = AppSettings()

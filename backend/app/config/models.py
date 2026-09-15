from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPOSITORY_ENV = Path(__file__).resolve().parents[3] / ".env"


class EnvSettings(BaseSettings):
    """Environment-driven settings."""

    API_TITLE: str = "Financial Intelligence Platform API"
    API_VERSION: str = "v1"
    DEBUG: bool = False

    DEFAULT_LLM_MODEL: str = "zai-org/glm-5.3-flash"
    HIVE_API_KEY: str | None = None
    HIVE_BASE_URL: str = "https://api-cdn.thehive.ai/api/v3"
    HIVE_MODEL: str = "zai-org/glm-5.3-flash"
    HIVE_TIMEOUT: float = 120.0
    HIVE_CONNECT_TIMEOUT: float = 5.0
    HIVE_POOL_TIMEOUT: float = 2.0
    HIVE_WRITE_TIMEOUT: float = 10.0
    HIVE_READ_TIMEOUT: float = 20.0
    HIVE_MAX_RETRIES: int = 2
    HIVE_BACKOFF_BASE: float = 0.5
    HIVE_BACKOFF_CAP: float = 4.0
    HIVE_CIRCUIT_FAILURE_THRESHOLD: int = 3
    HIVE_CIRCUIT_RECOVERY_TIMEOUT: float = 30.0
    HIVE_MAX_OUTPUT_TOKENS: int = 4096
    FINAI_CONTEXT_MAX_TOKENS: int = 250_000
    FINAI_CONTEXT_COMPACTION_RATIO: float = 0.9
    MIN_QUALITY_SCORE: float = 40.0
    MAX_ARTICLES_PER_COMPANY: int = 50
    PIPELINE_VERSION: str = "1.0.0"
    TINYFISH_API_KEY: str | None = None
    TINYFISH_SEARCH_URL: str = "https://api.search.tinyfish.ai"
    TINYFISH_SEARCH_TIMEOUT: float = 20.0
    TINYFISH_MAX_RESULTS_PER_QUERY: int = 10
    HTTP_POOL_MAX_CONNECTIONS: int = 10
    HTTP_POOL_MAX_KEEPALIVE_CONNECTIONS: int = 10

    model_config = SettingsConfigDict(
        env_file=(_REPOSITORY_ENV, ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

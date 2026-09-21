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
    FINAI_ROUTER_ENABLED: bool = True
    FINAI_ROUTER_TIMEOUT_SECONDS: float = 10.0
    FINAI_ROUTER_MAX_RETRIES: int = 1
    FINAI_ROUTER_MIN_CONFIDENCE: float = 0.60
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_JEV_BASE_URL: str = "https://openrouter.ai/api/alpha/decisions"
    OPENROUTER_JEV_MODEL: str = "~typesafe/jev-latest"
    HIVE_API_KEY: str | None = None
    HIVE_BASE_URL: str = "https://api-cdn.thehive.ai/api/v3"
    HIVE_MODEL: str = "zai-org/glm-5.3-flash"
    HIVE_TIMEOUT: float = 600.0
    HIVE_CONNECT_TIMEOUT: float = 5.0
    HIVE_POOL_TIMEOUT: float = 2.0
    HIVE_WRITE_TIMEOUT: float = 10.0
    HIVE_READ_TIMEOUT: float = 60.0
    HIVE_MAX_RETRIES: int = 2
    HIVE_BACKOFF_BASE: float = 0.5
    HIVE_BACKOFF_CAP: float = 4.0
    HIVE_CIRCUIT_FAILURE_THRESHOLD: int = 3
    HIVE_CIRCUIT_RECOVERY_TIMEOUT: float = 30.0
    HIVE_MAX_OUTPUT_TOKENS: int = 8192
    HIVE_MAX_REPORT_TOKENS: int = 32768
    HIVE_MAX_REPAIR_TOKENS: int = 8192
    HIVE_MAX_REPORT_REPAIRS: int = 2
    HIVE_REPAIR_TIMEOUT: float = 120.0
    FINAI_AGENT_MAX_RUN_SECONDS: float = 300.0
    FINAI_AGENT_EMERGENCY_MAX_TOOL_CALLS: int = 128
    FINAI_AGENT_MAX_INPUT_TOKENS: int = 32_000
    FINAI_AGENT_DUPLICATE_REUSE_LIMIT: int = 1
    FINAI_CHATGPT_CODEX_ENABLED: bool = False
    FINAI_CHATGPT_CODEX_PRIMARY: bool = True
    FINAI_CHATGPT_CODEX_CLIENT_ID: str = "app_EMoamEEZ73f0CkXaXp7hrann"
    FINAI_CHATGPT_CODEX_ISSUER: str = "https://auth.openai.com"
    FINAI_CHATGPT_CODEX_API_ENDPOINT: str = (
        "https://chatgpt.com/backend-api/codex/responses"
    )
    FINAI_CHATGPT_CODEX_LUNA_MODEL: str = "gpt-5.6-luna"
    FINAI_CHATGPT_CODEX_TERRA_MODEL: str = "gpt-5.6-terra"
    FINAI_CHATGPT_CODEX_SOL_MODEL: str = "gpt-5.6-sol"
    FINAI_CHATGPT_CODEX_ASTRA_MODEL: str = "gpt-6-astra"
    FINAI_CHATGPT_CODEX_ASTRA_ENABLED: bool = False
    FINAI_CHATGPT_CODEX_REDIRECT_HOST: str = "localhost"
    FINAI_CHATGPT_CODEX_REDIRECT_PORT: int = 1455
    FINAI_CHATGPT_CODEX_TIMEOUT_SECONDS: float = 60.0
    FINAI_CHATGPT_CODEX_CREDENTIAL_PATH: str = "~/.config/finai/chatgpt-codex.json"
    FINAI_CONTEXT_MAX_TOKENS: int = 250_000
    FINAI_CONTEXT_COMPACTION_RATIO: float = 0.9
    MIN_QUALITY_SCORE: float = 40.0
    MARKET_DATA_MAX_AGE_DAYS: int = 7
    VENDOR_MAX_RELATIVE_DIFFERENCE: float = 0.02
    MAX_ARTICLES_PER_COMPANY: int = 50
    PIPELINE_VERSION: str = "1.0.0"
    TINYFISH_API_KEY: str | None = None
    TINYFISH_SEARCH_URL: str = "https://api.search.tinyfish.ai"
    TINYFISH_SEARCH_TIMEOUT: float = 45.0
    TINYFISH_QUERY_TIMEOUT: float = 8.0
    TINYFISH_MAX_RESULTS_PER_QUERY: int = 10
    TINYFISH_MAX_QUERIES_PER_RUN: int = 3
    TINYFISH_MAX_RETRIES: int = 1
    TINYFISH_BACKOFF_SECONDS: float = 0.5
    NEWS_PIPELINE_TOTAL_TIMEOUT: float = 60.0
    NEWS_EXTRACTION_TIMEOUT: float = 8.0
    NEWS_MAX_EXTRACTIONS: int = 12
    HTTP_POOL_MAX_CONNECTIONS: int = 10
    HTTP_POOL_MAX_KEEPALIVE_CONNECTIONS: int = 10
    UPSTOX_ACCESS_TOKEN: str | None = None
    UPSTOX_BASE_URL: str = "https://api.upstox.com"
    UPSTOX_TIMEOUT: float = 20.0
    UPSTOX_REQUESTS_PER_SECOND: int = 50
    UPSTOX_REQUESTS_PER_MINUTE: int = 500
    UPSTOX_REQUESTS_PER_30_MINUTES: int = 2000
    FINAI_QUOTA_DB: str = ".finai/quota.sqlite3"
    FINAI_PROVIDER_REQUESTS_PER_SECOND: int = 2
    FINAI_OBSERVABILITY_ENABLED: bool = False
    FINAI_PHOENIX_ENDPOINT: str = "http://127.0.0.1:6006/v1/traces"
    FINAI_PHOENIX_PROJECT: str = "fin-ai-local"
    FINAI_TRACE_CONTENT: str = "redacted_full"
    FINAI_TRACE_MAX_CONTENT_BYTES: int = 1_000_000
    FINAI_TRACE_SAMPLE_RATE: float = 1.0

    model_config = SettingsConfigDict(
        env_file=(_REPOSITORY_ENV, ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

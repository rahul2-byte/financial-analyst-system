# Configuration

Settings are defined by `backend/app/config/models.py` and loaded by Pydantic Settings from the repository `.env` and then `.env`. Names are case-sensitive and unknown variables are ignored. `.env.example` is the authoritative starter list.

## Required or commonly used variables

| Group | Variables | Purpose |
| --- | --- | --- |
| Application | `API_TITLE`, `API_VERSION`, `DEBUG`, `DEFAULT_LLM_MODEL` | FastAPI metadata and defaults |
| Jev | `FINAI_ROUTER_ENABLED`, `FINAI_ROUTER_TIMEOUT_SECONDS`, `FINAI_ROUTER_MAX_RETRIES`, `FINAI_ROUTER_MIN_CONFIDENCE`, `OPENROUTER_API_KEY`, `OPENROUTER_JEV_BASE_URL`, `OPENROUTER_JEV_MODEL` | Optional typed routing |
| Hive | `HIVE_API_KEY`, `HIVE_BASE_URL`, `HIVE_MODEL`, `HIVE_TIMEOUT`, `HIVE_CONNECT_TIMEOUT`, `HIVE_POOL_TIMEOUT`, `HIVE_WRITE_TIMEOUT`, `HIVE_READ_TIMEOUT`, `HIVE_MAX_RETRIES`, `HIVE_BACKOFF_BASE`, `HIVE_BACKOFF_CAP`, `HIVE_CIRCUIT_FAILURE_THRESHOLD`, `HIVE_CIRCUIT_RECOVERY_TIMEOUT` | Main model streaming and recovery |
| Run limits | `FINAI_AGENT_MAX_RUN_SECONDS`, `FINAI_AGENT_EMERGENCY_MAX_TOOL_CALLS`, `FINAI_AGENT_MAX_INPUT_TOKENS`, `FINAI_AGENT_DUPLICATE_REUSE_LIMIT`, `FINAI_CONTEXT_MAX_TOKENS`, `FINAI_CONTEXT_COMPACTION_RATIO` | Bound model/tool work |
| News | `TINYFISH_API_KEY`, `TINYFISH_SEARCH_URL`, `TINYFISH_SEARCH_TIMEOUT`, `TINYFISH_QUERY_TIMEOUT`, `TINYFISH_MAX_RESULTS_PER_QUERY`, `TINYFISH_MAX_QUERIES_PER_RUN`, `TINYFISH_MAX_RETRIES`, `TINYFISH_BACKOFF_SECONDS`, `NEWS_PIPELINE_TOTAL_TIMEOUT`, `NEWS_EXTRACTION_TIMEOUT`, `NEWS_MAX_EXTRACTIONS` | Search, extraction, and quality limits |
| Data quality | `MIN_QUALITY_SCORE`, `MARKET_DATA_MAX_AGE_DAYS`, `VENDOR_MAX_RELATIVE_DIFFERENCE`, `MAX_ARTICLES_PER_COMPANY`, `PIPELINE_VERSION` | Evidence acceptance and metadata |
| Upstox | `UPSTOX_ACCESS_TOKEN`, `UPSTOX_BASE_URL`, `UPSTOX_TIMEOUT`, `UPSTOX_REQUESTS_PER_SECOND`, `UPSTOX_REQUESTS_PER_MINUTE`, `UPSTOX_REQUESTS_PER_30_MINUTES` | Optional market/instrument provider |
| Storage | `FINAI_QUOTA_DB`, `FINAI_PROVIDER_REQUESTS_PER_SECOND`, `HTTP_POOL_MAX_CONNECTIONS`, `HTTP_POOL_MAX_KEEPALIVE_CONNECTIONS` | Local quota and HTTP pool |

## Optional ChatGPT Codex path

Set `FINAI_CHATGPT_CODEX_ENABLED=true` and, if it should replace Hive as the primary provider, `FINAI_CHATGPT_CODEX_PRIMARY=true`. The service uses the configured issuer, endpoint, redirect host/port, timeout, credential path, `gpt-5.6-luna` primary/repair model, and `gpt-6-luna` escalation model. Login and logout are explicit CLI commands:

```bash
PYTHONPATH=backend uv run python -m finai --chatgpt-login
PYTHONPATH=backend uv run python -m finai --chatgpt-logout
```

The credential file is local OAuth state and should not be committed.

## Observability variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `FINAI_OBSERVABILITY_ENABLED` | `false` | Enable Phoenix/OpenTelemetry setup |
| `FINAI_PHOENIX_ENDPOINT` | `http://127.0.0.1:6006/v1/traces` | OTLP HTTP trace endpoint |
| `FINAI_PHOENIX_PROJECT` | `fin-ai-local` | Phoenix project name |
| `FINAI_TRACE_CONTENT` | `redacted_full` | Use `metadata` to omit prompt/response content |
| `FINAI_TRACE_MAX_CONTENT_BYTES` | `1000000` | Bound trace content size |
| `FINAI_TRACE_SAMPLE_RATE` | `1.0` | Trace sampling ratio |
| `FINAI_MODEL_TRACE` | `off` | Set `full` for sensitive local model-call JSONL traces |
| `FINAI_MODEL_TRACE_DIR` | `.finai/model-traces` | Raw trace root |

`FINAI_DIAGNOSTICS=trace|payloads` is a runtime diagnostic variable set by CLI flags; it is not listed in `EnvSettings`.

## Defaults that matter operationally

- Hive generation timeout budget: 600 seconds; read timeout: 60 seconds; maximum retries: 2.
- Agent run budget: 300 seconds and 128 emergency tool calls.
- Context budget: 250,000 tokens with compaction at 90%.
- News pipeline total timeout: 60 seconds; extraction timeout: 8 seconds; maximum extractions: 12.
- Upstox is disabled when `UPSTOX_ACCESS_TOKEN` is empty.
- Phoenix is disabled unless explicitly enabled.

Do not copy real credentials into `.env.example`, source files, traces, or documentation. Full traces and session artifacts may contain sensitive research content even after common credential redaction.

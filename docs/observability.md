# Observability and artifacts

## Event and run records

The runtime emits typed events from `backend/app/events/models.py`. Important event types include route decisions, skill selection, provider attempts/retries/failures, tool lifecycle, source updates, response deltas, clarification, cancellation, and terminal completion/failure.

`TraceLedger` persists semantic events under the session directory. `SessionStore.write_run()` writes a JSON run artifact containing the query, terminal status, events, creation time, and a feedback summary. The CLI exposes local inspection through `/debug`, `/logs`, and `/trace` commands in the Textual interface.

## Provider archives and replay

`ProviderArchive` writes immutable snapshots under `<data-dir>/provider-snapshots/`, keyed by the SHA-256 of canonical provider, operation, payload, and fetch-time content. Loading verifies both the stored hash and the file path. `--replay-snapshots` maps provider operations to those hashes and replaces live model/YFinance/news dependencies with replay adapters.

Replay is strict about missing or mismatched snapshots. It is suitable for deterministic tests and local diagnosis, but a replay input must contain the complete sequence needed by the requested execution path.

## Phoenix/OpenTelemetry

Phoenix is optional. When `FINAI_OBSERVABILITY_ENABLED=true`, `backend/app/observability/tracing.py` registers an OTLP HTTP exporter, instruments HTTPX, and optionally instruments FastAPI. Setup and shutdown failures are logged and do not stop the research run. The default project is `fin-ai-local`.

Start a local Phoenix instance with the optional dependency group:

```bash
UV_CACHE_DIR=.uv-cache uv sync --group observability
PHOENIX_WORKING_DIR=.finai/phoenix PHOENIX_DEFAULT_RETENTION_POLICY_DAYS=30 \
  uvx --from arize-phoenix==20.14.0 phoenix serve
```

Then set `FINAI_OBSERVABILITY_ENABLED=true` and open `http://127.0.0.1:6006`. Use `FINAI_TRACE_CONTENT=metadata` when prompt and response content should not be sent to the collector.

## Raw model-call traces

`FINAI_MODEL_TRACE=full` enables owner-only JSONL files under `FINAI_MODEL_TRACE_DIR`. These include request bodies, response events, and timing details for local diagnosis. Authorization headers and credential-store contents are excluded, but prompts, market evidence, and model output can remain. The existing detailed format and pilot instructions are in [`model-call-tracing.md`](model-call-tracing.md).

## Metrics and retention

Provider timing/attempt metrics are process-local. The repository does not export a metrics endpoint or ship logs to an external system. Model trace folders older than seven days are eligible for cleanup when new traces are created; general session artifacts, provider snapshots, and quota data have no comparable automated retention policy.

The local filesystem is not encrypted or centrally backed up by this repository. Treat `.finai/`, local logs, credentials, and generated evaluation artifacts as sensitive.

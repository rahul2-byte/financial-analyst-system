# Research failure runbook

1. Inspect the newest `.finai/sessions/*/runs/*.json` and `events.v1.jsonl`.
2. Check `.finai/logs/finai.log` for the first `tool.failed`, `provider.failed`,
   or `run.failed` event.
3. Missing `HIVE_API_KEY`/`TINYFISH_API_KEY`: configure `.env` and rerun.
4. Invalid, stale, or incomplete evidence: retry with a confirmed ticker or
   accept the explicit partial/insufficient-data result; do not infer values.
5. For interrupted runs, restart the CLI; `SessionStore` marks abandoned runs
   and preserves checkpoints for safe inspection.

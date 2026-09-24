# Local model-call traces

Set `FINAI_MODEL_TRACE=full` for a local process to record exact outbound model
request bodies, full assembled responses, streamed chunk timing, provider
attempts, retries, failures, and fallback. This covers AgentLoop generation and
repair, ChatGPT Codex and Hive, Jev routing and output review, and standalone
evaluation judge calls. Tracing is disabled unless explicitly enabled.

Trace files are append-only JSONL under `.finai/model-traces/YYYY-MM-DD/` by
default. Calls in the same run share one file; each record contains its call ID.
Set `FINAI_MODEL_TRACE_DIR` to choose another local directory. Direct calls
without a run or conversation ID get a per-call file. Files and directories
are created with owner-only permissions. Tool-created dated folders older than
seven days are removed when a new trace is created. Unowned folders or folders
containing other files are preserved, and existing directory permissions remain
unchanged.

The trace includes the full prompt, evidence/tool results, and model output.
Treat it as sensitive local data. Authorization headers and credential-store
contents are never written. Do not commit, publish, or share traces without
reviewing and redacting them first.

## Run the existing 8-case pilot with tracing

Use new output paths so the completed pilot artifacts remain immutable:

```sh
FINAI_MODEL_TRACE=full \
FINAI_MODEL_TRACE_DIR=.finai/evals/gpt-pilot-model-trace-20260923/model-traces \
FINAI_LIVE_EVAL=1 PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache \
uv run python -m evals.execute \
  --cases .finai/evals/upstox-pilot-20260922.jsonl \
  --expected-cases 8 \
  --output-dir .finai/evals/gpt-pilot-model-trace-20260923/artifacts \
  --results .finai/evals/gpt-pilot-model-trace-20260923/results.jsonl \
  --events .finai/evals/gpt-pilot-model-trace-20260923/events.jsonl \
  --metrics .finai/evals/gpt-pilot-model-trace-20260923/metrics.jsonl \
  --model gpt-5.6-luna \
  --escalation-model gpt-6-luna \
  --allow-live
```

The command makes live provider calls and may consume account quota. It is not
run by the test suite. Use the normal `--resume` option only if this new run is
interrupted, keeping all paths and model options unchanged.

For a local interactive/one-shot AgentLoop run:

```sh
FINAI_MODEL_TRACE=full PYTHONPATH=backend:. UV_CACHE_DIR=.uv-cache \
uv run python -m finai --plain "Ask a bounded research question"
```

Inspect a trace by run ID or call ID:

```sh
find .finai/model-traces -type f -name '*.jsonl' -print
jq . .finai/model-traces/YYYY-MM-DD/<run-or-call-id>.jsonl
```

`request.attempt` contains the actual provider JSON body but no HTTP headers.
`call.completed` contains the assembled text/tool calls and chunk timing
entries. If a process stops mid-call, the file ends after the last durable
record, usually `request.attempt`, with no matching completion record. The
`read_trace()` helper ignores a malformed final partial line while preserving
all earlier complete records.

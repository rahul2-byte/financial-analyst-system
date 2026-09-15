# FIN-AI diagnostics

Use the CLI flags only while investigating a failing local run:

```bash
python -m finai --debug --data-dir .finai "analyse HDFC Bank"
python -m finai --debug-payloads --data-dir .finai "analyse HDFC Bank"
```

`--debug` records lifecycle events, run IDs, event sequence numbers, timings,
provider attempts, tool outcomes, exceptions, and persistence activity in
`.finai/logs/finai.log`. `--debug-payloads` additionally records bounded,
redacted JSON payloads. Secrets and private reasoning are excluded.

The ordered event ledger remains in
`.finai/sessions/<session-id>/events.v1.jsonl`; large event payloads are stored
under its `artifacts/` directory. Use `/debug`, `/trace`, and `/logs` in the
interactive client to inspect the current run.

When reporting a failure, include the session ID, run ID, last event type and
sequence, provider attempt/phase, tool name (if present), and the relevant
exception traceback. Do not attach `.env`, credentials, or unredacted payloads.

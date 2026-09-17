# FIN-AI runtime guide

## Entry points

- CLI: `PYTHONPATH=backend python -m finai`
- HTTP: `app.main:app`, with `/api/chat` returning Server-Sent Events
- Python import: `from finai.session import FinAIRepl`

## Production flow

```text
CLI or HTTP adapter -> AgentLoop -> HiveService
                    -> FinancialToolRunner -> providers / deterministic quant
                    -> ResearchEvent -> TUI or SSE adapter
```

`finai/session.py` owns terminal session state. Persistence is delegated to
`SessionPersistence` and execution to `ResearchRunner`.

Research mode buffers the model's final response, validates its structured
claims and current-run evidence in `AgentLoop`, then renders and persists it.
Rejected drafts are neither streamed nor persisted. Conversational mode keeps
ordinary token streaming.

## Safe change locations

- Terminal presentation: `backend/finai/app.py`, `render.py`, and `styles/`.
- Session artifact formats: `SessionStore` and its tests.
- Model/tool iteration: `backend/app/core/agent_loop/`.
- Providers: `backend/app/services/` and `backend/data/`.
- Financial calculations: `backend/quant/` with deterministic tests.

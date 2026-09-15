# FIN-AI runtime guide

## Entry points

- CLI: `PYTHONPATH=backend python -m finai`
- HTTP: `app.main:app`, with `/api/chat` returning Server-Sent Events
- Compatibility import: `from finai.__main__ import FinAIRepl`

## Production flow

```text
CLI or HTTP adapter -> AgentLoop -> HiveService
                    -> RegistryToolRunner -> providers / deterministic quant
                    -> ResearchEvent -> TUI or SSE adapter
```

`finai/session.py` is the terminal compatibility facade. Persistence is
delegated to `SessionPersistence` and production execution to `ResearchRunner`.
The former LangGraph/PipelineOrchestrator runtime is removed; specialist
handlers now use the shared AgentLoop-compatible contracts.

## Safe change locations

- Terminal presentation: `backend/finai/app.py`, `render.py`, and `styles/`.
- Session artifact formats: `SessionStore` and its tests.
- Model/tool iteration: `backend/app/core/agent_loop/`.
- Providers: `backend/app/services/` and `backend/data/`.
- Financial calculations: `backend/quant/` with deterministic tests.

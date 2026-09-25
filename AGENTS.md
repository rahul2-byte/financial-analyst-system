# Repository agent guidance

FIN-AI is a CLI-first financial research system. Keep deterministic market calculations in Python and keep LLM synthesis grounded in provider evidence. The system does not place orders.

## Repository boundaries

- `backend/finai/`: CLI, Textual UI, rendering, sessions, and local persistence.
- `backend/app/`: configuration, routing, bounded AgentLoop, providers, events, security, and observability.
- `backend/data/`: YFinance, optional Upstox, and the TinyFish news pipeline.
- `backend/quant/`: deterministic fundamental and technical analysis.
- `backend/experiments/`: separate offline feature/signal/simulation runtime.
- `backend/skills/`: validated runtime skill packages.
- `evals/`: synthetic, replay, live, adversarial, and judge evaluation tooling.
- `docs/`: maintained system and operational documentation.

The current runtime is CLI-first. FastAPI exposes root and health routes only; it is not a research API or SSE gateway.

## Engineering rules

- Do not move ratios, indicators, forecasts, or other financial calculations into prompts or model code.
- Keep external access behind provider/service adapters and registered tools.
- Validate and normalize provider data before passing it to synthesis; preserve provenance.
- Use Pydantic v2 for external schemas and settings.
- Load LLM-facing instructions through `PromptRegistry` and validate skill manifests.
- Do not commit secrets or credentials. Treat local `.finai/` artifacts and full traces as sensitive.
- Prefer the smallest coherent change and avoid speculative abstractions.
- Add tests for new behavior and preserve fail-closed behavior for unsupported evidence.

## Local commands

```bash
uv sync
uv run ruff check backend evals
uv run mypy backend
uv run pytest backend/tests --no-cov
uv run pytest backend/tests --cov=backend --cov-report=term-missing --cov-fail-under=70
PYTHONPATH=backend uv run python -m finai --help
PYTHONPATH=backend uv run python -m experiments --help
PYTHONPATH=. uv run python -m evals.validate
```

For setup, runtime flow, configuration, deployment reality, and evaluation limitations, use [`README.md`](README.md) and [`docs/`](docs/). Issue operations and triage labels are in [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md).

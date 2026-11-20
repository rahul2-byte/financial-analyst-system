# Contributing

FIN-AI is a CLI-first financial research system. Read [`AGENTS.md`](AGENTS.md) for
repository boundaries and engineering rules. Key points:

- Keep deterministic financial calculations in Python, never in prompts or model code.
- Keep external access behind provider adapters and registered tools.
- Add tests for new behavior and preserve fail-closed handling of unsupported evidence.
- Never commit secrets. Treat `.finai/` artifacts and full traces as sensitive.

## Setup

The project uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Checks

Run all of these before opening a pull request.

```bash
uv run ruff check backend evals
uv run mypy backend
uv run pytest backend/tests --no-cov
```

Coverage must stay at or above 70%:

```bash
uv run pytest backend/tests --cov=backend --cov-report=term-missing --cov-fail-under=70
```

Validate the evaluation tooling:

```bash
PYTHONPATH=. uv run python -m evals.validate
```

## Running the CLIs

```bash
PYTHONPATH=backend uv run python -m finai --help
PYTHONPATH=backend uv run python -m experiments --help
```

## Pull requests

Prefer the smallest coherent change. Update [`CHANGELOG.md`](CHANGELOG.md) under
`Unreleased` for user-visible changes. See [`docs/`](docs/) for system documentation.

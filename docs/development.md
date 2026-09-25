# Development

## Environment

```bash
uv sync
cp .env.example .env
```

The repository is not installed as a package. Module commands that import `app`, `finai`, or `experiments` use `PYTHONPATH=backend` (or the equivalent configured test path). `uv.lock` is committed and CI uses `uv sync --frozen --dev`.

## Main commands

```bash
# CLI
PYTHONPATH=backend uv run python -m finai --help

# FastAPI development server
PYTHONPATH=backend uv run uvicorn app.main:app --reload

# Independent offline experiment CLI
PYTHONPATH=backend uv run python -m experiments --help

# Evaluation CLI
PYTHONPATH=. uv run python -m evals.validate
uv run python evals/run.py --help
```

## Tests and static checks

```bash
uv run ruff check backend evals
uv run mypy backend
uv run python -m compileall -q backend evals
uv run pytest backend/tests --no-cov
uv run pytest backend/tests --cov=backend --cov-report=term-missing --cov-fail-under=70
```

Pytest defaults are defined in `pyproject.toml`: asyncio mode is automatic, coverage targets `backend`, and the default coverage threshold is 70%. Use `--no-cov` for focused behavioral runs.

The tests are organized into `backend/tests/unit/` and `backend/tests/integration/`. The integration tests cover CLI research flow, smoke execution, experiments, and storage recovery. Unit tests cover the AgentLoop, providers, news pipeline, quant logic, events, publication, persistence, evaluation helpers, and safety policy.

## Change boundaries

Keep provider access behind service/provider adapters and keep deterministic financial calculations behind `backend/quant/` or the registered analysis tools. Do not move ratios, indicators, or forecasts into prompts or model code. Use Pydantic models for external schemas and preserve provenance when adding evidence paths.

For a new tool, update the tool definitions, argument validation, `FinancialToolRunner`, relevant prompts/skills, event or publication behavior if needed, and tests. For a new setting, update `EnvSettings` and `.env.example`, then document its default and operational impact.

## Reproducibility

Use provider snapshots for deterministic local diagnosis:

```bash
PYTHONPATH=backend uv run python -m finai \
  --replay-snapshots snapshots.json \
  --plain "Analyze RELIANCE.NS"
```

A replay mapping references content hashes under the selected data directory. Live provider credentials are not used in replay mode. Evaluation runners record model/prompt/configuration metadata and classify synthetic, replay, and live evidence separately.

## CI equivalence

The closest local reproduction of CI is:

```bash
uv run ruff check backend/ evals/
uv run mypy backend/
PYTHONPATH=. uv run python -m evals.validate
PYTHONPATH=backend:. uv run python -m evals.adversarial
PYTHONPATH=backend:. uv run pytest \
  backend/tests/unit/test_eval_numeric.py \
  backend/tests/unit/test_eval_support.py \
  backend/tests/unit/test_eval_stage_metrics.py \
  backend/tests/unit/test_adversarial_assertions.py \
  --no-cov
uv run pytest backend/tests --no-cov
uv run pytest backend/tests --cov=backend --cov-report=term-missing --cov-fail-under=70
```

## Known repository inconsistencies

The implementation is authoritative. Some older guidance still refers to nonexistent `backend/agents/`, `CONTEXT.md`, `docs/adr/`, or HTTP research/SSE execution. Those claims are not part of the current runtime. The current structure is documented in [`architecture.md`](architecture.md).

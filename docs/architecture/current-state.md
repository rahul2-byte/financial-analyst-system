# FIN-AI architecture audit

## Production path

```text
python -m finai
  -> finai.cli
  -> FinAIRepl / FinAIApp
  -> ResearchRunner
  -> AgentLoop
  -> FinancialToolRunner
  -> provider and deterministic quant handlers
  -> typed ResearchEvent stream
  -> session store and terminal renderer
```

The `AgentLoop` is the canonical runtime. The Textual UI and plain/JSON CLI
are interfaces over that loop; they do not own financial logic.

## Current component mapping

| Current component | Target responsibility | Action |
| --- | --- | --- |
| `finai.cli` | CLI interface and lifecycle | KEEP |
| `finai.app` and `finai.render` | Presentation and event consumption | KEEP; incremental decomposition |
| `finai.session*` | Session persistence and runtime wiring | REFACTOR; remove implicit fallbacks |
| `app.core.agent_loop.runtime` | Bounded workflow and tool boundary | REFACTOR; enforce evidence contracts |
| `app.core.agent_loop.tool_runner` | Tool schemas and deterministic execution | KEEP; finite direct boundary |
| `data.providers.yfinance` | External data adapter | REFACTOR; add explicit metadata and quality status |
| `quant/*` | Deterministic financial calculations | KEEP; extend only behind validated inputs |
| `app.events.ledger` | Ordered local audit artifact | KEEP; extend run manifest later |
| `evals/*` | Offline quality measurement | KEEP; populate frozen, reviewed cases |

## Dependency order

```text
RuntimeResources
  -> evidence identity and validation
  -> deterministic quant services
  -> structured report/publication gate
  -> workflow failure handling
  -> evaluation and replay
  -> observability and production hardening
```

## P0 backlog

1. Close the quantitative input trust boundary and prevent cross-ticker cache reuse.
2. Define evidence metadata and report claim contracts.
3. Require a publication gate before a run is reported as complete.
4. Populate a small frozen benchmark and add failure-case regression tests.

This audit is intentionally limited to the current local runtime. It does not
claim that a live vendor feed, licensing arrangement, or historical dataset is
institutional-grade until independently verified.

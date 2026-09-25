# ML and AI system

## What is and is not learned

The repository does not contain a training pipeline for an LLM, embeddings, a vector index, or a learned ranking model in the research runtime. The AI layer is provider-hosted generation plus typed routing. Financial calculations are deterministic Python code in `backend/quant/` and `backend/app/core/agent_loop/tool_runner.py`.

## Prompt and skill control

`backend/app/core/prompts/registry.py:PromptRegistry` loads `backend/app/core/prompts/prompts.yaml` with a duplicate-key-checking YAML loader. It flattens semantic prompt namespaces, validates placeholders, and rejects missing or unexpected render variables. FastAPI loads the bundled registry during application lifespan; the CLI loads it while building runtime resources.

`backend/skills/*/SKILL.md` contains reviewed package manifests. `SkillRegistry` validates IDs, referenced files, allowed tool names, and hashes each skill file. Query words select at most two skills. The selected skill prompt and package hash are emitted in `SkillSelected` events. Current skill packages cover equity research, fundamental analysis, technical analysis, news evidence, and report synthesis.

## Providers and model roles

| Role | Implementation | Default | Failure behavior |
| --- | --- | --- | --- |
| Typed route decision | `JevService` | `~typesafe/jev-latest` through OpenRouter | Deterministic/baseline route on missing key, low confidence, invalid response, or failure |
| Main generation | `HiveService` | `zai-org/glm-5.3-flash` through Hive | Bounded retry, circuit breaker, partial-output handling, or terminal failure |
| Optional primary generation | `ChatGPTCodexService` | `gpt-5.6-luna`; escalation `gpt-6-luna` | Local OAuth credential refresh and fallback to Hive before streaming |

The provider stream is OpenAI-compatible SSE for Hive. Tool-call fragments are merged before they reach the loop. Completed provider events are archived when a `ProviderArchive` is configured.

## Orchestration

`ResearchRunner.stream()` decides whether a request is a direct tool lookup, clarification, denial, or a full `AgentLoop` run. For full runs, `AgentLoop.run()`:

1. Adds the core system prompt and selected skill prompts.
2. Adds a lookup or report schema when the answer contract requires structured output.
3. Streams model rounds and typed provider events.
4. Validates and executes model tool calls through `ToolExecutor`.
5. Tracks evidence availability and provenance through `EvidenceAccounting`.
6. Applies duplicate-call and time/tool/token limits.
7. Reviews or repairs structured output when configured.
8. Publishes a report only when the evidence and schema checks pass; otherwise it emits an evidence-limited result.

The loop yields `ResearchEvent` values rather than mutating the UI. The Textual UI, plain renderer, JSON renderer, and trace ledger consume that same stream.

## Evidence and publication

Research schemas in `backend/app/core/research_schemas.py` distinguish citations, provenance, evidence records, findings, claims, and agent results. Provenance includes source, dataset, instrument, observation and ingestion times, version, quality status, and optional currency/timezone/adjustment/hash fields.

The publication layer in `backend/app/core/agent_loop/publication.py` parses lookup/report outputs, checks required fields and evidence references, detects unreferenced fact markers, and allows bounded repairs. A report is not equivalent to a validated financial conclusion: the system can only validate the structural relationship between claims and the evidence available in the current run.

## Deterministic quantitative layer

### Fundamentals

`quant.fundamentals:FundamentalScanner` consumes YFinance-style fields such as P/E, price-to-book, debt-to-equity, margin, and ROE. It handles missing/non-finite values and emits explanatory text. It does not claim a sector baseline when one was not supplied.

### Technical indicators

`quant.technical_engine:TechnicalEngine` validates non-empty finite OHLCV data and positive, internally consistent prices. It computes the enabled registry with TA-Lib and optional Pandas TA Classic indicators:

- SMA and EMA at 20, 50, and 200 bars
- ADX 14, RSI 14, ATR 14, NATR 14
- OBV, MFI 14, MACD 12/26/9
- Bollinger bands 20/2, Keltner channel 20, and CMF 20

Short series are returned as `partial` and mark unavailable long-lookback indicators rather than fabricating values.

### Offline experiments

`backend/experiments/` is independent from the agent runtime. Its CLI loads a dataset, generates features and signals, creates expanding or rolling temporal splits, purges overlapping label windows with optional embargo, shifts execution to the next bar open, simulates fills with explicit costs/limits, calculates metrics, and writes a registry artifact. It is hypothetical and does not place orders.

## Data sources

The research runtime uses YFinance by default. Upstox is optional and is preferred for supported daily/instrument/fundamental paths when configured. TinyFish searches news; article extraction uses `trafilatura`/PDF support through the news pipeline. There is no RAG index or persistent corpus. Current-run evidence is passed through loop state and archived locally when provider archiving is active.

## Evaluation interpretation

The evaluation harness measures contract behavior, evidence selection, support/citation structure, operational outcomes, and selected offline experiment metrics. It does not provide a trained-model benchmark. Human labels are absent for the recorded real-v1 evaluation, and the repository does not contain a defensible financial-answer accuracy or investment-performance result. See [`evaluation.md`](evaluation.md).

## Main AI failure modes

- Provider timeout, incomplete SSE, rate limiting, or circuit-open state
- Router failure or low-confidence route
- Ambiguous instrument identity
- Missing or stale market/news evidence
- Unsupported or malformed tool arguments
- Duplicate tool calls or exhausted run budgets
- Structured report with unsupported claims or invalid citations
- Prompt injection or unsafe request patterns
- Provider credentials or local replay snapshots missing

The implemented response is bounded execution, clarification, provider fallback where available, and explicit partial/insufficient-data terminal statuses. It is not a guarantee that a plausible answer is financially correct.

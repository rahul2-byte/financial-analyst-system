# Prompt management

LLM-facing instructions live in `backend/app/core/prompts/prompts.yaml`.
Application code retrieves them through `PromptRegistry`; it must not parse
YAML or define replacement system prompts inline.

Keys are semantic dotted names, grouped by boundary:

```yaml
prompts:
  agent_loop:
    retry:
      empty_answer:
        template: "The previous response contained no visible answer."
```

Use `PromptRegistry.get("agent_loop.retry.empty_answer")` for static text and
`PromptRegistry.render("session.research_plan", ticker=ticker)` for templates.
Templates use strict named placeholders. Missing, unexpected, malformed, empty,
duplicate, or incorrectly typed values fail during load or render with a
descriptive `PromptConfigurationError`/`PromptRenderError`.

The bundled registry is immutable after loading and cached for the process.
FastAPI startup and runtime-resource construction validate it before use. Logs
contain only the source path and key count, never rendered prompt content or
runtime variables. There are currently no environment-specific overrides.

Tool descriptions, Jev criteria, report-repair instructions, AgentLoop system
messages, and selected-skill instructions are all prompt-managed. User-facing
CLI/UI messages, provider search-query templates, and runtime data are not
LLM prompts and remain in their owning modules.

`agent_loop.core.system` is injected on every model request. It is the small,
always-on policy layer for NSE/BSE scope, evidence precedence, untrusted source
text, prohibited assistance, and clarification behavior. Report schema rules
remain conditional under `agent_loop.report.system`; they are not a substitute
for runtime validation. Direct deterministic lookups do not use model wording:
the runtime requires successful data plus source and observation/as-of metadata
and emits one terminal status.

Add a prompt by choosing a stable semantic key, preserving existing whitespace,
adding a regression test for rendered output, and consuming it through the
registry. Do not add behavioral instructions directly to application code.

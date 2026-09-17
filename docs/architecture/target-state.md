# Target state

FIN-AI remains a single-process AgentLoop application. Typed boundaries surround
providers, deterministic quant services, reasoning agents, publication, risk,
evaluation, and local artifacts. External providers are validated before use;
LLM output is advisory and cannot bypass deterministic validation or risk policy.

```text
CLI / HTTP -> AgentLoop -> typed tools -> validated provider data
                         |             -> deterministic quant
                         -> publication gate -> session artifacts
```

Change providers in `backend/data/providers`, calculations in `backend/quant`,
tools in `backend/app/core/tools`, prompts in `backend/app/core/prompts`, and
evaluation cases in `evals/gold`.

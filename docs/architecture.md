# FIN-AI architecture and evaluation boundary

The runtime follows:

```text
request -> validation -> bounded plan -> data fetch/validation -> quant tools
        -> source discovery/extraction -> agent research -> synthesis -> critic -> hard validation
```

Quantitative outputs are produced by Python under `backend/quant/` and recorded as evidence. Agents may plan and explain, but do not calculate ratios, indicators, scores, or forecasts. Extracted source evidence and citations remain separate from structured tool outputs.

`backend/finai` is the interactive terminal client. It pauses for clarification and plan approval before running the bounded research graph, then records the session and run artifacts under `.finai/`. `evals/run.py` is intentionally outside the runtime graph. It evaluates recorded outputs against frozen JSONL tasks, which prevents provider availability, changing prices, or changing news from altering an offline regression result. Live provider runs use the same result shape but remain a separate diagnostic mode.

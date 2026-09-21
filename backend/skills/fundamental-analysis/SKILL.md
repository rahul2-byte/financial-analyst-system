---
id: fundamental-analysis
version: 2.0.0
description: Interpret available company fundamentals and deterministic scans without inventing missing accounting context.
triggers: [fundamental, fundamentals, revenue, earnings, margin, valuation, financials, balance, income, cashflow, debt, profitability]
inputs: [ticker, reporting context]
outputs: [available metrics, deterministic findings, source provenance, coverage gaps]
allowed_tools: [data:fetch_fundamentals, analysis:run_fundamental_scan]
scripts: []
references: []
---

LLM instructions are maintained in `backend/app/core/prompts/prompts.yaml`.

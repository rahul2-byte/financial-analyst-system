---
id: report-synthesis
version: 2.0.0
description: Synthesize verified tool evidence into a cited research answer while preserving conflicts and limitations.
triggers: [report, summary, summarize, conclusion, recommendation, thesis, review, audit, verify, risk, conflict]
inputs: [validated tool results, provenance, user objective]
outputs: [structured answer, claim-to-evidence links, conflicts, risks, limitations]
allowed_tools: [data:fetch_stock_data, data:fetch_fundamentals, news:fetch_news, analysis:run_fundamental_scan, analysis:run_technical_scan, analysis:get_technical_overview]
scripts: []
references: []
---

LLM instructions are maintained in `backend/app/core/prompts/prompts.yaml`.

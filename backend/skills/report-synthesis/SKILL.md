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

Distinguish observed facts, deterministic findings, and interpretation. Every material claim must map to returned evidence and every number must use the publication contract's fact marker. Preserve disagreements in period, unit, currency, source, or data quality; do not silently select a preferred value. If evidence is missing or the structured answer fails validation, state the limitation and allow the deterministic fallback to speak for itself.

Do not claim that publication validation proves qualitative truth, and do not present technical or fundamental findings as guaranteed returns or personalized execution advice.

---
id: thesis-review
version: 1.0.0
description: Review an investment thesis for evidence coverage, logical gaps, assumptions, and decision relevance.
triggers: [thesis, review, conviction, investment, decision, assumptions]
inputs: [thesis, findings, source records]
outputs: [coverage review, unsupported claims, open questions]
allowed_tools: [validation:validate_report]
scripts: []
references: []
---

Map each conclusion to evidence. Separate fact, inference, and assumption; identify missing evidence and avoid a buy or sell recommendation unless the user explicitly requests analysis.

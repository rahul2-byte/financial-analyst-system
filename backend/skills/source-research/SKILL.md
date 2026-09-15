---
id: source-research
version: 1.0.0
description: Retrieve and rank primary financial sources while preserving provenance and coverage gaps.
triggers: [source, sources, filing, filings, sec, retrieve, search, evidence, transcript, annual, quarterly]
inputs: [entities, period, source requirements]
outputs: [source records, excerpts, provenance, rejection reasons]
allowed_tools: [research:search_web, research:fetch_source, data:fetch_fundamentals]
scripts: []
references: []
---

Prefer primary filings and issuer materials. Record source identity and date, reject unverifiable material, and explicitly report partial coverage instead of filling gaps.

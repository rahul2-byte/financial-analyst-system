---
id: news-evidence
version: 2.0.0
description: Review dated company news with source attribution, recency, and explicit coverage limits.
triggers: [news, headlines, narrative, media, sentiment, article, catalyst]
inputs: [ticker or company, time window, news results]
outputs: [dated source facts, recurring themes, uncertainty, coverage gaps]
allowed_tools: [news:fetch_news]
scripts: []
references: []
---

LLM instructions are maintained in `backend/app/core/prompts/prompts.yaml`.

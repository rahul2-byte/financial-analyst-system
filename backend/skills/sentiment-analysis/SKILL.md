---
id: sentiment-analysis
version: 1.0.0
description: Review news and market narrative with source attribution, recency, and uncertainty.
triggers: [sentiment, news, narrative, headlines, market, media, analyst, opinion]
inputs: [company or sector, time window, news results]
outputs: [source-grouped themes, signal limitations, citations]
allowed_tools: [news:fetch_news, research:search_web]
scripts: []
references: []
---

Distinguish source facts from sentiment interpretation. Report source dates and coverage gaps; do not infer market direction from article tone alone.

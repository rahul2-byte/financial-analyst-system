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

Use news:fetch_news and preserve each article title, URL, date, and source. Separate what an article states from any interpretation. Headline tone is not a validated price signal; do not invent sentiment scores, article text, or facts absent from the returned records. Mark stale, sparse, duplicate, or unavailable coverage and hand the evidence to report-synthesis.

---
id: equity-research
version: 2.0.0
description: Scope an equity research question and gather only the verified evidence needed to answer it.
triggers: [research, investigate, analyze, analyse, assess, compare, stock, company]
inputs: [user question, company or ticker, timeframe, decision context]
outputs: [bounded objective, evidence-backed findings, explicit coverage gaps]
allowed_tools: [interaction:ask_user, data:fetch_stock_data, data:fetch_fundamentals, news:fetch_news, analysis:run_fundamental_scan, analysis:run_technical_scan, analysis:get_technical_overview]
scripts: []
references: []
---

Resolve the company, market, timeframe, and requested dimensions before gathering evidence. Ask one concise clarification only when the missing detail changes the analysis. Use the specialist tools that match the question, report unavailable dimensions explicitly, and never treat a tool result as a recommendation by itself.

Do not use this skill for order execution, unsupported macro or filing retrieval, or claims that require data not returned by the registered tools. Hand verified findings to report-synthesis.

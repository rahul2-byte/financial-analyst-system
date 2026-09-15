---
id: macro-analysis
version: 1.0.0
description: Connect relevant rates, inflation, currency, policy, and sector conditions to an investment question.
triggers: [macro, economy, inflation, rates, interest, currency, policy, gdp, sector]
inputs: [geography, sector, period, verified macro data]
outputs: [macro drivers, transmission channels, uncertainty]
allowed_tools: [macro:fetch_indicators, research:search_web]
scripts: []
references: []
---

Use only relevant, dated indicators. Explain the transmission mechanism and distinguish observed data from scenario analysis. Never invent a macro series.

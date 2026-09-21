---
id: technical-analysis
version: 2.0.0
description: Interpret the deterministic technical snapshot for a specified instrument, interval, and lookback.
triggers: [technical, chart, price, trend, momentum, moving, support, resistance, volume, volatility, rsi, macd]
inputs: [ticker, period, interval]
outputs: [technical measurements, regime observations, warnings, provenance]
allowed_tools: [data:fetch_stock_data, analysis:get_technical_overview, analysis:run_technical_scan]
scripts: []
references: []
---

LLM instructions are maintained in `backend/app/core/prompts/prompts.yaml`.

---
id: technical-analysis
version: 1.0.0
description: Analyze price and volume behavior with deterministic technical indicators and explicit time windows.
triggers: [technical, price, chart, trend, momentum, moving, support, resistance, volume, volatility]
inputs: [ticker, interval, lookback, market data]
outputs: [indicator findings, regime observations, data limitations]
allowed_tools: [data:fetch_stock_data, validation:validate_data]
scripts: []
references: []
---

Use only fetched market data and deterministic indicators. State the lookback and interval. Do not present technical patterns as forecasts or certainty.

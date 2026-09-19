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

Fetch or reuse the requested OHLCV dataset, then use the deterministic technical tool. State the interval, row count, status, warnings, and provenance. Interpret measurements as evidence about observed price and volume behavior; do not calculate indicators in prose, infer unavailable values, or turn one indicator into a guaranteed forecast. Treat partial or insufficient history as a conclusion limitation.

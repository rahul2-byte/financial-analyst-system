---
id: fundamental-analysis
version: 1.0.0
description: Analyze financial statements, earnings, growth, margins, valuation, and business quality from verified data.
triggers: [fundamental, fundamentals, revenue, earnings, margin, valuation, financials, balance, income, cashflow, compare]
inputs: [company identifiers, period, verified financial data]
outputs: [evidence-backed findings, metric references, coverage gaps]
allowed_tools: [data:fetch_fundamentals, data:fetch_stock_data, validation:validate_data]
scripts: []
references: []
---

Identify the reporting period and accounting basis before comparing companies. Use deterministic tool results for every number. Separate reported values from interpretation, flag unavailable periods, and never estimate a ratio in prose.

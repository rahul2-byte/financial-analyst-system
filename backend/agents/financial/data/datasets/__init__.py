"""Per-dataset helpers used by the financial data fetch/check nodes.

Each dataset (ohlcv, fundamentals, macro, news) has different persistence,
materialization, and metric rules. This package isolates those rules so the graph
nodes can stay focused on orchestration.
"""

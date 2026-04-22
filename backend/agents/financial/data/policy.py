"""Policy constants for financial data nodes.

The data nodes use heuristic thresholds for determining whether a dataset is
"fresh enough" and "complete enough".

Behavior-preserving note:
Values in this module must remain identical to their current inline values in the
node modules. Centralizing them prevents drift between nodes.
"""

from __future__ import annotations

REQUIRED_DATASETS: tuple[str, ...] = ("ohlcv", "news", "fundamentals", "macro")

# Used by data_check_node when evaluating if a dataset is stale.
DATA_CHECK_FRESHNESS_THRESHOLD = 0.6

# Used by data_fetch_node when deciding whether local materialization is "ready".
DATA_FETCH_FRESHNESS_THRESHOLD = 0.6

# Used by data_fetch_node when summarizing/recording news cache status.
NEWS_FRESHNESS_THRESHOLD = 0.6

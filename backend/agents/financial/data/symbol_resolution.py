"""Symbol normalization and ranked-match helpers.

This module consolidates ticker canonicalization / variant expansion and the
"ranked instrument search" acceptance heuristic.

Behavior-preserving note:
The thresholds are intentionally parameterized. Callers must supply the same
thresholds currently hardcoded in their node logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.ticker import parse_ticker


def canonicalize_ticker(ticker: str) -> str:
    """Normalize a ticker to its canonical form.

    Empty/whitespace input returns an empty string for legacy callers.
    Non-empty input delegates validation and normalization to the central ticker
    parser.
    """

    value = (ticker or "").strip()
    if not value:
        return ""
    return parse_ticker(value).canonical


def ticker_variants(ticker: str) -> list[str]:
    """Expand a ticker into common variants used for lookups.

    The vector store and local caches may store symbols with/without suffixes.
    This function provides a stable list of candidates for querying.
    """

    value = (ticker or "").strip()
    if not value:
        return []
    parsed_ticker = parse_ticker(value)
    variants = list(parsed_ticker.db_lookup_variants)
    if parsed_ticker.exchange_suffix is None:
        return variants

    return list(dict.fromkeys([parsed_ticker.provider_symbol, *variants]))


@dataclass(frozen=True)
class RankedMatchPolicy:
    """Thresholds used to accept a ranked symbol match.

    - `min_top_score`: minimum score required for the top result.
    - `min_gap`: minimum difference between #1 and #2 when multiple results exist.
    """

    min_top_score: float
    min_gap: float


def should_accept_ranked_symbol_match(
    results: list[dict[str, Any]],
    *,
    policy: RankedMatchPolicy,
) -> tuple[bool, str | None]:
    """Decide whether a ranked instrument search result is unambiguous enough.

    Inputs:
    - `results`: list of dict rows with at least `trading_symbol` and `score`.

    Returns:
    - (accepted, symbol). `symbol` is uppercased when accepted.
    """

    if not results:
        return False, None

    top = results[0]
    top_score = float(top.get("score", 0.0) or 0.0)
    symbol = top.get("trading_symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        return False, None

    if len(results) == 1:
        if top_score >= policy.min_top_score:
            return True, symbol.strip().upper()
        return False, symbol.strip().upper()

    runner_up = results[1]
    second_score = float(runner_up.get("score", 0.0) or 0.0)
    if (
        top_score >= policy.min_top_score
        and (top_score - second_score) >= policy.min_gap
    ):
        return True, symbol.strip().upper()

    return False, None

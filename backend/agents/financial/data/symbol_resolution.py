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


def canonicalize_ticker(ticker: str) -> str:
    """Normalize a ticker to its canonical form.

    Rules (legacy):
    - Uppercase and strip whitespace.
    - Remove common Indian equity suffixes (".NS", ".BO") if present.

    Returns an empty string for empty/whitespace input.
    """

    value = (ticker or "").strip().upper()
    if not value:
        return ""
    for suffix in (".NS", ".BO"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def ticker_variants(ticker: str) -> list[str]:
    """Expand a ticker into common variants used for lookups.

    The vector store and local caches may store symbols with/without suffixes.
    This function provides a stable list of candidates for querying.
    """

    canonical = canonicalize_ticker(ticker)
    raw = (ticker or "").strip().upper()
    variants: list[str] = []
    for candidate in (raw, canonical, f"{canonical}.NS", f"{canonical}.BO"):
        cleaned = (candidate or "").strip().upper()
        if cleaned and cleaned not in variants:
            variants.append(cleaned)
    return variants


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
        return (top_score >= policy.min_top_score), symbol.strip().upper()

    runner_up = results[1]
    second_score = float(runner_up.get("score", 0.0) or 0.0)
    if (
        top_score >= policy.min_top_score
        and (top_score - second_score) >= policy.min_gap
    ):
        return True, symbol.strip().upper()

    return False, None

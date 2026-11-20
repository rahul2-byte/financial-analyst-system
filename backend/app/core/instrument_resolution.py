"""Deterministic instrument identity resolution for Indian-market requests."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.ticker import parse_ticker

_EXPLICIT = re.compile(r"\b[A-Z0-9][A-Z0-9&-]{1,14}\.(?:NS|BO)\b", re.IGNORECASE)
_BARE = re.compile(r"\b[A-Z][A-Z0-9&-]{1,14}\b")
_STOPWORDS = frozenset(
    {
        "WHAT",
        "THE",
        "CURRENT",
        "PRICE",
        "LATEST",
        "CLOSE",
        "OF",
        "FOR",
        "IS",
        "SHOW",
        "GET",
        "STOCK",
        "SHARE",
        "ANALYSE",
        "ANALYZE",
        "RESEARCH",
        "LAST",
        "YEAR",
        "ONE",
        "MONTH",
        "DAY",
        "BANK",
        "FUNDAMENTAL",
        "FUNDAMENTALS",
        "TECHNICAL",
        "TECH",
        "ANALYSIS",
        "NEWS",
        "RSI",
        "SMA",
        "EMA",
        "MACD",
        "VALUATION",
        "QUOTE",
        "TICKER",
        "SYMBOL",
        "COMPANY",
        "NSE",
        "BSE",
        "AND",
        "COMPARE",
        "WITH",
        "PROFITABILITY",
        "DEBT",
        "TODAY",
        "BUY",
        "SELL",
        "HOLD",
        "SHARES",
        "AFFECT",
        "MIGHT",
        "HOW",
        "GIVE",
        "ME",
        "ON",
        "IT",
        "ITS",
        "ABOUT",
        "IN",
        "ARE",
        "TELL",
        "SHOULD",
        "WORTH",
        "RECENT",
        "UPDATE",
        "UPDATES",
        "TO",
        "ANY",
    }
)
MAX_CANDIDATES_SHOWN = 5
MAX_FALLBACK_SEARCHES = 6


@dataclass(frozen=True, slots=True)
class InstrumentResolution:
    status: str
    ticker: str | None = None
    candidates: tuple[dict[str, Any], ...] = ()
    reason: str | None = None


def resolve_instrument(
    query: str,
    search: Callable[[str], list[dict[str, Any]]] | None = None,
) -> InstrumentResolution:
    """Resolve an explicit symbol or a provider-backed name without guessing."""
    explicit = _EXPLICIT.search(query.upper())
    if explicit:
        return InstrumentResolution(
            "resolved", ticker=parse_ticker(explicit.group()).provider_symbol
        )
    if search is None:
        return InstrumentResolution(
            "unresolved", reason="provider instrument search unavailable"
        )
    terms = [token for token in _BARE.findall(query.upper()) if token not in _STOPWORDS]
    search_term = " ".join(terms) if terms else query.strip()
    candidates = _rank_candidates(_unique_candidates(search(search_term)), search_term)
    if not candidates and len(terms) > 1:
        # Filler words can hide the real name; try adjacent pairs, then single
        # tokens. Only an exact symbol match may resolve from this path;
        # anything else is offered back to the user, never guessed.
        long_terms = [term for term in terms if len(term) >= 3]
        phrases = [
            f"{a} {b}" for a, b in zip(long_terms, long_terms[1:], strict=False)
        ] + long_terms
        first: tuple[str, list[dict[str, Any]]] | None = None
        for phrase in phrases[:MAX_FALLBACK_SEARCHES]:
            found = _unique_candidates(search(phrase))
            if not found:
                continue
            exact_hits = [item for item in found if _symbol(item) == phrase]
            if exact_hits:
                return InstrumentResolution(
                    "resolved",
                    ticker=_ticker(exact_hits[0]),
                    candidates=tuple(exact_hits),
                )
            if first is None:
                first = (phrase, found)
        if first is not None:
            return InstrumentResolution(
                "ambiguous",
                candidates=tuple(first[1]),
                reason=_ambiguity_message(first[0], first[1], did_you_mean=True),
            )
    if not candidates:
        return InstrumentResolution(
            "unresolved",
            reason=(
                f"No NSE/BSE instrument named {search_term}. "
                "Try the exact NSE symbol, e.g. INFY or INFY.NS."
            ),
        )
    exact = [item for item in candidates if _symbol(item) == search_term]
    if len(exact) == 1:
        return InstrumentResolution(
            "resolved", ticker=_ticker(exact[0]), candidates=tuple(exact)
        )
    containing = [item for item in candidates if _name_contains_all(item, search_term)]
    if len(containing) == 1:
        return InstrumentResolution(
            "resolved", ticker=_ticker(containing[0]), candidates=tuple(containing)
        )
    symbols = {_symbol(item) for item in candidates}
    if len(symbols) == 1:
        return InstrumentResolution(
            "resolved", ticker=next(iter(symbols)) + ".NS", candidates=tuple(candidates)
        )
    return InstrumentResolution(
        "ambiguous",
        candidates=tuple(candidates),
        reason=_ambiguity_message(search_term, candidates),
    )


def _name_contains_all(item: dict[str, Any], term: str) -> bool:
    name = str(item.get("name") or item.get("short_name") or "").upper()
    words = term.upper().split()
    return bool(words) and all(word in name for word in words)


def _rank_candidates(
    candidates: list[dict[str, Any]], term: str
) -> list[dict[str, Any]]:
    """Exact symbol first, then names containing every term, then the rest."""

    def rank(item: dict[str, Any]) -> int:
        if _symbol(item) == term.upper():
            return 0
        return 1 if _name_contains_all(item, term) else 2

    return sorted(candidates, key=rank)  # stable


def _symbol(item: dict[str, Any]) -> str:
    return str(item.get("trading_symbol") or item.get("symbol") or "").upper().strip()


def _ambiguity_message(
    term: str, candidates: list[dict[str, Any]], *, did_you_mean: bool = False
) -> str:
    shown = candidates[:MAX_CANDIDATES_SHOWN]
    lines = []
    for item in shown:
        symbol = _symbol(item)
        exchange = str(item.get("exchange") or "NSE")
        name = str(item.get("name") or item.get("short_name") or "").strip()
        lines.append(f"- {symbol} ({exchange})" + (f" {name}" if name else ""))
    more = len(candidates) - len(shown)
    tail = f"\n(and {more} more)" if more > 0 else ""
    if did_you_mean:
        return (
            "Did you mean:\n"
            + "\n".join(lines)
            + tail
            + "\nReply with the exact symbol."
        )
    return (
        f"Several NSE/BSE instruments match {term}. Reply with the exact symbol:\n"
        + "\n".join(lines)
        + tail
    )


def _unique_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        symbol = (
            str(item.get("trading_symbol") or item.get("symbol") or "").upper().strip()
        )
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        result.append(dict(item))
    return result


def _ticker(item: dict[str, Any]) -> str:
    symbol = str(item.get("trading_symbol") or item.get("symbol") or "").upper()
    return symbol if symbol.endswith((".NS", ".BO")) else f"{symbol}.NS"

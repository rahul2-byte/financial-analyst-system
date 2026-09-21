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
    }
)


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
        return InstrumentResolution("resolved", ticker=parse_ticker(explicit.group()).provider_symbol)
    if search is None:
        return InstrumentResolution("unresolved", reason="provider instrument search unavailable")
    terms = [token for token in _BARE.findall(query.upper()) if token not in _STOPWORDS]
    search_term = " ".join(terms) if terms else query.strip()
    raw = search(search_term)
    candidates = _unique_candidates(raw)
    if not candidates:
        return InstrumentResolution("unresolved", reason="no NSE/BSE instrument matched")
    exact = [item for item in candidates if str(item.get("trading_symbol", "")).upper() == search_term]
    if len(exact) == 1:
        return InstrumentResolution("resolved", ticker=_ticker(exact[0]), candidates=tuple(exact))
    symbols = {str(item.get("trading_symbol", "")).upper() for item in candidates if item.get("trading_symbol")}
    if len(symbols) == 1:
        return InstrumentResolution("resolved", ticker=next(iter(symbols)) + ".NS", candidates=tuple(candidates))
    return InstrumentResolution(
        "ambiguous",
        candidates=tuple(candidates),
        reason="multiple NSE/BSE instruments matched; require explicit identity",
    )


def _unique_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        symbol = str(item.get("trading_symbol") or item.get("symbol") or "").upper().strip()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        result.append(dict(item))
    return result


def _ticker(item: dict[str, Any]) -> str:
    symbol = str(item.get("trading_symbol") or item.get("symbol") or "").upper()
    return symbol if symbol.endswith((".NS", ".BO")) else f"{symbol}.NS"

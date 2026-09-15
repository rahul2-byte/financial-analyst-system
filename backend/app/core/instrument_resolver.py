from __future__ import annotations

import re
from typing import Any

from app.core.ticker import parse_ticker
from pydantic import BaseModel, Field


class ResolvedInstrument(BaseModel):
    instrument_key: str
    trading_symbol: str
    exchange: str
    segment: str
    instrument_type: str
    underlying_symbol: str | None = None
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None


class ResolutionResult(BaseModel):
    resolved_instruments: list[ResolvedInstrument] = Field(default_factory=list)
    primary_instrument: ResolvedInstrument | None = None
    ambiguous_candidates: list[str] = Field(default_factory=list)
    unresolved_entities: list[str] = Field(default_factory=list)
    resolver_source: str = "deterministic_candidate"


_EXCHANGE_HINTS = {"NSE", "BSE", "NSE_EQ", "BSE_EQ", "NSE_FO", "MCX_FO", "MCX"}


def _normalize_candidate_text(candidate: str) -> str:
    value = (candidate or "").strip()
    if not value:
        return ""

    if "//" in value:
        value = value.split("//", 1)[0].strip()
    value = re.sub(r"\([^)]*\)", "", value).strip()

    if ":" in value:
        left, right = value.split(":", 1)
        if right.strip().upper() in _EXCHANGE_HINTS:
            value = left.strip()

    value = re.sub(r"\s+", " ", value).strip().strip("\"'")
    return value.upper()


def _expand_candidate_variants(candidate: str) -> list[str]:
    normalized = _normalize_candidate_text(candidate)
    if not normalized:
        return []

    variants = [normalized]
    compact = normalized.replace(" ", "")
    if compact and compact not in variants:
        variants.append(compact)

    for token in re.split(r"[\s,;/|]+", normalized):
        token_clean = token.strip()
        if len(token_clean) >= 3 and token_clean not in variants:
            variants.append(token_clean)

    return variants


def _should_accept_ranked_match(
    results: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any] | None]:
    if not results:
        return False, None
    if len(results) == 1:
        return True, results[0]

    top = results[0]
    runner_up = results[1]
    top_score = float(top.get("score", 0.0) or 0.0)
    second_score = float(runner_up.get("score", 0.0) or 0.0)

    if top_score >= 0.85 and (top_score - second_score) >= 0.1:
        return True, top

    return False, None


def _append_resolved(
    resolved: list[ResolvedInstrument],
    seen_keys: set[str],
    candidate: dict[str, Any],
) -> None:
    parsed = _to_resolved(candidate)
    if parsed.instrument_key and parsed.instrument_key not in seen_keys:
        seen_keys.add(parsed.instrument_key)
        resolved.append(parsed)


def _to_resolved(candidate: dict[str, Any]) -> ResolvedInstrument:
    return ResolvedInstrument(
        instrument_key=str(candidate.get("instrument_key", "")),
        trading_symbol=str(candidate.get("trading_symbol", "")),
        exchange=str(candidate.get("exchange", "")),
        segment=str(candidate.get("segment", "")),
        instrument_type=str(candidate.get("instrument_type", "")),
        underlying_symbol=candidate.get("underlying_symbol"),
        company_name=candidate.get("company_name"),
        sector=candidate.get("sector"),
        industry=candidate.get("industry"),
    )


def resolve_instruments(
    user_query: str,
    llm_candidates: list[str] | None = None,
    limit_per_candidate: int = 5,
    exchange_hint: str | None = None,
    segment_hint: str | None = None,
    instrument_type_hint: str | None = None,
) -> ResolutionResult:
    effective_exchange = (exchange_hint or "NSE").strip().upper()
    effective_segment = (segment_hint or "EQ").strip().upper()
    effective_instrument_type = (
        instrument_type_hint.strip().lower()
        if isinstance(instrument_type_hint, str) and instrument_type_hint.strip()
        else None
    )
    candidates = [candidate for candidate in (llm_candidates or []) if candidate]

    if not candidates and user_query:
        candidates = [user_query]

    resolved: list[ResolvedInstrument] = []
    seen_keys: set[str] = set()
    ambiguous: list[str] = []
    unresolved: list[str] = []

    for raw_candidate in candidates:
        # A prose company name is not enough evidence to invent a ticker. Keep
        # resolution conservative unless the caller supplied an explicit
        # uppercase symbol-like token.
        words = str(raw_candidate).split()
        if len(words) > 1 and not any(word.isupper() for word in words):
            unresolved.append(raw_candidate)
            continue
        variants = _expand_candidate_variants(raw_candidate)
        if not variants:
            unresolved.append(raw_candidate)
            continue
        try:
            parsed_ticker = parse_ticker(variants[0].replace(" ", ""))
        except ValueError:
            unresolved.append(raw_candidate)
            continue
        normalized = parsed_ticker.canonical
        suffix_exchange = {
            ".NS": "NSE",
            ".BO": "BSE",
        }.get(parsed_ticker.exchange_suffix or "")
        if not re.fullmatch(r"[A-Z0-9^=\-]{1,24}", normalized):
            unresolved.append(raw_candidate)
            continue
        exchange = suffix_exchange or effective_exchange
        if exchange not in {"NSE", "BSE"}:
            unresolved.append(raw_candidate)
            continue
        _append_resolved(
            resolved,
            seen_keys,
            {
                "instrument_key": f"{exchange}_{effective_segment}:{normalized}",
                "trading_symbol": normalized,
                "exchange": exchange,
                "segment": effective_segment,
                "instrument_type": effective_instrument_type or "equity",
                "underlying_symbol": normalized,
            },
        )

    primary = resolved[0] if resolved else None
    return ResolutionResult(
        resolved_instruments=resolved,
        primary_instrument=primary,
        ambiguous_candidates=ambiguous,
        unresolved_entities=unresolved,
        resolver_source="deterministic_candidate",
    )

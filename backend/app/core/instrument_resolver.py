from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from storage.sql.client import PostgresClient


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
    resolver_source: str = "db_lookup"


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
    client = PostgresClient()
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
        variants = _expand_candidate_variants(raw_candidate)
        if not variants:
            unresolved.append(raw_candidate)
            continue

        matched = False
        ranked_ambiguous = False

        for variant in variants:
            resolve_alias = getattr(client, "resolve_alias", None)
            if callable(resolve_alias):
                alias_match = resolve_alias(variant)
                if isinstance(alias_match, dict):
                    _append_resolved(resolved, seen_keys, alias_match)
                    matched = True
                    break

            exact = client.resolve_exact_symbol(variant)
            if exact:
                _append_resolved(resolved, seen_keys, exact)
                matched = True
                break

            ranked_search = getattr(client, "search_instruments_ranked", None)
            if callable(ranked_search):
                ranked_raw = ranked_search(
                    query=variant,
                    limit=limit_per_candidate,
                    exchange=effective_exchange,
                    segment=effective_segment,
                    instrument_type=effective_instrument_type,
                )
                ranked = ranked_raw if isinstance(ranked_raw, list) else []
                accepted, row = _should_accept_ranked_match(ranked)
                if accepted and row is not None:
                    _append_resolved(resolved, seen_keys, row)
                    matched = True
                    break
                if ranked:
                    ranked_ambiguous = True

        if matched:
            continue

        if ranked_ambiguous:
            ambiguous.append(raw_candidate)
            continue

        likely = client.resolve_underlying(
            variants[0],
            limit=limit_per_candidate,
            exchange=effective_exchange,
            segment=effective_segment,
        )
        if len(likely) == 1:
            _append_resolved(resolved, seen_keys, likely[0])
        elif len(likely) > 1:
            ambiguous.append(raw_candidate)
        else:
            unresolved.append(raw_candidate)

    primary = resolved[0] if resolved else None
    return ResolutionResult(
        resolved_instruments=resolved,
        primary_instrument=primary,
        ambiguous_candidates=ambiguous,
        unresolved_entities=unresolved,
        resolver_source="db_lookup",
    )

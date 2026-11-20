"""Build the display-ready ``ReportView`` the TypeScript frontend lays out.

Python computes and formats; the frontend only draws. Everything here is a pure
function of provider evidence the runtime already holds (the published draft,
verified facts, availability and, when reachable, the price rows and the
deterministic technical snapshot). Nothing is estimated: a block with no real
data is ``None`` or empty, and any inconsistency returns ``None`` so the
frontend falls back to the markdown answer (fail closed).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from app.core.agent_loop.publication import EvidenceFact, _format_fact_value
from app.core.ticker import parse_ticker

from .bridge import protocol as p
from .display import _raw_id_free, clean_text, friendly_error, source_label

DISCLAIMER = (
    "Research aid based on provider data, not investment advice. "
    "Verify figures before acting."
)
MAX_SPARK_POINTS = 48
MAX_KEY_FIGURES = 6
MAX_SIGNALS = 6

_FACT_MARKER = re.compile(r"\[\[fact:([a-zA-Z0-9_.:-]+)\]\]")
_CITATIONS_TAIL = re.compile(r"\s*\[citations?:[^\]]*\]", re.IGNORECASE)

SOURCE_NAMES = {
    "market_data": "Price history",
    "fundamentals": "Fundamentals",
    "news": "News",
    "technical_analysis": "Technical scan",
    "technical_overview": "Technical scan",
    "fundamental_analysis": "Fundamental scan",
}

FIELD_LABELS = {
    "close": "Last close",
    "period_return_pct": "Period return",
    "peRatio": "P/E",
    "forwardPE": "Forward P/E",
    "marketCap": "Market cap",
    "priceToBook": "Price / book",
    "evToEbitda": "EV / EBITDA",
    "debtToEquity": "Debt / equity",
    "profitMargins": "Profit margin",
    "operatingMargins": "Operating margin",
    "grossMargins": "Gross margin",
    "returnOnEquity": "Return on equity",
    "returnOnAssets": "Return on assets",
    "dividendYield": "Dividend yield",
    "totalRevenue": "Revenue",
    "enterpriseValue": "Enterprise value",
    "volume": "Volume",
}
_PREFERRED_FIELDS = (
    "close",
    "period_return_pct",
    "marketCap",
    "peRatio",
    "forwardPE",
    "priceToBook",
    "returnOnEquity",
    "profitMargins",
    "debtToEquity",
    "dividendYield",
)
_EXTREME_DIRECTION = {"overbought": "bearish", "oversold": "bullish"}
SIGNAL_NAMES = {
    "RSI_14": "RSI (14)",
    "SMA_20": "SMA 20",
    "SMA_50": "SMA 50",
    "SMA_200": "SMA 200",
    "MACD_12_26_9": "MACD",
    "MACD_SIGNAL_12_26_9": "MACD signal",
    "BBANDS_UPPER_20_2": "Bollinger upper",
    "BBANDS_LOWER_20_2": "Bollinger lower",
}


def collect_material(
    runner: Any,
    *,
    contract: str | None = None,
) -> dict[str, Any] | None:
    """Gather already-computed run data from a ``ResearchRunner`` (read-only)."""
    loop = getattr(runner, "last_loop", None)
    if loop is None:
        return None
    evidence = getattr(loop, "last_evidence", None)
    tools = getattr(runner, "tool_runner", None)
    latest = getattr(tools, "latest_ohlcv", None)
    ohlcv = latest() if callable(latest) else None
    return {
        "contract": contract or getattr(loop.config, "answer_contract", None),
        "result": dict(getattr(loop, "last_report_result", {}) or {}),
        "facts": dict(evidence.facts) if evidence is not None else {},
        "sources": dict(evidence.sources) if evidence is not None else {},
        "availability": dict(evidence.availability) if evidence is not None else {},
        "technical": getattr(tools, "last_technical_snapshot", None),
        "ohlcv": ohlcv,
    }


def evidence_availability(
    items: Iterable[Mapping[str, Any]] | None,
) -> list[p.ReportSourceStatus] | None:
    """Per-source availability with friendly names; ``None`` when unknown."""
    if not items:
        return None
    rows = _availability_rows(
        {str(item.get("source", index)): item for index, item in enumerate(items)}
    )
    return rows or None


def build_report_view(material: Mapping[str, Any] | None) -> p.ReportView | None:
    """Return the structured view, or ``None`` when it cannot be built safely."""
    if not material:
        return None
    result = material.get("result") or {}
    draft = result.get("draft")
    if result.get("publication_status") != "passed" or not isinstance(draft, dict):
        return None
    try:
        return _build(material, draft)
    except Exception:  # noqa: BLE001 - any inconsistency falls back to markdown
        return None


def _build(material: Mapping[str, Any], draft: dict[str, Any]) -> p.ReportView:
    facts: dict[str, EvidenceFact] = dict(material.get("facts") or {})
    availability: dict[str, dict[str, Any]] = dict(material.get("availability") or {})
    kind: str = "report" if "executive_summary" in draft else "lookup"
    claims: list[dict[str, Any]] = list(draft.get("claims") or [])

    def resolve(text: str) -> str:
        replaced = _FACT_MARKER.sub(lambda m: _format_fact(facts[m.group(1)]), text)
        return clean_text(_CITATIONS_TAIL.sub("", replaced)).strip()

    sources, citation_ref = _sources(material, draft, facts)
    source_ref = {item.ref: item for item in sources}
    ref_by_source_id = {
        sid: ref for ref, sid in _ordered_source_ids(draft).items()
    }

    def refs_for(claim: dict[str, Any] | None) -> list[int]:
        if claim is None:
            return []
        refs = {
            citation_ref[cid]
            for cid in claim.get("evidence_refs") or []
            if cid in citation_ref
        }
        return sorted(refs & set(source_ref))

    summary = resolve(draft["executive_summary" if kind == "report" else "answer"])
    if not summary:
        raise ValueError("empty summary")

    drivers = [
        p.ReportDriver(
            text=resolve(item),
            importance=(_match(item, claims) or {}).get("importance", "supporting"),
            source_refs=refs_for(_match(item, claims)),
        )
        for item in draft.get("key_drivers") or []
    ]
    risks = [
        p.ReportRisk(text=resolve(item), source_refs=refs_for(_match(item, claims)))
        for item in draft.get("risks") or []
    ]
    instrument_symbol = _instrument(facts)
    evidence_rows = _availability_rows(availability)
    limited = any(row.status != "available" for row in evidence_rows)
    observed = (
        max(fact.observed_at for fact in facts.values()) if facts else None
    )
    limitations = [clean_text(str(item)) for item in draft.get("limitations") or []]
    for row in evidence_rows:
        if row.status != "available":
            limitations.append(
                f"{row.name} {'unavailable' if row.status == 'unavailable' else 'degraded'}"
                + (f": {row.reason}" if row.reason else "")
            )
    return p.ReportView(
        kind=kind,  # type: ignore[arg-type]
        instrument=_instrument_model(instrument_symbol),
        quote=_quote(material, facts, instrument_symbol),
        sparkline=_sparkline(material, instrument_symbol),
        evidence=p.ReportEvidence(
            status="limited" if limited else "complete",
            sources=evidence_rows,
            observed_through_text=_date_text(observed) if observed else None,
        ),
        stance_text=None,
        summary=summary,
        key_figures=_key_figures(claims, facts, ref_by_source_id),
        signals=_signals(material, availability, instrument_symbol),
        drivers=drivers,
        risks=risks,
        final_view=resolve(draft["final_view"]) if draft.get("final_view") else None,
        detailed_analysis=(
            resolve(draft["detailed_analysis"])
            if draft.get("detailed_analysis")
            else None
        ),
        limitations=list(dict.fromkeys(limitations)),
        sources=sources,
        disclaimer=DISCLAIMER,
    )


# --- Facts and key figures ---------------------------------------------------


def _field(fact_id: str) -> str:
    return fact_id.rsplit(".", 1)[-1]


def _format_fact(fact: EvidenceFact) -> str:
    """Existing report formatting, with provider fractions/ratios made readable."""
    if fact.unit == "fraction" and isinstance(fact.value, (int, float)):
        return f"{float(fact.value) * 100:.2f}%"
    if fact.unit == "ratio" and isinstance(fact.value, (int, float)):
        return f"{float(fact.value):.2f}"
    if fact.unit == "currency" and isinstance(fact.value, (int, float)):
        return _compact(float(fact.value))
    if _field(fact.fact_id) == "close" and isinstance(fact.value, (int, float)):
        return f"{float(fact.value):,.2f}"
    return _format_fact_value(fact)


def _compact(value: float) -> str:
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= threshold:
            return f"{value / threshold:,.2f}{suffix}"
    return f"{value:,.0f}"


def _label(fact: EvidenceFact) -> str:
    field = _field(fact.fact_id)
    if field in FIELD_LABELS:
        return FIELD_LABELS[field]
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", field).replace("_", " ").strip()
    return spaced[:1].upper() + spaced[1:]


def _key_figures(
    claims: list[dict[str, Any]],
    facts: Mapping[str, EvidenceFact],
    ref_by_source_id: Mapping[str, int],
) -> list[p.ReportKeyFigure]:
    referenced: list[str] = []
    for claim in sorted(
        claims, key=lambda item: ("major", "supporting", "minor").index(item.get("importance", "minor"))
    ):
        for fact_id in claim.get("numeric_refs") or []:
            if fact_id in facts and fact_id not in referenced:
                referenced.append(fact_id)
    preferred = [
        fact_id
        for field in _PREFERRED_FIELDS
        for fact_id in sorted(facts)
        if _field(fact_id) == field and fact_id not in referenced
    ]
    figures: list[p.ReportKeyFigure] = []
    seen: set[str] = set()
    for fact_id in [*referenced, *preferred]:
        fact = facts[fact_id]
        if fact.unit in {"provider_date", "provider_timestamp"}:
            continue
        # Row-level provider fields (e.g. data.rows.3.close) are not headline numbers.
        if re.search(r"\.\d+(\.|$)", fact_id):
            continue
        label = _label(fact)
        if label in seen:
            continue
        seen.add(label)
        figures.append(
            p.ReportKeyFigure(
                label=label,
                value_text=_format_fact(fact),
                as_of_text=_date_text(fact.observed_at),
                source_ref=ref_by_source_id.get(fact.source_id),
            )
        )
        if len(figures) >= MAX_KEY_FIGURES:
            break
    return figures


def _match(text: str, claims: list[dict[str, Any]]) -> dict[str, Any] | None:
    needle = _norm(text)
    for claim in claims:
        hay = _norm(str(claim.get("text", "")))
        if hay and (hay == needle or hay in needle or needle in hay):
            return claim
    return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


# --- Sources -------------------------------------------------------------------


def _ordered_source_ids(draft: Mapping[str, Any]) -> dict[int, str]:
    ordered: dict[str, None] = {}
    for citation in draft.get("citations") or []:
        ordered.setdefault(str(citation["source_id"]), None)
    return {index + 1: sid for index, sid in enumerate(ordered)}


def _provider_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "yahoo" in host:
        return "yfinance"
    if "upstox" in host:
        return "upstox"
    return host.removeprefix("www.")


def _sources(
    material: Mapping[str, Any],
    draft: Mapping[str, Any],
    facts: Mapping[str, EvidenceFact],
) -> tuple[list[p.ReportSource], dict[str, int]]:
    """Numbered cited sources and a citation-id → source-number map."""
    by_number = _ordered_source_ids(draft)
    number_of = {sid: number for number, sid in by_number.items()}
    citation_ref = {
        str(c["citation_id"]): number_of[str(c["source_id"])]
        for c in draft.get("citations") or []
        if str(c["source_id"]) in number_of
    }
    fact_for: dict[str, EvidenceFact] = {}
    for fact in sorted(facts.values(), key=lambda item: item.fact_id):
        current = fact_for.get(fact.source_id)
        if current is None or (bool(fact.source_url), fact.observed_at) > (
            bool(current.source_url),
            current.observed_at,
        ):
            fact_for[fact.source_id] = fact
    records: Mapping[str, Mapping[str, str]] = material.get("sources") or {}
    rows: list[p.ReportSource] = []
    for number, sid in by_number.items():
        fact = fact_for.get(sid)
        record = records.get(sid) or {}
        url = (fact.source_url if fact else None) or record.get("url") or ""
        provider = _provider_from_url(url) if url else sid
        label = clean_text(source_label({"name": provider, "url": url}))
        parsed = urlparse(url)
        host = parsed.netloc if parsed.scheme in {"http", "https"} else None
        rows.append(
            p.ReportSource(
                ref=number,
                label=label,
                url=clean_text(url),
                host=host,
                retrieved_text=(
                    f"observed {_date_text(fact.observed_at)}" if fact else None
                ),
                freshness_text=None,
                trust=fact.quality_status if fact else None,
            )
        )
    return rows, citation_ref


# --- Availability / evidence ---------------------------------------------------


def _availability_rows(
    availability: Mapping[str, Mapping[str, Any]],
) -> list[p.ReportSourceStatus]:
    rows: list[p.ReportSourceStatus] = []
    seen: set[str] = set()
    for key, item in availability.items():
        status = str(item.get("status"))
        if status == "empty":
            status = "unavailable"
        if status not in {"available", "degraded", "unavailable"}:
            continue
        name = SOURCE_NAMES.get(str(item.get("source", key)), str(item.get("source", key)))
        if name in seen and status == "available":
            continue
        seen.add(name)
        reason = item.get("reason")
        rows.append(
            p.ReportSourceStatus(
                name=name,
                status=status,  # type: ignore[arg-type]
                reason=(
                    clean_text(_raw_id_free(friendly_error(str(reason)), name))
                    if reason
                    else None
                ),
            )
        )
    return rows


# --- Price block: quote and sparkline ------------------------------------------


def _instrument(facts: Mapping[str, EvidenceFact]) -> str | None:
    counts: dict[str, int] = {}
    for fact in facts.values():
        counts[fact.instrument] = counts.get(fact.instrument, 0) + 1
    return max(counts, key=lambda key: counts[key]) if counts else None


def _instrument_model(symbol: str | None) -> p.ReportInstrument | None:
    if not symbol:
        return None
    try:
        ticker = parse_ticker(symbol)
    except ValueError:
        return p.ReportInstrument(symbol=clean_text(symbol))
    exchange = {".NS": "NSE", ".BO": "BSE"}.get(ticker.exchange_suffix or "")
    return p.ReportInstrument(symbol=clean_text(ticker.canonical), exchange=exchange)


def _same(a: str | None, b: str | None) -> bool:
    return bool(a and b) and a.upper().replace(" ", "") == b.upper().replace(" ", "")  # type: ignore[union-attr]


def _closes(rows: list[Any]) -> list[tuple[str | None, float]]:
    values: list[tuple[str | None, float]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        raw = row.get("close", row.get("Close"))
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        if not math.isfinite(float(raw)):
            continue
        stamp = row.get("timestamp", row.get("Date", row.get("date")))
        values.append((str(stamp) if stamp is not None else None, float(raw)))
    return values


def _price_series(
    material: Mapping[str, Any], symbol: str | None
) -> tuple[tuple[str, str, str], list[tuple[str | None, float]]] | None:
    latest = material.get("ohlcv")
    if not latest or not symbol:
        return None
    key, rows = latest
    if not _same(str(key[0]), symbol):
        return None
    closes = _closes(rows)
    return (key, closes) if len(closes) >= 2 else None


def _quote(
    material: Mapping[str, Any],
    facts: Mapping[str, EvidenceFact],
    symbol: str | None,
) -> p.ReportQuote | None:
    series = _price_series(material, symbol)
    if series is None or not any(f.source_id == "historical_prices" for f in facts.values()):
        return None
    key, closes = series
    stamp, last = closes[-1]
    change: str | None = None
    direction: p.Direction | None = None
    for fact in facts.values():
        if fact.source_id == "historical_prices" and fact.fact_id.endswith(
            ":data.period_return_pct"
        ) and isinstance(fact.value, (int, float)):
            value = float(fact.value)
            direction = "up" if value > 0 else "down" if value < 0 else "flat"
            change = f"{value:+.2f}% ({key[1]})"
            break
    return p.ReportQuote(
        price_text=f"{last:,.2f}",
        change_text=change,
        direction=direction,
        as_of_text=_stamp_text(stamp),
    )


def _sparkline(
    material: Mapping[str, Any], symbol: str | None
) -> p.ReportSparkline | None:
    series = _price_series(material, symbol)
    if series is None:
        return None
    key, closes = series
    values = [value for _, value in closes]
    if len(values) > MAX_SPARK_POINTS:
        last = len(values) - 1
        values = [
            values[round(i * last / (MAX_SPARK_POINTS - 1))]
            for i in range(MAX_SPARK_POINTS)
        ]
    low, high = min(values), max(values)
    span = high - low
    points = [0.5 if span == 0 else (v - low) / span for v in values]
    return p.ReportSparkline(
        points=points,
        period_text=key[1],
        low_text=f"{low:,.2f}",
        high_text=f"{high:,.2f}",
    )


# --- Signals ---------------------------------------------------------------------


def _signals(
    material: Mapping[str, Any],
    availability: Mapping[str, Mapping[str, Any]],
    symbol: str | None,
) -> list[p.ReportSignal]:
    snapshot = material.get("technical")
    if not isinstance(snapshot, Mapping) or not _same(str(snapshot.get("ticker")), symbol):
        return []
    if not any(
        availability.get(name, {}).get("status") == "available"
        for name in ("technical_overview", "technical_analysis")
    ):
        return []
    by_indicator = {
        str(item.get("indicator")): item
        for item in snapshot.get("measurements") or []
        if isinstance(item, Mapping)
    }
    signals: list[p.ReportSignal] = []
    for indicator, name in SIGNAL_NAMES.items():
        item = by_indicator.get(indicator)
        if not item or item.get("value") is None or not item.get("available", True):
            continue
        value = float(item["value"])
        unit = item.get("unit")
        percentile = item.get("percentile")
        direction = item.get("direction", "unavailable")
        # The engine reads oscillators against their centre (RSI 74 -> "bullish"), which
        # clashes with the "overbought" state next to it. Extremes read as mean-reversion
        # cautions: overbought is bearish, oversold is bullish.
        if direction != "unavailable":
            direction = _EXTREME_DIRECTION.get(str(item.get("state")), direction)
        signals.append(
            p.ReportSignal(
                name=name,
                value_text=f"{value:,.2f}" + (f" {unit}" if unit and unit != "ratio" else ""),
                direction=direction,
                state_text=(
                    clean_text(str(item["state"])).replace("_", " ")
                    if item.get("state") not in (None, "unavailable")
                    else None
                ),
                strength=item.get("strength"),
                percentile_text=(
                    f"{_ordinal(round(float(percentile) * 100))} pct"
                    if isinstance(percentile, (int, float))
                    else None
                ),
            )
        )
        if len(signals) >= MAX_SIGNALS:
            break
    return signals


# --- Dates -------------------------------------------------------------------------


def _ordinal(number: int) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _date_text(value: datetime) -> str:
    return f"{value.day} {value:%b %Y}"


def _stamp_text(stamp: str | None) -> str | None:
    if not stamp:
        return None
    try:
        return _date_text(datetime.fromisoformat(stamp.replace("Z", "+00:00")))
    except ValueError:
        return None

"""Deterministic fake-mode report material (full, partial, lookup).

Used by ``FakeRepl`` (``python -m finai.bridge --fake-report full``), the Python
tests and the TypeScript golden generator. The prices and indicators below are
*synthetic fixture data*; they never come from a provider and must not be
mistaken for market data. The markdown answer is rendered by the real
``publication._render`` so its section structure matches a live run.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from app.core.agent_loop.publication import (
    EvidenceFact,
    ReportDraft,
    _render,
    _source_records,
)
from app.events.models import (
    ResearchEvent,
    RunCompleted,
    ToolCompleted,
    ToolFailed,
    ToolStarted,
)

Kind = Literal["full", "partial", "lookup"]
KINDS: tuple[Kind, ...] = ("full", "partial", "lookup")

_SYMBOL = "HDFCBANK.NS"
_OBSERVED = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
_HISTORY = f"historical_prices:{_SYMBOL}:1y:1d"
_FUND = f"fundamentals_snapshot:{_SYMBOL}"
_NEWS = f"news_articles:{_SYMBOL}"

_URLS = {
    "historical_prices": f"https://finance.yahoo.com/quote/{_SYMBOL}/history/",
    "fundamentals_snapshot": f"https://finance.yahoo.com/quote/{_SYMBOL}/key-statistics/",
    "news_articles": "https://upstox.com/news/market-news/hdfc-bank-q2-results",
}


def _fact(fact_id: str, value: float | int, unit: str, source_id: str) -> EvidenceFact:
    return EvidenceFact(
        fact_id=fact_id,
        value=value,
        unit=unit,
        source_id=source_id,
        instrument=_SYMBOL,
        observed_at=_OBSERVED,
        quality_status="verified",
        source_url=_URLS[source_id],
    )


def _facts(kind: Kind) -> dict[str, EvidenceFact]:
    items = [
        _fact(
            f"{_HISTORY}:data.latest.close",
            846.0,
            "provider_value",
            "historical_prices",
        ),
        _fact(
            f"{_HISTORY}:data.period_return_pct",
            14.82,
            "provider_value",
            "historical_prices",
        ),
        _fact(
            f"{_HISTORY}:data.latest.volume",
            6240100,
            "provider_value",
            "historical_prices",
        ),
    ]
    if kind != "lookup":
        items += [
            _fact(f"{_FUND}:data.peRatio", 15.13, "ratio", "fundamentals_snapshot"),
            _fact(f"{_FUND}:data.priceToBook", 2.1, "ratio", "fundamentals_snapshot"),
            _fact(
                f"{_FUND}:data.returnOnEquity",
                0.1375,
                "fraction",
                "fundamentals_snapshot",
            ),
            _fact(
                f"{_FUND}:data.marketCap", 1.3e13, "currency", "fundamentals_snapshot"
            ),
            _fact(
                f"{_FUND}:data.profitMargins",
                0.2711,
                "fraction",
                "fundamentals_snapshot",
            ),
        ]
    if kind == "full":
        items.append(
            _fact(f"{_NEWS}:data.article_count", 8, "provider_value", "news_articles")
        )
    return {item.fact_id: item for item in items}


def _availability(kind: Kind) -> dict[str, dict[str, Any]]:
    def ok(source: str, count: int) -> dict[str, Any]:
        return {
            "source": source,
            "status": "available",
            "reason": None,
            "evidence_count": count,
        }

    rows = {"market_data": ok("market_data", 3)}
    if kind == "lookup":
        return rows
    rows["fundamentals"] = ok("fundamentals", 5)
    rows["technical_overview"] = ok("technical_overview", 8)
    if kind == "full":
        rows["news"] = ok("news", 1)
    else:
        rows["news"] = {
            "source": "news",
            "status": "unavailable",
            "reason": "news provider timed out",
            "evidence_count": 0,
        }
    return rows


def _ohlcv() -> list[dict[str, Any]]:
    """250 synthetic daily rows whose last close is 846.0 and period return 14.82%."""
    n = 250
    first = 846.0 / 1.1482
    start = date(2026, 11, 20) - timedelta(days=n - 1)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        t = i / (n - 1)
        wobble = 0.045 * math.sin(i / 9.0) + 0.02 * math.sin(i / 3.1)
        close = first + (846.0 - first) * t + first * wobble * (1 - t**8)
        if i == n - 1:
            close = 846.0
        if i == 0:
            close = first
        rows.append(
            {
                "timestamp": (start + timedelta(days=i)).isoformat()
                + "T00:00:00+05:30",
                "close": round(close, 2),
            }
        )
    return rows


def _technical() -> dict[str, Any]:
    def m(
        indicator: str,
        value: float,
        direction: str,
        state: str,
        strength: float,
        pct: float,
    ) -> dict[str, Any]:
        return {
            "indicator": indicator,
            "category": "momentum",
            "value": value,
            "unit": None,
            "direction": direction,
            "state": state,
            "strength": strength,
            "percentile": pct,
            "available": True,
            "evidence_id": f"tech:{indicator}",
        }

    return {
        "ticker": _SYMBOL,
        "as_of": "2026-11-20T00:00:00+05:30",
        "interval": "1d",
        "status": "ok",
        "measurements": [
            m("RSI_14", 77.95, "bearish", "overbought", 0.78, 0.93),
            m("SMA_20", 821.4, "bullish", "price_above", 0.46, 0.81),
            m("SMA_50", 804.9, "bullish", "price_above", 0.52, 0.88),
            m("SMA_200", 778.3, "bullish", "price_above", 0.61, 0.9),
            m("MACD_12_26_9", 9.84, "bullish", "above_signal", 0.57, 0.84),
        ],
    }


_FULL_DRAFT: dict[str, Any] = {
    "executive_summary": (
        "HDFC Bank closed at ₹[[fact:@H@:data.latest.close]] after a "
        "[[fact:@H@:data.period_return_pct]] one-year move. Trailing P/E of "
        "[[fact:@F@:data.peRatio]] sits below its recent history while momentum is stretched."
    ),
    "key_drivers": [
        "Valuation: P/E of [[fact:@F@:data.peRatio]] and price/book of [[fact:@F@:data.priceToBook]] look undemanding for the franchise.",
        "Profitability: return on equity of [[fact:@F@:data.returnOnEquity]] with a [[fact:@F@:data.profitMargins]] profit margin.",
        "Trend: price holds above its 20, 50 and 200 day averages.",
        "Newsflow: Q2 results coverage points to steady loan growth.",
    ],
    "detailed_analysis": (
        "The stock gained [[fact:@H@:data.period_return_pct]] over the last year and "
        "trades near its highs with daily volume of [[fact:@H@:data.latest.volume]] shares.\n\n"
        "Fundamentals are steady: return on equity of [[fact:@F@:data.returnOnEquity]] and a "
        "market capitalisation of [[fact:@F@:data.marketCap]]. The technical scan shows an RSI "
        "above 75, which historically precedes consolidation."
    ),
    "risks": [
        "Momentum is stretched: RSI above 75 raises the odds of a pullback.",
        "Net interest margin pressure could cap earnings growth.",
        "Single-name concentration: banking sector rotation would hit the stock regardless of fundamentals.",
    ],
    "final_view": (
        "Constructive on fundamentals but wait for a pullback: the setup favours "
        "accumulating on dips rather than chasing a stretched RSI."
    ),
    "claims": [
        {
            "claim_id": "k1",
            "text": "Valuation: P/E of [[fact:@F@:data.peRatio]] and price/book of [[fact:@F@:data.priceToBook]] look undemanding for the franchise.",
            "importance": "major",
            "evidence_refs": ["c2"],
            "numeric_refs": [f"{_FUND}:data.peRatio", f"{_FUND}:data.priceToBook"],
        },
        {
            "claim_id": "k2",
            "text": "Profitability: return on equity of [[fact:@F@:data.returnOnEquity]] with a [[fact:@F@:data.profitMargins]] profit margin.",
            "importance": "major",
            "evidence_refs": ["c2"],
            "numeric_refs": [
                f"{_FUND}:data.returnOnEquity",
                f"{_FUND}:data.profitMargins",
            ],
        },
        {
            "claim_id": "k3",
            "text": "Trend: price holds above its 20, 50 and 200 day averages.",
            "importance": "supporting",
            "evidence_refs": ["c1"],
            "numeric_refs": [],
        },
        {
            "claim_id": "k4",
            "text": "Newsflow: Q2 results coverage points to steady loan growth.",
            "importance": "minor",
            "evidence_refs": ["c3"],
            "numeric_refs": [],
        },
        {
            "claim_id": "k5",
            "text": "Momentum is stretched: RSI above 75 raises the odds of a pullback.",
            "importance": "major",
            "evidence_refs": ["c1"],
            "numeric_refs": [f"{_HISTORY}:data.period_return_pct"],
        },
    ],
    "citations": [
        {"citation_id": "c1", "source_id": "historical_prices"},
        {"citation_id": "c2", "source_id": "fundamentals_snapshot"},
        {"citation_id": "c3", "source_id": "news_articles"},
    ],
}

_LOOKUP_DRAFT: dict[str, Any] = {
    "outcome": "answered",
    "answer": (
        "HDFC Bank last closed at ₹[[fact:@H@:data.latest.close]], up "
        "[[fact:@H@:data.period_return_pct]] over the past year."
    ),
    "claims": [
        {
            "claim_id": "k1",
            "text": "HDFC Bank last closed at ₹[[fact:@H@:data.latest.close]].",
            "importance": "major",
            "evidence_refs": ["c1"],
            "numeric_refs": [
                f"{_HISTORY}:data.latest.close",
                f"{_HISTORY}:data.period_return_pct",
            ],
        }
    ],
    "citations": [{"citation_id": "c1", "source_id": "historical_prices"}],
    "limitations": [],
}


def _bind(draft: dict[str, Any]) -> dict[str, Any]:
    """Expand the @H@/@F@ scope placeholders into real fact-id prefixes."""
    text = json.dumps(draft, ensure_ascii=False)
    text = text.replace("@H@", _HISTORY).replace("@F@", _FUND)
    return json.loads(text)  # type: ignore[no-any-return]


def _draft(kind: Kind) -> dict[str, Any]:
    if kind == "lookup":
        return _bind(deepcopy(_LOOKUP_DRAFT))
    draft = _bind(deepcopy(_FULL_DRAFT))
    if kind == "partial":
        draft["key_drivers"] = draft["key_drivers"][:3]
        draft["claims"] = [c for c in draft["claims"] if c["claim_id"] != "k4"]
        draft["citations"] = [c for c in draft["citations"] if c["citation_id"] != "c3"]
    return draft


def fake_material(kind: Kind) -> dict[str, Any]:
    """Run material in the shape ``report_view.collect_material`` produces."""
    facts = _facts(kind)
    return {
        "contract": "lookup" if kind == "lookup" else "report",
        "result": {
            "status": "structured",
            "draft": _draft(kind),
            "publication_status": "passed",
            "reasons": [],
        },
        "facts": facts,
        "sources": {},
        "availability": _availability(kind),
        "technical": _technical() if kind != "lookup" else None,
        "ohlcv": ((_SYMBOL, "1y", "1d"), _ohlcv()),
    }


def fake_markdown(kind: Kind) -> str:
    """The answer text a live run would publish for ``kind`` (real ``_render``)."""
    material = fake_material(kind)
    facts = material["facts"]
    draft = material["result"]["draft"]
    if kind == "lookup":
        text = draft["answer"]
        from app.core.agent_loop.publication import _FACT_MARKER, _format_fact_value

        return _FACT_MARKER.sub(lambda m: _format_fact_value(facts[m.group(1)]), text)
    return _render(
        ReportDraft.model_validate(draft),
        facts,
        {k: v for k, v in _source_records(facts).items()},
        material["availability"],
    )


def fake_events(base: list[ResearchEvent], kind: Kind) -> list[ResearchEvent]:
    """Adapt the HDFC fixture stream to ``kind`` (answer text and completion)."""
    markdown = fake_markdown(kind)
    events: list[ResearchEvent] = []
    for event in base:
        if event.type == "response.delta":
            event = event.model_copy(update={"text": markdown})
        elif event.type == "run.completed":
            assert isinstance(event, RunCompleted)
            event = event.model_copy(
                update={
                    "terminal_status": (
                        "completed_with_limited_evidence"
                        if kind == "partial"
                        else "success"
                    ),
                    "evidence_status": "limited" if kind == "partial" else "complete",
                    "evidence_availability": list(_availability(kind).values()),
                }
            )
        events.append(event)
    if kind == "lookup":
        keep = {
            "run.started",
            "stage.started",
            "response.delta",
            "run.completed",
            "sources.updated",
        }
        events = [
            e
            for e in events
            if e.type in keep or (getattr(e, "tool", None) == "data:fetch_fundamentals")
        ]
        events = [
            e.model_copy(update={"tool": "data:fetch_stock_data"})
            if isinstance(e, (ToolStarted, ToolCompleted))
            else e
            for e in events
        ]
    if kind == "partial":
        events = [
            ToolFailed(
                meta=e.meta,
                tool=e.tool,
                tool_id=e.tool_id,
                message="news provider timed out",
            )
            if isinstance(e, ToolCompleted) and e.tool == "news:fetch_news"
            else e
            for e in events
        ]
    return events

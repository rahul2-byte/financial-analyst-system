"""Usage-test UX regressions: tickers, resolution, direct answers, notices."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from app.core.guardrails import validate_tool_arguments
from app.core.instrument_resolution import resolve_instrument
from app.events.models import EventFactory, ProviderFailed, RunCompleted
from app.models.routing import ExecutionMode, ModelTier, RoutePlan
from finai.plain import (
    REVIEW_UNAVAILABLE_NOTE,
    friendly_error,
    render_event,
    render_sources_plain,
    source_label,
)
from finai.session_runtime import _run_direct_tool, format_direct_answer

# -- Task 1: ticker validation ------------------------------------------------


@pytest.mark.parametrize(
    "ticker", ["M&M", "M&M.NS", "BAJAJ-AUTO.NS", "^NSEI", "tcs.ns"]
)
def test_valid_tickers_pass_guardrails(ticker: str) -> None:
    out = validate_tool_arguments("data:fetch_stock_data", {"ticker": ticker})
    assert out["ticker"] == ticker.upper()


@pytest.mark.parametrize(
    "ticker", ["TCS NS", "TCS'; DROP", 'A"B', "A;B", "A/B", "A..B", "../etc", ""]
)
def test_injection_like_tickers_fail(ticker: str) -> None:
    with pytest.raises(ValueError):
        validate_tool_arguments("data:fetch_stock_data", {"ticker": ticker})


def test_validation_error_is_one_plain_line() -> None:
    with pytest.raises(ValueError) as caught:
        validate_tool_arguments("data:fetch_stock_data", {"ticker": "A;B"})
    message = str(caught.value)
    assert message == 'Ticker "A;B" has unsupported characters'
    assert "[type=" not in message
    dump = "1 validation error for ToolArguments\nticker\n  Value error, bad [type=x]"
    assert friendly_error(dump) == "bad"


# -- Task 2: resolution -------------------------------------------------------


def _search(table: dict[str, list[dict[str, Any]]]):
    def search(term: str) -> list[dict[str, Any]]:
        return table.get(term, [])

    return search


def test_bare_symbol_in_long_query_resolves() -> None:
    search = _search({"INFY": [{"trading_symbol": "INFY", "name": "Infosys"}]})
    result = resolve_instrument(
        "Analyse the fundamentals of INFY — valuation, debt and profitability",
        search,
    )
    assert result.status == "resolved"
    assert result.ticker == "INFY.NS"


_LONG = "Analyse the fundamentals of INFY — valuation, debt and profitability"


def test_filler_word_hit_cannot_override_exact_symbol() -> None:
    search = _search(
        {
            "INFY": [{"trading_symbol": "INFY", "name": "Infosys"}],
            "PROFITABILITY": [{"trading_symbol": "PROFIT", "name": "Wrong Co"}],
        }
    )
    result = resolve_instrument(_LONG, search)
    assert (result.status, result.ticker) == ("resolved", "INFY.NS")


def test_fallback_without_exact_symbol_is_ambiguous_never_resolved() -> None:
    search = _search({"LEVERAGE": [{"trading_symbol": "LEVCO", "name": "Lev Co"}]})
    result = resolve_instrument(
        "Analyse the fundamentals of INFY, valuation and leverage", search
    )
    assert result.status == "ambiguous" and result.ticker is None
    assert "Did you mean:" in (result.reason or "")
    assert "- LEVCO (NSE) Lev Co" in (result.reason or "")
    assert "Reply with the exact symbol." in (result.reason or "")


def test_fallback_search_count_is_capped() -> None:
    calls: list[str] = []

    def search(term: str) -> list[dict[str, Any]]:
        calls.append(term)
        return []

    resolve_instrument("AAA BBB CCC DDD EEE FFF GGG HHH III", search)
    assert len(calls) <= 7


def test_bare_symbol_exact_match_beats_other_hits() -> None:
    search = _search(
        {
            "INFY": [
                {"trading_symbol": "INFYBEES", "name": "x"},
                {"trading_symbol": "INFY", "name": "Infosys"},
            ]
        }
    )
    assert resolve_instrument("INFY", search).ticker == "INFY.NS"


def test_ambiguity_lists_up_to_five_candidates() -> None:
    items = [
        {"trading_symbol": f"ADANI{i}", "exchange": "NSE", "name": f"Adani Co {i}"}
        for i in range(7)
    ]
    result = resolve_instrument(
        "Adani Enterprises", _search({"ADANI ENTERPRISES": items})
    )
    assert result.status == "ambiguous"
    reason = result.reason or ""
    assert reason.count("- ADANI") == 5
    assert "ADANI0 (NSE) Adani Co 0" in reason
    assert "ADANI6" not in reason and "2 more" in reason


def test_unknown_fails_closed_with_distinct_message() -> None:
    result = resolve_instrument("Analyse XYZNOTREAL", _search({}))
    assert result.status == "unresolved" and result.ticker is None
    assert result.reason is not None
    assert result.reason.startswith("No NSE/BSE instrument named XYZNOTREAL")
    assert "INFY.NS" in result.reason
    assert "multiple" not in result.reason.lower()


# -- Task 3: direct-route answer ----------------------------------------------

_PROV = {
    "source": "yfinance",
    "dataset": "historical_prices",
    "instrument": "TCS.NS",
    "currency": "INR",
    "as_of": "2026-11-19T18:30:00+00:00",
    "observed_at": "2026-11-19T18:30:00+00:00",
    "ingested_at": "2026-11-20T14:36:11+00:00",
    "quality_status": "verified",
    "version": "v1",
    "source_url": "https://finance.yahoo.com/quote/TCS.NS/history/",
}
_DATA = {
    "ticker": "TCS.NS",
    "period": "1y",
    "latest": {"Close": 2376.199951171875, "Date": "2026-11-20 00:00:00+05:30"},
    "period_return_pct": -21.1793,
}


class _Runner:
    def definitions(self) -> list[Any]:
        return []

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "data": _DATA, "provenance": _PROV}


def test_direct_answer_text_is_a_sentence() -> None:
    text = format_direct_answer("data:fetch_stock_data", _DATA, _PROV)
    assert text == (
        "TCS.NS last close ₹2,376.20 on 20 Nov 2026 (1-year −21.2%). "
        "Source: Yahoo Finance, as of 2026-11-19T18:30:00+00:00."
    )
    assert format_direct_answer("data:fetch_fundamentals", _DATA, _PROV) is None


async def test_direct_route_plain_text_and_full_payload_in_events() -> None:
    route = RoutePlan.model_construct(
        intent="lookup",
        execution_mode=ExecutionMode.TOOL_ONLY,
        required_tools=["data:fetch_stock_data"],
        allowed_tools={"data:fetch_stock_data"},
        model_tier=ModelTier.NONE,
        confidence=1.0,
    )
    events = [
        e
        async for e in _run_direct_tool(
            _Runner(),  # type: ignore[arg-type]
            "data:fetch_stock_data",
            {"ticker": "TCS.NS"},
            "price of TCS",
            uuid4(),
            route,
            None,
        )
    ]
    text = "".join(render_event(e) for e in events if e.type == "response.delta")
    assert "₹2,376.20" in text and "as of 2026-11-19" in text
    assert not text.lstrip().startswith("{")
    completed = next(e for e in events if e.type == "tool.completed")
    assert completed.detail is not None and '"period_return_pct"' in completed.detail
    assert events[-1].terminal_status == "completed"


# -- Task 4/5: notices ---------------------------------------------------------


def _failed() -> ProviderFailed:
    return EventFactory(uuid4()).make(
        ProviderFailed,
        provider="openrouter",
        attempts=1,
        phase="request",
        message="OpenRouter HTTP 500: boom\nsecond line Bearer abc123def456ghi789",
    )


def test_provider_failure_line_without_structured_fields() -> None:
    line = render_event(_failed())
    assert line.startswith("⚠ OpenRouter error: OpenRouter HTTP 500")
    assert "second line" not in line and "abc123def456" not in line
    assert line.count("\n") == 1


def test_provider_failure_line_with_reason() -> None:
    event = _failed()
    object.__setattr__(event, "reason", "rate_limit")
    object.__setattr__(event, "message", "OpenRouter HTTP 429")
    assert render_event(event) == (
        "⚠ OpenRouter error (rate_limit): rate limited — OpenRouter HTTP 429\n"
    )


def test_review_unavailable_note_rendered_when_present() -> None:
    completed = EventFactory(uuid4()).make(RunCompleted, terminal_status="completed")
    assert REVIEW_UNAVAILABLE_NOTE not in render_event(completed)
    object.__setattr__(completed, "output_review", "unavailable")
    assert REVIEW_UNAVAILABLE_NOTE in render_event(completed)


# -- Task 6: source labels ----------------------------------------------------


def test_source_label_is_descriptive() -> None:
    source = {
        "name": "yfinance",
        "url": "https://finance.yahoo.com/quote/TCS.NS/history/",
    }
    assert source_label(source) == "Yahoo Finance · price history · TCS.NS"
    rendered = render_sources_plain([source, {"name": "upstox", "url": ""}])
    assert "Untitled" not in rendered
    assert source_label({"name": "upstox", "url": ""}) == "Upstox"

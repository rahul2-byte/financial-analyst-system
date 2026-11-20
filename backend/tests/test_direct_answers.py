"""Direct-route answers are readable text, not raw JSON.

Payload shapes follow backend/app/core/agent_loop/tool_runner.py:
``key_values`` (_technical_key_values), ``data.measurements`` and
``data.as_of`` for technicals; flat Yahoo keys (_FUNDAMENTAL_KEY_FIELDS) for
fundamentals.
"""

from typing import Any

from finai.session_runtime import _compact_listing, format_direct_answer

PROV = {
    "source": "yfinance",
    "as_of": "2026-11-20T00:00:00+05:30",
    "currency": "INR",
    "instrument": "RELIANCE.NS",
}


def _tech(rsi: float | None = 75.2) -> tuple[dict[str, Any], dict[str, Any]]:
    data = {
        "ticker": "RELIANCE.NS",
        "as_of": "2026-11-20T00:00:00+05:30",
        "interval": "1d",
        "measurements": [{"indicator": "SMA_50", "value": 1244.926}],
    }
    kv: dict[str, Any] = {
        "as_of": data["as_of"],
        "close": 1377.5,
        "SMA_50": 1244.926,
        "SMA_200": 1322.745,
    }
    if rsi is not None:
        kv["RSI_14"] = rsi
    return data, kv


def test_technical_overview_readable() -> None:
    data, kv = _tech()
    text = format_direct_answer("analysis:get_technical_overview", data, PROV, kv)
    assert text is not None
    assert '{"data"' not in text and "{" not in text
    assert "RELIANCE.NS technicals as of 2026-11-20 (daily)" in text
    assert "close ₹1,377.50" in text
    assert "RSI(14) 75.2 (overbought >70)" in text
    assert "SMA50 1,244.93" in text and "SMA200 1,322.74" in text
    assert "SMA20 n/a" in text
    assert text.splitlines()[-1].startswith("Source: Yahoo Finance")
    assert 2 <= len(text.splitlines()) <= 8


def test_technical_scan_oversold_and_missing_rsi() -> None:
    data, kv = _tech(24.0)
    text = format_direct_answer("analysis:run_technical_scan", data, PROV, kv)
    assert text and "RSI(14) 24.0 (oversold <30)" in text
    data, kv = _tech(None)
    text = format_direct_answer("analysis:run_technical_scan", data, PROV, kv)
    assert text and "RSI(14) n/a" in text


def test_fundamentals_readable() -> None:
    data = {"ticker": "INFY.NS", "peRatio": 24.5, "priceToBook": 7.1, "marketCap": None}
    for tool in ("data:fetch_fundamentals", "analysis:run_fundamental_scan"):
        text = format_direct_answer(tool, data, PROV)
        assert text and '{"data"' not in text
        assert "P/E 24.50" in text and "P/B 7.10" in text
        assert "ROE n/a" in text and "Mkt cap n/a" in text


def test_unrecognised_payload_uses_compact_listing() -> None:
    data = {"name": "Infosys", "score": 3, "nested": {"a": 1}}
    assert format_direct_answer("data:fetch_fundamentals", data, PROV) is None
    text = _compact_listing(data, PROV)
    assert "name: Infosys" in text and "score: 3" in text
    assert "{" not in text and "nested" not in text


def test_technical_close_from_real_yfinance_row_shape() -> None:
    from app.core.agent_loop.tool_runner import _technical_key_values

    snapshot = {"as_of": "2026-11-20T00:00:00+05:30", "measurements": []}
    rows = [{"Date": "2026-11-20", "Close": 1377.5, "Open": 1370.0}]
    kv = _technical_key_values(snapshot, rows)
    assert kv["close"] == 1377.5
    assert _technical_key_values(snapshot, [{"close": 9.0}])["close"] == 9.0
    data, _ = _tech()
    text = format_direct_answer("analysis:get_technical_overview", data, PROV, kv)
    assert text and "close ₹1,377.50" in text and "close n/a" not in text


def test_fundamentals_units_labelled() -> None:
    data = {"ticker": "INFY.NS", "returnOnEquity": 0.312, "debtToEquity": 0.453}
    text = format_direct_answer("data:fetch_fundamentals", data, PROV)
    assert text and "ROE 31.2%" in text and "Debt/Equity 0.45x" in text

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.core.ticker import parse_ticker
from experiments.schemas import CostSpec, PortfolioLimits
from experiments.simulation import simulate
from quant.technical_engine import TechnicalEngine


def _frame(n: int = 60) -> pd.DataFrame:
    close = 100 + np.arange(n, dtype=float) + np.sin(np.arange(n))
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC"),
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.full(n, 1000.0),
        }
    )


@pytest.mark.parametrize("raw", ["M&M.NS", "L&TFH.NS", "J&KBANK.NS"])
def test_ticker_allows_ampersand(raw: str) -> None:
    ticker = parse_ticker(raw)
    assert ticker.provider_format_yfinance(default_exchange_suffix=".NS") == raw
    assert "&" in ticker.canonical


def test_ticker_ampersand_default_suffix() -> None:
    assert (
        parse_ticker("m&m").provider_format_yfinance(default_exchange_suffix=".NS")
        == "M&M.NS"
    )


def test_macd_outputs_line_signal_histogram() -> None:
    snap = TechnicalEngine().analyze(_frame(), ticker="TEST.NS")
    by_name = {m.indicator: m.value for m in snap.measurements}
    line = by_name["MACD_12_26_9"]
    signal = by_name["MACD_SIGNAL_12_26_9"]
    hist = by_name["MACD_HIST_12_26_9"]
    assert line is not None and signal is not None and hist is not None
    assert hist == pytest.approx(line - signal)
    assert line != pytest.approx(hist)


def test_bad_rows_are_dropped_and_counted() -> None:
    frame = _frame(100)
    frame.loc[10, "close"] = np.nan
    frame.loc[20, "high"] = frame.loc[20, "low"] - 5  # OHLC violation
    snap = TechnicalEngine().analyze(frame, ticker="TEST.NS")
    assert snap.metadata["dropped_rows"] == 2
    assert snap.row_count == 98


def test_clean_frame_reports_zero_dropped() -> None:
    snap = TechnicalEngine().analyze(_frame(), ticker="TEST.NS")
    assert snap.metadata["dropped_rows"] == 0


def test_too_many_bad_rows_fails_hard() -> None:
    frame = _frame(100)
    frame.loc[:2, "close"] = np.nan  # 3% bad
    with pytest.raises(ValueError, match="too many invalid"):
        TechnicalEngine().analyze(frame, ticker="TEST.NS")


def _limits() -> PortfolioLimits:
    return PortfolioLimits(
        max_asset_weight=1,
        max_gross_exposure=1,
        min_cash_weight=0,
        max_holdings=1,
        max_turnover=2,
    )


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "AAA", "timestamp": "2026-01-01", "open": 100, "close": 100},
            {"ticker": "AAA", "timestamp": "2026-01-02", "open": 100, "close": 100},
        ]
    )


def test_full_weight_with_commission_still_trades() -> None:
    targets = pd.DataFrame(
        [{"ticker": "AAA", "timestamp": "2026-01-02", "desired_weight": 1.0}]
    )
    result = simulate(
        _bars(),
        targets,
        initial_cash=10_000,
        costs=CostSpec(commission_bps=100, spread_bps=0, slippage_bps=0),
        limits=_limits(),
    )
    # 10000 / (100 * 1.01) = 99.0099 -> 99 whole shares.
    assert len(result.fills) == 1
    assert result.fills[0].quantity == 99
    assert result.ending_cash >= 0
    assert result.rejections == ()


def test_unaffordable_order_emits_rejection() -> None:
    targets = pd.DataFrame(
        [{"ticker": "AAA", "timestamp": "2026-01-02", "desired_weight": 1.0}]
    )
    result = simulate(
        _bars(),
        targets,
        initial_cash=100.5,
        # desired 1 share, but 100 * 1.01 = 101 > 100.5 cash.
        costs=CostSpec(commission_bps=100, spread_bps=0, slippage_bps=0),
        limits=_limits(),
    )
    assert result.fills == ()
    assert result.rejections[0]["reason"] == "insufficient_cash"
    assert result.rejections[0]["ticker"] == "AAA"

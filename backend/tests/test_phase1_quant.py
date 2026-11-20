"""Phase 1 regression tests for quant and experiments findings."""

import math
import warnings
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from experiments.cli import run
from experiments.datasets import create_dataset
from experiments.features import generate_features
from experiments.metrics import aggregate_window_metrics, calculate_metrics
from experiments.registry import ExperimentRegistry
from experiments.schemas import (
    CostSpec,
    DatasetRef,
    ExperimentSpec,
    PortfolioLimits,
    ValidationSpec,
)
from experiments.signals import generate_signals
from experiments.simulation import simulate
from experiments.validation import make_splits, purge_splits
from quant.technical_engine import TechnicalEngine
from quant.technical_registry import CORE_REGISTRY

DAY = pd.Timedelta(days=1)


def _dataset(tmp_path, tickers=("AAA",), days=10):
    rows = [
        {
            "ticker": ticker,
            "timestamp": f"2026-01-{day:02d}T00:00:00+00:00",
            "open": day + 10,
            "high": day + 11,
            "low": day + 9,
            "close": day + 10,
            "volume": 100,
        }
        for ticker in tickers
        for day in range(1, days + 1)
    ]
    return create_dataset(
        tmp_path,
        dataset_id="d",
        source="fixture",
        source_bytes=b"fixture",
        rows=rows,
        currency="USD",
        timezone="UTC",
        adjustment="unadjusted",
        as_of=datetime(2026, 1, 20, tzinfo=UTC),
    )


# F-19 ----------------------------------------------------------------------
def test_f19_splits_use_time_windows_shared_across_tickers() -> None:
    # Ticker-major frame: AAA days 1-8 then BBB days 1-8.
    stamps = list(pd.date_range("2026-01-01", periods=8, tz=UTC)) * 2
    ts = pd.Series(stamps)
    splits = make_splits(ts, minimum_train_bars=3, test_bars=2, step_bars=2)
    assert len(splits) == 2  # test windows: days 4-5 and days 6-7
    first = splits[0]
    assert sorted(ts.iloc[list(first.test)].unique()) == list(ts.iloc[3:5])
    # Both tickers appear in each window, with the same timestamps.
    assert len(first.test) == 4
    assert set(ts.iloc[list(first.train)]) == set(ts.iloc[0:3])
    for split in splits:
        assert ts.iloc[list(split.train)].max() < ts.iloc[list(split.test)].min()
    # Windows move forward in time.
    assert ts.iloc[list(splits[1].test)].min() > ts.iloc[list(first.test)].max()


# F-38 ----------------------------------------------------------------------
def test_f38_aggregate_does_not_bridge_windows() -> None:
    w1 = tuple({"equity": v} for v in (100.0, 110.0))
    w2 = tuple({"equity": v} for v in (200.0, 180.0))  # gap: 110 -> 200 ignored
    agg = aggregate_window_metrics([(w1, ()), (w2, ())])
    # Returns +10% and -10%: 1.1 * 0.9 - 1 = -0.01. Bridging would add +81.8%.
    assert agg["cumulative_return"] == pytest.approx(-0.01)
    assert agg["observations"] == 4


def test_f38_cli_reports_per_window_metrics(tmp_path) -> None:
    result = run(
        *_cli_setup(
            tmp_path,
            ValidationSpec(
                minimum_train_bars=3, test_bars=2, step_bars=2, embargo_bars=0
            ),
        )
    )
    record = ExperimentRegistry(tmp_path).load(result["run_id"])
    windows = record["artifacts"]["window_metrics"]
    assert len(windows) >= 2
    assert windows[0]["end"] < windows[1]["start"]


# F-39 ----------------------------------------------------------------------
def test_f39_minimum_embargo_and_horizon_applied_when_zero(tmp_path) -> None:
    result = run(
        *_cli_setup(
            tmp_path,
            ValidationSpec(
                minimum_train_bars=3,
                test_bars=2,
                step_bars=2,
                embargo_bars=0,
                label_horizon_bars=0,
            ),
        )
    )
    artifacts = ExperimentRegistry(tmp_path).load(result["run_id"])["artifacts"]
    assert artifacts["effective_embargo_bars"] == 1
    assert artifacts["effective_label_horizon_bars"] == 1


def test_f39_purge_embargo_uses_next_timestamps_for_all_tickers() -> None:
    stamps = list(pd.date_range("2026-01-01", periods=6, tz=UTC)) * 2
    ts = pd.Series(stamps)
    splits = make_splits(ts, minimum_train_bars=3, test_bars=1, step_bars=1)
    purged = purge_splits(splits, ts, ts + DAY, embargo_bars=1)
    # Test day 4 -> embargo is day 5 for both tickers (rows 4 and 10).
    assert purged[0].embargo == (4, 10)


# F-40 ----------------------------------------------------------------------
def test_f40_available_at_is_bar_close(tmp_path) -> None:
    features = generate_features(_dataset(tmp_path), ema_window=2)
    assert (features["available_at"] == features["timestamp"] + DAY).all()
    assert (features["available_at"] > features["timestamp"]).all()


def test_f40_no_signal_executes_before_feature_available(tmp_path) -> None:
    features = generate_features(_dataset(tmp_path, ("AAA", "BBB")), ema_window=2)
    signals = generate_signals(features)
    execution = signals.groupby("ticker")["timestamp"].shift(-1)
    mask = execution.notna()
    assert (execution[mask] >= signals.loc[mask, "available_at"]).all()


# F-37 ----------------------------------------------------------------------
def test_f37_missing_bar_carries_last_price_and_flags_stale() -> None:
    bars = pd.DataFrame(
        [
            {"ticker": "AAA", "timestamp": "2026-01-01", "open": 100, "close": 100},
            {"ticker": "AAA", "timestamp": "2026-01-02", "open": 100, "close": 110},
            {"ticker": "BBB", "timestamp": "2026-01-01", "open": 50, "close": 50},
            {"ticker": "BBB", "timestamp": "2026-01-02", "open": 50, "close": 50},
            {"ticker": "BBB", "timestamp": "2026-01-03", "open": 50, "close": 50},
        ]
    )
    targets = pd.DataFrame(
        [{"ticker": "AAA", "timestamp": "2026-01-01", "desired_weight": 1.0}]
    )
    limits = PortfolioLimits(
        max_asset_weight=1,
        max_gross_exposure=1,
        min_cash_weight=0,
        max_holdings=2,
        max_turnover=2,
        allow_fractional=True,
    )
    result = simulate(
        bars,
        targets,
        initial_cash=1000,
        costs=CostSpec(commission_bps=0, spread_bps=0, slippage_bps=0),
        limits=limits,
    )
    # 10 shares: day 2 mark 110 -> 1100; day 3 AAA missing -> carried at 110.
    assert [e["equity"] for e in result.equity] == [
        pytest.approx(1000),
        pytest.approx(1100),
        pytest.approx(1100),
    ]
    assert result.equity[2]["stale_tickers"] == ["AAA"]
    assert result.equity[1]["stale_tickers"] == []
    assert calculate_metrics(result.equity, result.fills)["stale_bars"] == 1


# F-42 ----------------------------------------------------------------------
def test_f42_annualised_metrics_hand_checked() -> None:
    equity = tuple({"equity": v} for v in (100.0, 110.0, 99.0))
    m = calculate_metrics(equity, ())
    # returns +0.1, -0.1: mean 0, sample std = sqrt(0.02) = 0.14142136
    assert m["volatility_per_bar"] == pytest.approx(math.sqrt(0.02))
    assert m["volatility"] == pytest.approx(math.sqrt(0.02) * math.sqrt(252))
    assert m["cumulative_return"] == pytest.approx(-0.01)
    assert m["cagr"] == pytest.approx(0.99 ** (252 / 2) - 1)
    assert m["max_drawdown"] == pytest.approx(-0.1)
    assert m["sharpe_ratio"] == pytest.approx(0.0, abs=1e-12)  # default rf 0
    assert m["risk_free_rate"] == 0.0


def test_f42_risk_free_rate_lowers_sharpe() -> None:
    equity = tuple({"equity": v} for v in (100.0, 110.0, 99.0))
    m = calculate_metrics(equity, (), risk_free_rate=0.07)
    per_bar_rf = 1.07 ** (1 / 252) - 1
    expected = (0 - per_bar_rf) / math.sqrt(0.02) * math.sqrt(252)
    assert m["sharpe_ratio"] == pytest.approx(expected)
    assert m["sharpe_ratio"] < 0


# Technical engine -----------------------------------------------------------
def _frame(count: int = 300, index=None) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    close = pd.Series(100 + np.cumsum(rng.normal(0.2, 1.0, count)))
    index = (
        index
        if index is not None
        else pd.date_range("2024-01-01", periods=count, freq="D")
    )
    frame = pd.DataFrame(
        {
            "open": close.to_numpy(),
            "high": (close + 1.5).to_numpy(),
            "low": (close - 1.5).to_numpy(),
            "close": close.to_numpy(),
            "volume": 1000.0,
        }
    )
    frame.index = index
    return frame


def _values(snapshot):
    return {m.indicator: m for m in snapshot.measurements}


def test_f44_strength_and_direction_per_indicator() -> None:
    snap = TechnicalEngine().analyze(_frame(), ticker="X.NS")
    m = _values(snap)
    rsi = m["RSI_14"]
    assert rsi.strength == pytest.approx(min(abs(rsi.value - 50) / 50, 1))
    assert rsi.direction == ("bullish" if rsi.value >= 50 else "bearish")
    close = float(_frame()["close"].iloc[-1])
    sma = m["SMA_20"]
    assert sma.direction == ("bullish" if close > sma.value else "bearish")
    hist = m["MACD_HIST_12_26_9"]
    assert hist.direction == ("bullish" if hist.value > 0 else "bearish")
    assert hist.strength is not None and 0 <= hist.strength <= 1
    pct_b = m["BBANDS_PCT_B_20_2"]
    assert pct_b.direction == ("bullish" if pct_b.value > 0.5 else "bearish")
    adx = m["ADX_14"]
    assert adx.strength == pytest.approx(min(adx.value / 50, 1))
    # No fabricated strength where none is meaningful.
    for name in ("ATR_14", "NATR_14", "OBV", "MACD_12_26_9", "ROC_10"):
        assert m[name].strength is None


def test_f44_old_fake_strength_removed() -> None:
    m = _values(TechnicalEngine().analyze(_frame(), ticker="X.NS"))
    assert m["OBV"].strength is None  # old formula gave min(abs(OBV)/100, 1) == 1


def test_f45_registry_matches_emitted_indicators() -> None:
    snap = TechnicalEngine().analyze(_frame(), ticker="X.NS")
    base = {
        "MACD_SIGNAL_12_26_9": "MACD_12_26_9",
        "MACD_HIST_12_26_9": "MACD_12_26_9",
        "BBANDS_UPPER_20_2": "BBANDS_20_2",
        "BBANDS_LOWER_20_2": "BBANDS_20_2",
    }
    emitted = {base.get(m.indicator, m.indicator) for m in snap.measurements}
    assert emitted == {spec.name for spec in CORE_REGISTRY}
    new = _values(snap)
    for name in ("AROON_14", "STOCH_14_3_3", "CCI_20", "WILLR_14", "ROC_10"):
        assert new[name].available


def test_f45_new_indicators_match_talib() -> None:
    import talib

    frame = _frame()
    h, lo, c = (frame[k].to_numpy() for k in ("high", "low", "close"))
    m = _values(TechnicalEngine().analyze(frame, ticker="X.NS"))
    assert m["CCI_20"].value == pytest.approx(talib.CCI(h, lo, c, 20)[-1])
    assert m["WILLR_14"].value == pytest.approx(talib.WILLR(h, lo, c, 14)[-1])
    assert m["ROC_10"].value == pytest.approx(talib.ROC(c, 10)[-1])
    assert m["AROON_14"].value == pytest.approx(talib.AROONOSC(h, lo, 14)[-1])


def test_f47_as_of_is_ist_and_warning_free() -> None:
    frame = _frame(index=pd.date_range("2024-01-01", periods=300, freq="D"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        snap = TechnicalEngine().analyze(frame, ticker="X.NS")
    last = frame.index[-1]
    assert snap.as_of.utcoffset().total_seconds() == 5.5 * 3600
    assert snap.as_of.date() == last.date()
    assert snap.provenance.timezone == "Asia/Kolkata"


def test_f47_ist_midnight_input_keeps_trading_date() -> None:
    index = pd.date_range("2024-01-01", periods=300, freq="D", tz="Asia/Kolkata")
    snap = TechnicalEngine().analyze(_frame(index=index), ticker="X.NS")
    # Converting to UTC would have shifted this to the previous calendar day.
    assert snap.as_of.date() == index[-1].date()


def test_f47_nanosecond_timestamps_do_not_warn() -> None:
    index = pd.date_range("2024-01-01", periods=300, freq="D") + pd.Timedelta(
        nanoseconds=7
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        TechnicalEngine().analyze(_frame(index=index), ticker="X.NS")


def test_dq39_range_and_relative_volume() -> None:
    frame = _frame(300)
    frame.iloc[-1, frame.columns.get_loc("volume")] = 2000.0  # prior 20 bars: 1000
    m = _values(TechnicalEngine().analyze(frame, ticker="X.NS"))
    assert m["HIGH_52W"].value == pytest.approx(frame["high"].iloc[-252:].max())
    assert m["LOW_52W"].value == pytest.approx(frame["low"].iloc[-252:].min())
    assert m["REL_VOLUME_20"].value == pytest.approx(2.0)
    short = _values(TechnicalEngine().analyze(_frame(100), ticker="X.NS"))
    assert short["HIGH_52W"].value is None  # fail closed: under 252 bars


def _cli_setup(tmp_path, validation: ValidationSpec):
    dataset = _dataset(tmp_path, days=12)
    spec = ExperimentSpec(
        strategy_id="fixture",
        strategy_version="1",
        dataset=DatasetRef(
            dataset_id=dataset.dataset_id,
            source=dataset.source,
            source_hash=dataset.source_hash,
            normalized_hash=dataset.normalized_hash,
            currency=dataset.currency,
            timezone=dataset.timezone,
            adjustment="unadjusted",
            as_of=dataset.as_of,
            tickers=("AAA",),
        ),
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 20, tzinfo=UTC),
        initial_cash=1000,
        base_currency="USD",
        costs=CostSpec(commission_bps=1, spread_bps=1, slippage_bps=1),
        limits=PortfolioLimits(
            max_asset_weight=1,
            max_gross_exposure=1,
            min_cash_weight=0,
            max_holdings=1,
            max_turnover=2,
        ),
        validation=validation,
    )
    path = tmp_path / "spec.json"
    path.write_text(spec.model_dump_json(), encoding="utf-8")
    return tmp_path, tmp_path, path

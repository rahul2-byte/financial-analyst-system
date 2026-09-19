import numpy as np
import pandas as pd
import pytest
import talib
from quant.technical_engine import TechnicalEngine


def bars(count: int = 240) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=count, freq="D", tz="UTC")
    close = pd.Series(np.linspace(100, 150, count), index=index)
    return pd.DataFrame(
        {
            "open": close - 1,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": 1_000,
        },
        index=index,
    )


def test_engine_uses_talib_values_and_typed_snapshot() -> None:
    frame = bars()
    snapshot = TechnicalEngine().analyze(frame, ticker="ABC")
    values = {item.indicator: item.value for item in snapshot.measurements}
    assert snapshot.status == "ok"
    assert values["RSI_14"] == pytest.approx(
        talib.RSI(frame["close"].to_numpy(), 14)[-1]
    )
    assert values["ATR_14"] == pytest.approx(
        talib.ATR(
            frame["high"].to_numpy(),
            frame["low"].to_numpy(),
            frame["close"].to_numpy(),
            14,
        )[-1]
    )


def test_engine_rejects_invalid_ohlc() -> None:
    frame = bars()
    frame.loc[frame.index[-1], "high"] = frame.loc[frame.index[-1], "close"] - 1
    with pytest.raises(ValueError, match="OHLC relationships"):
        TechnicalEngine().analyze(frame, ticker="ABC")


def test_engine_marks_long_lookbacks_unavailable() -> None:
    snapshot = TechnicalEngine().analyze(bars(50), ticker="ABC")
    values = {item.indicator: item.value for item in snapshot.measurements}
    assert snapshot.status == "partial"
    assert values["SMA_200"] is None
    assert "less than 200 bars" in snapshot.warnings[0]


def test_engine_uses_provider_timestamp_column() -> None:
    frame = bars().reset_index(names="timestamp")
    snapshot = TechnicalEngine().analyze(frame, ticker="ABC")
    assert snapshot.as_of.year == 2024

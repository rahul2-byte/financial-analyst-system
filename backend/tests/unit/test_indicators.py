import numpy as np
import pandas as pd
from quant.indicators import TechnicalScanner


def create_dummy_data(n=100):
    """Creates dummy OHLCV data for testing."""
    dates = pd.date_range(start="2024-01-01", periods=n, freq="D")
    # Sine wave with trend and noise
    t = np.linspace(0, 10, n)
    close = 100 + 10 * np.sin(t) + 0.5 * t + np.random.normal(0, 0.1, n)
    high = close + 2
    low = close - 2
    open_price = close - 0.5
    volume = np.random.randint(1000, 5000, n)

    df = pd.DataFrame(
        {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )
    return df


def test_calculate_rsi():
    df = create_dummy_data(50)
    rsi = TechnicalScanner.calculate_rsi(df["close"])
    assert isinstance(rsi, pd.Series)
    assert len(rsi) == 50
    # RSI should be between 0 and 100
    valid_rsi = rsi.dropna()
    assert all(valid_rsi >= 0)
    assert all(valid_rsi <= 100)
    assert not rsi.isna().all()


def test_calculate_macd():
    df = create_dummy_data(100)
    macd = TechnicalScanner.calculate_macd(df["close"])
    assert "line" in macd
    assert "signal" in macd
    assert "histogram" in macd
    assert len(macd["line"]) == 100
    assert isinstance(macd["line"], pd.Series)
    assert not macd["line"].isna().all()


def test_calculate_bollinger_bands():
    df = create_dummy_data(50)
    bb = TechnicalScanner.calculate_bollinger_bands(df["close"])
    assert "upper" in bb
    assert "middle" in bb
    assert "lower" in bb
    assert len(bb["upper"]) == 50

    valid_upper = bb["upper"].dropna()
    valid_middle = bb["middle"].dropna()
    valid_lower = bb["lower"].dropna()

    # Check relative order
    assert (valid_upper >= valid_middle).all()
    assert (valid_middle >= valid_lower).all()


def test_scan_empty_df():
    df = pd.DataFrame()
    result = TechnicalScanner.scan(df)
    assert "error" in result
    assert "empty" in result["error"]


def test_scan_missing_columns():
    df = pd.DataFrame({"not_close": [1, 2, 3]})
    result = TechnicalScanner.scan(df)
    assert "error" in result
    assert "missing" in result["error"].lower()


def test_scan_success():
    df = create_dummy_data(100)
    result = TechnicalScanner.scan(df)
    assert "price_action" in result
    assert "trend" in result
    assert "momentum" in result
    assert "volatility" in result

    assert isinstance(result["momentum"]["rsi_14"], float)
    assert isinstance(result["volatility"]["bb_upper"], float)

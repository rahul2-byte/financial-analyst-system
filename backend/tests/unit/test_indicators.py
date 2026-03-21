import pandas as pd
import numpy as np
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
    rsi = TechnicalScanner.calculate_rsi(df)
    assert isinstance(rsi, pd.Series)
    assert len(rsi) == 50
    # RSI should be between 0 and 100
    valid_rsi = rsi.dropna()
    assert all(valid_rsi >= 0)
    assert all(valid_rsi <= 100)
    # With period 14, at least first 13 should be NaN (min_periods=14)
    # But EWM can start earlier depending on alpha, let's just check it eventually produces values
    assert not rsi.isna().all()


def test_calculate_macd():
    df = create_dummy_data(100)
    macd = TechnicalScanner.calculate_macd(df)
    assert "macd_line" in macd
    assert "signal_line" in macd
    assert "macd_hist" in macd
    assert len(macd["macd_line"]) == 100
    assert isinstance(macd["macd_line"], pd.Series)
    # Check that it produces non-NaN values eventually
    assert not macd["macd_line"].isna().all()


def test_calculate_bollinger_bands():
    df = create_dummy_data(50)
    bb = TechnicalScanner.calculate_bollinger_bands(df)
    assert "upper_band" in bb
    assert "middle_band" in bb
    assert "lower_band" in bb
    assert len(bb["upper_band"]) == 50

    valid_upper = bb["upper_band"].dropna()
    valid_middle = bb["middle_band"].dropna()
    valid_lower = bb["lower_band"].dropna()

    # Check relative order
    assert (valid_upper >= valid_middle).all()
    assert (valid_middle >= valid_lower).all()


def test_scan_empty_df():
    df = pd.DataFrame()
    result = TechnicalScanner.scan(df)
    assert result["status"] == "error"
    assert "empty" in result["message"]


def test_scan_missing_columns():
    df = pd.DataFrame({"not_close": [1, 2, 3]})
    result = TechnicalScanner.scan(df)
    assert result["status"] == "error"
    assert "Missing required columns" in result["message"]


def test_scan_success():
    df = create_dummy_data(100)
    result = TechnicalScanner.scan(df)
    assert result["status"] == "success"
    data = result["data"]
    assert "rsi" in data
    assert "macd" in data
    assert "bollinger_bands" in data

    # Values for latest data point should be valid floats
    assert isinstance(data["rsi"], float)
    assert isinstance(data["macd"]["line"], float)
    assert isinstance(data["macd"]["signal"], float)
    assert isinstance(data["macd"]["histogram"], float)
    assert isinstance(data["bollinger_bands"]["upper"], float)
    assert isinstance(data["bollinger_bands"]["middle"], float)
    assert isinstance(data["bollinger_bands"]["lower"], float)

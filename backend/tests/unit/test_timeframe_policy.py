from agents.shared.timeframe_policy import build_timeframe_policy, normalize_timeframe


def test_normalize_timeframe_accepts_explicit_values() -> None:
    assert normalize_timeframe("5 years") == "5y"
    assert normalize_timeframe("1 month") == "1mo"
    assert normalize_timeframe("6mo") == "6mo"


def test_normalize_timeframe_rejects_ambiguous_values() -> None:
    assert normalize_timeframe("long term") is None
    assert normalize_timeframe("recent") is None


def test_build_timeframe_policy_returns_expected_ohlcv_contract() -> None:
    policy = build_timeframe_policy("5y")

    assert policy["normalized_timeframe"] == "5y"
    assert policy["ohlcv"]["period"] == "5y"
    assert policy["ohlcv"]["interval"] == "1d"
    assert policy["ohlcv"]["expected_points"] == 1260
    assert policy["ohlcv"]["minimum_coverage_ratio"] == 0.8
    assert policy["news"]["minimum_items"] == 10
    assert policy["news"]["minimum_coverage_ratio"] == 0.5
    assert policy["fundamentals"]["required_fields"]
    assert policy["fundamentals"]["minimum_coverage_ratio"] == 0.75
    assert policy["macro"]["required_fields"] == [
        "NIFTY_50",
        "INDIA_VIX",
        "USD_INR",
        "CRUDE_OIL",
        "GOLD",
    ]
    assert policy["macro"]["minimum_coverage_ratio"] == 1.0

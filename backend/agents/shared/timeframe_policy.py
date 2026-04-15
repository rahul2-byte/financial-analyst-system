from __future__ import annotations

from typing import Any

_TIMEFRAME_ALIASES = {
    "1mo": "1mo",
    "1 month": "1mo",
    "3mo": "3mo",
    "3 months": "3mo",
    "6mo": "6mo",
    "6 months": "6mo",
    "1y": "1y",
    "1 year": "1y",
    "3y": "3y",
    "3 years": "3y",
    "5y": "5y",
    "5 years": "5y",
    "10y": "10y",
    "10 years": "10y",
    "ytd": "ytd",
}

_OHLCV_POLICY = {
    "1mo": {"period": "1mo", "interval": "1d", "expected_points": 21},
    "3mo": {"period": "3mo", "interval": "1d", "expected_points": 63},
    "6mo": {"period": "6mo", "interval": "1d", "expected_points": 126},
    "1y": {"period": "1y", "interval": "1d", "expected_points": 252},
    "3y": {"period": "3y", "interval": "1d", "expected_points": 756},
    "5y": {"period": "5y", "interval": "1d", "expected_points": 1260},
    "10y": {"period": "10y", "interval": "1d", "expected_points": 2520},
    "ytd": {"period": "ytd", "interval": "1d", "expected_points": 252},
}

_FUNDAMENTAL_REQUIRED_FIELDS = [
    "marketCap",
    "currentPrice",
    "trailingPE",
    "forwardPE",
    "returnOnEquity",
    "debtToEquity",
    "revenueGrowth",
    "earningsGrowth",
]

_MACRO_REQUIRED_FIELDS = [
    "NIFTY_50",
    "INDIA_VIX",
    "USD_INR",
    "CRUDE_OIL",
    "GOLD",
]


def normalize_timeframe(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().lower().split())
    return _TIMEFRAME_ALIASES.get(normalized)


def build_timeframe_policy(value: str) -> dict[str, Any]:
    normalized = normalize_timeframe(value)
    if normalized is None:
        raise ValueError(f"Unsupported timeframe: {value}")

    ohlcv = dict(_OHLCV_POLICY[normalized])
    ohlcv["minimum_coverage_ratio"] = 0.8
    ohlcv["stale_after_days"] = 5

    return {
        "requested_timeframe": value,
        "normalized_timeframe": normalized,
        "needs_clarification": False,
        "ohlcv": ohlcv,
        "news": {
            "lookback_days": 30,
            "minimum_items": 10,
            "minimum_coverage_ratio": 0.5,
            "stale_after_days": 2,
        },
        "fundamentals": {
            "required_fields": list(_FUNDAMENTAL_REQUIRED_FIELDS),
            "minimum_coverage_ratio": 0.75,
            "stale_after_days": 90,
        },
        "macro": {
            "required_fields": list(_MACRO_REQUIRED_FIELDS),
            "minimum_coverage_ratio": 1.0,
            "stale_after_days": 7,
        },
    }

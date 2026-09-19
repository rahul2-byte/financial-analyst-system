"""Small, explicit registry for enabled technical indicators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    library: Literal["talib", "pandas_ta_classic", "derived"]
    category: str
    parameters: tuple[tuple[str, int | float | str], ...]
    required_columns: tuple[str, ...]
    minimum_history: int
    supported_timeframes: tuple[str, ...]


CORE_REGISTRY: tuple[IndicatorSpec, ...] = (
    IndicatorSpec(
        "SMA_20",
        "talib",
        "trend",
        (("period", 20),),
        ("close",),
        20,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "SMA_50",
        "talib",
        "trend",
        (("period", 50),),
        ("close",),
        50,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "SMA_200",
        "talib",
        "trend",
        (("period", 200),),
        ("close",),
        200,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "EMA_20",
        "talib",
        "trend",
        (("period", 20),),
        ("close",),
        20,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "EMA_50",
        "talib",
        "trend",
        (("period", 50),),
        ("close",),
        50,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "EMA_200",
        "talib",
        "trend",
        (("period", 200),),
        ("close",),
        200,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "ADX_14",
        "talib",
        "trend",
        (("period", 14),),
        ("high", "low", "close"),
        28,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "AROON_14",
        "talib",
        "trend",
        (("period", 14),),
        ("high", "low"),
        14,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "RSI_14",
        "talib",
        "momentum",
        (("period", 14),),
        ("close",),
        14,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "MACD_12_26_9",
        "talib",
        "momentum",
        (("fast", 12), ("slow", 26), ("signal", 9)),
        ("close",),
        34,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "STOCH_14_3_3",
        "talib",
        "momentum",
        (("period", 14),),
        ("high", "low", "close"),
        17,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "CCI_20",
        "talib",
        "momentum",
        (("period", 20),),
        ("high", "low", "close"),
        20,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "WILLR_14",
        "talib",
        "momentum",
        (("period", 14),),
        ("high", "low", "close"),
        14,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "ROC_10",
        "talib",
        "momentum",
        (("period", 10),),
        ("close",),
        10,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "ATR_14",
        "talib",
        "volatility",
        (("period", 14),),
        ("high", "low", "close"),
        14,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "NATR_14",
        "talib",
        "volatility",
        (("period", 14),),
        ("high", "low", "close"),
        14,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "BBANDS_20_2",
        "talib",
        "volatility",
        (("period", 20), ("stddev", 2.0)),
        ("close",),
        20,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "KC_20",
        "pandas_ta_classic",
        "volatility",
        (("period", 20),),
        ("high", "low", "close"),
        20,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "OBV", "talib", "volume", (), ("close", "volume"), 2, ("1d", "1w", "1h")
    ),
    IndicatorSpec(
        "MFI_14",
        "talib",
        "volume",
        (("period", 14),),
        ("high", "low", "close", "volume"),
        14,
        ("1d", "1w", "1h"),
    ),
    IndicatorSpec(
        "CMF_20",
        "pandas_ta_classic",
        "volume",
        (("period", 20),),
        ("high", "low", "close", "volume"),
        20,
        ("1d", "1w", "1h"),
    ),
)
